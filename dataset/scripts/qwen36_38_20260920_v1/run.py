"""Add two non-thinking models without changing the historical evaluation."""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import time
from types import SimpleNamespace

CODE = Path(__file__).resolve().parent
PROJECT = CODE.parents[1]
OLD = PROJECT / 'scripts/full_multimodel_20260908_v1'
V5 = PROJECT / 'scripts/full_multimodel_split_v5'
sys.path[:0] = [str(OLD), str(V5), str(PROJECT / 'src')]
from common import load, unique, sha, write, metrics
from output_policy import parse_prediction, gate_usable

RUN_ID = 'qwen36_38_nonthinking_20260920_v1'
ROOT = Path('artifacts/model_results') / RUN_ID
BASE = ROOT.parent / 'full_multimodel_20260908_v1'
WEIGHTS = Path('external/storage/industrybench_qwen368_20260917')
MODELS = ('qwen36_27b_direct', 'qwen38_27b_direct')
SEED = 20260904
SHARDS = 16
EXPECTED = {'L1': 16598, 'L2': 2424, 'L3': 2602, 'L4': 2572}
INPUT_HASHES = {
    'requests.jsonl': '7af7ed3837b316944724485fa35f5424e5c583ec742e0a90c2d2a85cdaa08e04',
    'private_gold.jsonl': '436e63149f44bfedb8e540726266cf496a9662396c4170f9bd8d71aebe418a80',
    'rubric.json': '81d6d5b1ba6616749fced2b8b964efa9f31b53352ed8acaa6ddaefa580c64ef8',
}

def code_paths():
    return [CODE / 'run.py', CODE / 'launch.py', CODE / 'job.sh',
            *[OLD / n for n in ('infer.py', 'common.py', 'protocol.py', 'output_policy.py')],
            V5 / 'base_score_v2.py', V5 / 'gpu_health.py', PROJECT / 'src/spaceconflict/mllm_l4.py']

def frozen_file(path, obj, jsonl=False):
    if path.exists():
        old = load(path) if jsonl else json.loads(path.read_text())
        if old != obj:
            raise ValueError('FROZEN_FILE_CONFLICT:' + str(path))
    else:
        write(path, obj, jsonl=jsonl)

def prepare(a):
    lock = ROOT / 'protocol_lock.json'
    if lock.exists():
        if not a.resume:
            raise FileExistsError(lock)
        verify()
        return
    ROOT.mkdir(parents=True, exist_ok=True)
    for name, digest in INPUT_HASHES.items():
        if sha(BASE / name) != digest:
            raise ValueError('HISTORICAL_INPUT_CHANGED:' + name)
    rows = load(BASE / 'requests.jsonl')
    assert len(unique(rows)) == 24196
    assert dict(collections.Counter(r['level'] for r in rows)) == EXPECTED
    gold = unique(load(BASE / 'private_gold.jsonl'))
    assert set(gold) == set(unique(rows))
    # Select only from historical non-test smoke, independent of model errors/gold.
    pool = load(BASE / 'smoke.jsonl')
    smoke = []
    for level in EXPECTED:
        group = sorted((r for r in pool if r['level'] == level),
                       key=lambda r: hashlib.sha256((str(SEED)+r['sample_id']).encode()).hexdigest())
        assert group and all(r['split'] != 'test' for r in group)
        chosen = [min(group, key=lambda r: len(r['media'])), max(group, key=lambda r: len(r['media']))]
        selected = {r['sample_id']: r for r in chosen}
        for row in group:
            if len(selected) >= 3:
                break
            selected.setdefault(row['sample_id'], row)
        assert len(selected) == 3
        smoke.extend(selected.values())
    assert all(unique(rows)[r['sample_id']] == r for r in smoke)
    # Fresh shared media audit; no downloads or substitute media.
    media = {}
    for row in rows:
        for item in row['media']:
            assert item['kind'] == 'image'
            path = item['path']
            expected = item.get('sha256', '').removeprefix('sha256:')
            if path in media:
                assert not expected or media[path]['sha256'] == expected
                continue
            digest = sha(path)
            assert not expected or digest == expected, 'MEDIA_HASH_MISMATCH:' + path
            media[path] = {'path': path, 'sha256': digest, 'bytes': Path(path).stat().st_size}
            if len(media) % 1000 == 0:
                print(json.dumps({'stage': 'media_audit', 'files': len(media)}), flush=True)
    frozen_file(ROOT / 'media_audit.jsonl', list(media.values()), jsonl=True)
    configurations = {}
    for key in MODELS:
        root = ROOT / key
        root.mkdir(exist_ok=True)
        manifest_path = WEIGHTS / 'manifests' / (key + '.json')
        manifest = json.loads(manifest_path.read_text())
        assert manifest['non_thinking_template_verified'] is True
        for name, record in manifest['files'].items():
            p = Path(manifest['model_path']) / name
            assert p.is_file() and p.stat().st_size == record['bytes'], str(p)
            if not record['is_weight']:
                assert sha(p) == record['sha256'], str(p)
        frozen_file(root / 'source_model_manifest.json', manifest)
        for name in INPUT_HASHES:
            target = root / name
            if not target.exists():
                shutil.copyfile(BASE / name, target)
            assert sha(target) == INPUT_HASHES[name]
        frozen_file(root / 'smoke.jsonl', smoke, jsonl=True)
        frozen_file(root / 'unavailable.jsonl', [], jsonl=True)
        config = dict(key=key, model_id=manifest['model_id'], model_path=manifest['model_path'],
            revision=manifest['revision'], source_manifest_sha256=sha(manifest_path),
            run_id=RUN_ID+'_'+key, seed=SEED, mode='direct', enable_thinking=False,
            gpus=2, dtype='bfloat16', attn_implementation='sdpa', family='qwen3_5',
            decode={'do_sample': False, 'max_new_tokens': 512},
            media_budget={'max_pixels': 401408, 'min_pixels': 100352, 'video_frames': 16, 'video_max_pixels': 200704},
            prompt_version='ordered_frames_bare_json_512_v1', scoring_policy='retained_prefix_512_v1',
            input_hashes={**INPUT_HASHES, 'smoke.jsonl': sha(root / 'smoke.jsonl')},
            shard_count=SHARDS, accuracy_gate=False, quantization=False,
            weight_verification='Prior manifest SHA256 provenance plus fresh file-size checks; fresh hashes of all non-weight files')
        frozen_file(root / 'config.json', config)
        configurations[str(root / 'config.json')] = sha(root / 'config.json')
    frozen_file(lock, dict(run_id=RUN_ID, seed=SEED, expected=EXPECTED,
        files={str(p): sha(p) for p in code_paths()}, configs=configurations,
        inputs=INPUT_HASHES, media_audit_sha256=sha(ROOT / 'media_audit.jsonl'),
        historical_results_read_only=True, smoke_selection='12 historical dev/train requests, 3 per level, min/max images plus seeded hash',
        scientific_prompt_changes=False, max_new_tokens=512, non_thinking=True,
        full_shards_per_model=SHARDS, no_cross_model_dependency=True,
        auxiliary_judge='Not requested in this accuracy evaluation; no explanation score invented'))
    print(json.dumps({'status': 'PREPARED', 'inputs': len(rows), 'unique_media': len(media), 'smoke': len(smoke)}), flush=True)

def verify():
    lock = json.loads((ROOT / 'protocol_lock.json').read_text())
    for path, digest in {**lock['files'], **lock['configs']}.items():
        assert sha(path) == digest, 'FROZEN_CODE_OR_CONFIG_CHANGED:' + path
    return lock

def infer(a):
    verify()
    import gpu_health
    root = ROOT / a.model
    gpu_health.check(root / a.action)
    cfg = json.loads((root / 'config.json').read_text())
    if a.action == 'full':
        assert json.loads((root / 'smoke_acceptance.json').read_text())['status'] == 'PASS'
    import torch
    started = time.monotonic()
    argv = [str(OLD / 'infer.py'), '--run-root', str(root), '--run-id', cfg['run_id'],
            '--scope', a.action, '--seed', str(SEED), '--resume']
    if a.action == 'full':
        argv += ['--num-shards', str(SHARDS), '--shard-index', str(a.shard_index)]
    sys.argv = argv
    runpy.run_path(str(OLD / 'infer.py'), run_name='__main__')
    index = a.shard_index if a.action == 'full' else 0
    path = root / a.action / f'predictions_{index:03d}.jsonl'
    rows = load(path)
    resources = dict(wall_seconds=round(time.monotonic()-started, 3), samples=len(rows),
        inference_seconds=sum(r['inference_seconds'] for r in rows),
        max_prompt_tokens=max(r.get('prompt_tokens', 0) for r in rows),
        gpu_peak_allocated_bytes=[torch.cuda.max_memory_allocated(i) for i in range(2)],
        gpu_peak_reserved_bytes=[torch.cuda.max_memory_reserved(i) for i in range(2)],
        gpu_names=[torch.cuda.get_device_name(i) for i in range(2)],
        job_id=os.environ['SLURM_JOB_ID'], hostname=os.uname().nodename)
    write(root / a.action / f'resources_{index:03d}.json', resources)
    if a.action == 'smoke':
        # This gate tests operation/non-thinking, NOT accuracy or cherry-picked output format.
        failures = [r['sample_id'] for r in rows if r.get('error') or
                    r.get('generated_tokens', 513) > 512 or r.get('channel_status') != 'DIRECT' or
                    not r.get('rendered_prompt', '').rstrip().endswith('</think>')]
        parsed = [parse_prediction(r) for r in rows]
        result = dict(status='FAIL' if failures or len(rows) != 12 else 'PASS',
            failures=failures, samples=len(rows), non_thinking_verified=not failures,
            schema_valid=sum(p['schema_valid'] for p in parsed),
            scoring_usable=sum(gate_usable(p, r) for p, r in zip(parsed, rows)),
            accuracy_gate=False, format_errors_retained_not_prompt_tuned=True,
            raw_sha256=sha(path), resources=resources)
        write(root / 'smoke_acceptance.json', result)
        if result['status'] != 'PASS':
            raise ValueError('OPERATIONAL_SMOKE_FAILED')

def score(a):
    verify()
    from base_score_v2 import score as existing_score
    root = ROOT / a.model
    cfg = json.loads((root / 'config.json').read_text())
    existing_score(SimpleNamespace(run_root=root, run_id=cfg['run_id'], scope='full', gate=False))
    report = json.loads((root / 'full_score.json').read_text())
    diagnostics = json.loads((root / 'full_diagnostics.json').read_text())
    rows = load(root / 'full_scored.jsonl')
    status = 'COMPLETE' if not diagnostics['missing'] and not diagnostics['runtime_errors'] else 'INCOMPLETE'
    lines = [f"# SpaceConflict × {cfg['model_id']}（non-thinking）", '',
        f"状态：{status}；应评测 24,196 条，缺失 {len(diagnostics['missing'])} 条，运行错误 {len(diagnostics['runtime_errors'])} 条。", '',
        '原始全量题目、gold、媒体顺序和评分器不变；贪心解码、BF16、512-token 上限。截断只评分已输出部分，不因截断自动判无效。', '',
        '| 范围 | 输入数 | 正确数 | 准确率 |', '|---|---:|---:|---:|']
    for label in ['All', 'L1', 'L2', 'L3', 'L4']:
        selected = rows if label == 'All' else [r for r in rows if r['level'] == label]
        correct = sum(r['label'] == r['gold'] for r in selected)
        lines.append(f'| {label} | {len(selected)} | {correct} | {100*correct/len(selected):.2f}% |')
    lines += ['', '所有 split 的合计是全量描述性评测，不等于独立留出 test。缺失、运行错误、不可解析答案保留在分母；不可将未完成时的数值作为最终准确率。',
        '解释文本保留，但本轮仅计算既有标签准确率等确定性指标，没有新增自动 judge 分数。', '',
        f"模型 revision：`{cfg['revision']}`。", '原始响应：`full/predictions_*.jsonl`；逐样本评分：`full_scored.jsonl`；分组指标：`full_score.json`。', '']
    text = '\n'.join(lines)
    (root / 'accuracy_report_cn.md').write_text(text)
    # Correct only the newly generated Markdown's legacy hard-coded model title.
    (root / 'full_score.md').write_text(text)
    write(root / 'acceptance.json', dict(status=status, expected_inputs=24196,
        missing=len(diagnostics['missing']), runtime_errors=len(diagnostics['runtime_errors']),
        schema_valid=diagnostics['complete_schema_valid'], scoring_usable=diagnostics['scoring_usable'],
        report_sha256=sha(root / 'full_score.json'), row_sha256=sha(root / 'full_scored.jsonl')))

def tests(a):
    good = {'raw_response': '{"label":"SUPPORTED","confidence":0.8,"reason":"Visible."}', 'generated_tokens': 20}
    assert parse_prediction(good)['schema_valid']
    cut = {'raw_response': '{"label":"SUPPORTED","confidence":0.8,"reason":"Part', 'generated_tokens': 512, 'finish_reason': 'length'}
    assert parse_prediction(cut)['label'] == 'SUPPORTED'
    assert gate_usable(parse_prediction(cut), cut)
    assert parse_prediction({'raw_response': 'reason says SUPPORTED'})['label'] is None
    assert metrics([{'gold': 'SUPPORTED', 'label': None, 'component': 'unknown'}])['claim_accuracy'] == 0
    for key in MODELS:
        m = json.loads((WEIGHTS / 'manifests' / (key+'.json')).read_text())
        assert m['non_thinking_template_verified'] and m['revision']
    print('PASS: parser, truncation, no prose label extraction, missing denominator, model manifests')

def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('action', choices=['prepare', 'smoke', 'full', 'score', 'tests'])
    p.add_argument('--model', choices=MODELS)
    p.add_argument('--shard-index', type=int, default=0)
    p.add_argument('--run-id', default=RUN_ID)
    p.add_argument('--seed', type=int, default=SEED)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--limit', type=int)
    a = p.parse_args()
    if a.run_id != RUN_ID or a.seed != SEED or a.limit is not None or not 0 <= a.shard_index < SHARDS:
        raise ValueError('PROTOCOL_ARGUMENT_MISMATCH')
    if a.action in ('smoke', 'full', 'score') and not a.model:
        p.error('--model required')
    if a.dry_run:
        print(json.dumps(vars(a)))
        return
    if a.action != 'tests' and not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('SLURM_REQUIRED')
    {'prepare': prepare, 'smoke': infer, 'full': infer, 'score': score, 'tests': tests}[a.action](a)

if __name__ == '__main__':
    main()
