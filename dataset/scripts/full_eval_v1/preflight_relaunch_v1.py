"""Read-only evaluation-input preflight; write a separate run audit, never gold."""
import argparse
import collections
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
from common import sha, load, unique, write, MODEL_ID, MODEL_REVISION, JUDGE_ID, JUDGE_REVISION, RUBRIC

EXPECTED = {
    'requests.jsonl': '0420b3e6db36fa09157cbf6db0c19b8773dfba61d1b52e3b22e475ec0e5c59b8',
    'smoke.jsonl': 'd2db0b6bd658bd0d6953563b947affac7c4f4c6cea33d34b147ac1613f677956',
    'private_gold.jsonl': '436e63149f44bfedb8e540726266cf496a9662396c4170f9bd8d71aebe418a80',
    'rubric.json': '81d6d5b1ba6616749fced2b8b964efa9f31b53352ed8acaa6ddaefa580c64ef8',
    'unavailable.jsonl': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
}

def model_presence(model_path):
    index = json.loads((model_path / 'model.safetensors.index.json').read_text())
    shards = sorted(set(index['weight_map'].values()))
    sizes = {}
    for name in shards:
        if Path(name).name != name:
            raise ValueError('UNSAFE_WEIGHT_INDEX_PATH')
        path = model_path / name
        if not path.is_file() or path.stat().st_size <= 100:
            raise ValueError(f'MODEL_SHARD_MISSING_OR_EMPTY:{path}')
        sizes[name] = path.stat().st_size
    return dict(path=str(model_path), shards=sizes, weight_bytes=sum(sizes.values()),
                check='index membership and nonzero file sizes; GPU loader will validate tensors')

def inspect(root, run_id, seed):
    cfg = json.loads((root / 'config.json').read_text())
    if (cfg['run_id'], cfg['seed'], cfg['model'], cfg['model_revision'], cfg['judge'], cfg['judge_revision']) != (
            run_id, seed, MODEL_ID, MODEL_REVISION, JUDGE_ID, JUDGE_REVISION):
        raise ValueError('RUN_MODEL_OR_SEED_MISMATCH')
    repair = json.loads((root / 'latest_media_repair_report.json').read_text())
    if not (repair['status'] == 'PASS' and repair['promoted'] and repair['eligible'] == 24196 and repair['unavailable'] == 0):
        raise ValueError('FULL_REPAIR_NOT_VALIDATED')
    hashes = {name: sha(root / name) for name in EXPECTED}
    if hashes != EXPECTED:
        raise ValueError('FROZEN_INPUT_HASH_MISMATCH')
    if json.loads((root / 'rubric.json').read_text()) != RUBRIC:
        raise ValueError('RUBRIC_CHANGED')
    requests = unique(load(root / 'requests.jsonl'))
    gold = unique(load(root / 'private_gold.jsonl'))
    smoke = unique(load(root / 'smoke.jsonl'))
    if len(requests) != 24196 or set(requests) != set(gold) or len(smoke) != 96:
        raise ValueError('RELEASE_OR_SMOKE_COVERAGE_MISMATCH')
    if any(requests.get(sid) != row for sid, row in smoke.items()):
        raise ValueError('SMOKE_NOT_EXACT_SUBSET')
    for scope in ('smoke', 'full', 'smoke_judge', 'full_judge'):
        if any((root / scope).glob('predictions_*.jsonl')) or any((root / scope).glob('judgments_*.jsonl')):
            raise ValueError('RELAUNCH_PREFLIGHT_REQUIRES_NO_EXISTING_PREDICTIONS')
    paths = set()
    for row in requests.values():
        if not isinstance(row.get('claim_text'), str) or not row['claim_text'].strip():
            raise ValueError('EMPTY_CLAIM')
        if row['component'] == 'unknown' and gold[row['sample_id']].get('reference_proposition') is not None:
            raise ValueError('UNKNOWN_REFERENCE_MUST_BE_WITHHELD')
        for media in row['media']:
            kind = media.get('kind', 'image')
            if kind not in ('image', 'video', 'video_frames'):
                raise ValueError('INVALID_MEDIA_KIND')
            selected = media.get('paths') if kind == 'video_frames' else [media.get('path')]
            if not isinstance(selected, list) or not selected or any(not isinstance(p, str) or not p for p in selected):
                raise ValueError('INVALID_MEDIA_PATHS')
            paths.update(selected)
    bundle = Path('artifacts').resolve()
    for raw in sorted(paths):
        path = Path(raw).resolve()
        if not path.is_relative_to(bundle) or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f'MEDIA_MISSING_EMPTY_OR_OUTSIDE_BUNDLE:{raw}')
    env_path = Path('external/projects/iclr benchmark/industry/reports/qwen25vl7b_full_eval_20260902/environment.json')
    env = json.loads(env_path.read_text())
    if (env['model_id'], env['model_revision']) != (MODEL_ID, MODEL_REVISION):
        raise ValueError('MODEL_ENVIRONMENT_REVISION_MISMATCH')
    judge_root = Path('external/scratch/industbench_qwen35_judge')
    judge_manifest = json.loads((judge_root / 'model_manifest.json').read_text())
    if (judge_manifest['model_id'], judge_manifest['revision']) != (JUDGE_ID, JUDGE_REVISION):
        raise ValueError('JUDGE_REVISION_MISMATCH')
    model_checks = [model_presence(Path(env['model_path'])), model_presence(judge_root / 'model/Qwen3.5-4B')]
    return dict(status='PASS', eligible=len(requests), unavailable=0, smoke_inputs=len(smoke),
                by_level=dict(collections.Counter(r['level'] for r in requests.values())),
                media_paths_present=len(paths), input_hashes=hashes, model_checks=model_checks,
                media_check='Frozen validated input hashes plus current path/nonempty checks; not a new full-media decode/hash audit',
                config_sha256=sha(root / 'config.json'), config_snapshot=cfg,
                source_revision={'model': MODEL_REVISION, 'judge': JUDGE_REVISION, 'media_validation_job': repair['job_id']},
                code_hashes={str(p): sha(p) for p in sorted((root / 'code').glob('*.py'))},
                code_commit='NO_GIT_REPOSITORY_AVAILABLE')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--seed', type=int, default=20260904)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--limit', type=int)
    a = p.parse_args()
    if a.limit is not None:
        p.error('This whole-release gate does not permit a partial --limit')
    if a.dry_run:
        print(json.dumps(dict(status='PLANNED', full_inputs=24196, smoke_inputs=96))); return
    output = a.run_root / 'relaunch_preflight_20260905.json'
    if output.exists() and not a.resume:
        raise FileExistsError(output)
    envelope = dict(run_id=a.run_id, seed=a.seed, job_id=os.getenv('SLURM_JOB_ID'), code_sha256=sha(__file__))
    try:
        report = dict(envelope, **inspect(a.run_root, a.run_id, a.seed), success_count=24196, failure_count=0)
        write(output, report)
        print(json.dumps({k:report[k] for k in ('status','eligible','smoke_inputs','media_paths_present')}), flush=True)
    except Exception as exc:
        write(output, dict(envelope, status='FAIL', failure_count=1, error=f'{type(exc).__name__}: {exc}'))
        raise

if __name__ == '__main__':
    main()
