"""Read-only source aggregation; snapshot the available Qwen3.8 response prefix."""
import argparse
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

CODE = Path(__file__).resolve().parent
REPO = CODE.parents[1]
FROZEN = REPO / 'scripts/full_multimodel_20260908_v1'
sys.path.insert(0, str(FROZEN))
from common import metrics, sha, write
from output_policy import parse_prediction, POLICY_VERSION

BASE = Path('artifacts/model_results')
LEGACY = BASE / 'full_multimodel_20260908_v1'
Q368 = BASE / 'qwen36_38_nonthinking_20260920_v1'
EXPECTED = {'L1': 16598, 'L2': 2424, 'L3': 2602, 'L4': 2572}
HASHES = {'requests.jsonl': '7af7ed3837b316944724485fa35f5424e5c583ec742e0a90c2d2a85cdaa08e04',
          'private_gold.jsonl': '436e63149f44bfedb8e540726266cf496a9662396c4170f9bd8d71aebe418a80'}
ORDER = [
    ('qwen25vl_7b', 'Qwen2.5-VL-7B'), ('qwen25vl_32b', 'Qwen2.5-VL-32B'),
    ('qwen35_4b', 'Qwen3.5-4B'), ('qwen35_9b', 'Qwen3.5-9B'), ('qwen35_27b', 'Qwen3.5-27B'),
    ('qwen36_27b_direct', 'Qwen3.6-27B (non-thinking)'),
    ('qwen38_27b_direct', 'Qwen3.8-27B (non-thinking)'),
    ('qwen3vl_8b_instruct', 'Qwen3-VL-8B-Instruct'),
    ('qwen3vl_2b_thinking', 'Qwen3-VL-2B-Thinking'), ('qwen3vl_8b_thinking', 'Qwen3-VL-8B-Thinking'),
    ('internvl35_8b', 'InternVL3.5-8B'), ('internvl35_14b', 'InternVL3.5-14B'),
    ('gemma4_31b_it', 'Gemma-4-31B-it'), ('mimo_vl_7b_rl', 'MiMo-VL-7B-RL'),
    ('gpt56_luna', 'gpt-5.6-luna'), ('gpt54', 'gpt-5.4 (Batch)'), ('claude_opus47', 'claude-opus-4-7')]
APIS = {'gpt56_luna': 'azure_luna_resume_20260920_v2',
        'gpt54': 'azure_gpt54_batch_20260920_v1',
        'claude_opus47': 'azure_claude_opus47_resume_20260921_v2'}


def now():
    return dt.datetime.now(ZoneInfo('America/Indiana/Indianapolis')).isoformat()


def integer_correct(m):
    value = m['n'] * m['claim_accuracy']
    assert abs(value - round(value)) < 1e-7
    return round(value)


def pct(x):
    return 'N/A' if x is None else f'{100*x:.2f}%'


def tests():
    good = {'raw_response': '{"label":"SUPPORTED","reason":"Visible.","confidence":0.8}'}
    assert parse_prediction(good)['label'] == 'SUPPORTED'
    truncated = {'raw_response': '{"label":"SUPPORTED","reason":"Part',
                 'generated_tokens': 512, 'finish_reason': 'length'}
    assert parse_prediction(truncated)['label'] == 'SUPPORTED'
    assert parse_prediction({'raw_response': 'The answer is SUPPORTED.'})['label'] is None
    rows = [{'gold': 'SUPPORTED', 'label': 'SUPPORTED', 'component': 'binary', 'pair_id': 'p'},
            {'gold': 'CONTRADICTORY', 'label': None, 'component': 'binary', 'pair_id': 'p'}]
    assert metrics(rows)['claim_accuracy'] == .5
    assert metrics(rows)['pair_accuracy'] == 0
    assert metrics(rows[:1])['pair_accuracy'] is None


def build(args):
    tests()
    out = BASE / args.run_id
    paper = REPO.parent / 'paper' / args.run_id
    if args.dry_run:
        print(json.dumps({'output': str(out), 'paper': str(paper), 'models': ORDER,
                          'inference': False, 'tests': 'PASS'}, ensure_ascii=False))
        return
    assert os.environ.get('SLURM_JOB_ID'), 'CPU_ANALYSIS_REQUIRES_SLURM'
    if (out / 'acceptance.json').exists():
        assert args.resume, 'EXISTING_FROZEN_SUMMARY_USE_NEW_RUN_ID'
        print((out / 'acceptance.json').read_text())
        return
    assert not (paper / 'Results_CN.md').exists(), 'PRESERVE_EXISTING_PAPER_REPORT'
    out.mkdir(parents=True, exist_ok=True)
    paper.mkdir(parents=True, exist_ok=True)
    source_index = []

    def snapshot(path, key):
        path = Path(path)
        content = path.read_bytes()
        obj = json.loads(content)
        digest = hashlib.sha256(content).hexdigest()
        target = out / 'source_reports' / (key + '.json')
        write(target, obj)
        source_index.append({'path': str(path), 'sha256': digest, 'bytes': len(content),
                             'snapshot': str(target), 'snapshot_sha256': sha(target)})
        return obj

    reports = {}
    for key, name in ORDER:
        if key == 'qwen38_27b_direct':
            continue
        api = key in APIS
        root = BASE / APIS[key] if api else (Q368 if key.startswith('qwen36') else LEGACY) / key
        source = root / ('report.json' if api else 'full_score.json')
        rep = snapshot(source, key)
        assert rep['scoring_policy'] == POLICY_VERSION
        levels = rep['by_level'] if api else rep['grouped']['level']
        assert {k: levels[k]['n'] for k in EXPECTED} == EXPECTED
        assert rep['overall']['n'] == 24196
        assert rep['test_only']['n'] == 5608
        assert sum(integer_correct(levels[k]) for k in EXPECTED) == integer_correct(rep['overall'])
        if api:
            assert rep['status'].startswith('COMPLETE') and rep['returned'] == 24196
            lock = json.loads((root / 'PROTOCOL_LOCK.json').read_text())
            for filename, digest in HASHES.items():
                assert any(Path(p).name == filename and h == digest for p, h in lock['sha256'].items())
            source_index.append({'path': str(root / 'PROTOCOL_LOCK.json'), 'sha256': sha(root / 'PROTOCOL_LOCK.json')})
            model_id, revision = rep['model'], 'AZURE_DEPLOYMENT_ID_NO_WEIGHT_REVISION_CLAIMED'
        else:
            assert rep['status'] == 'PASS'
            cfg = snapshot(root / 'config.json', key + '_config')
            assert all(cfg['input_hashes'][f] == h for f, h in HASHES.items())
            diagnostic = json.loads((root / 'full_diagnostics.json').read_text())
            assert not diagnostic['missing'] and not diagnostic['runtime_errors']
            model_id, revision = cfg['model_id'], cfg.get('revision')
        reports[key] = dict(key=key, name=name, model_id=model_id, revision=revision,
            status=rep['status'], complete=True, n=24196, expected=24196, source=str(source),
            overall=rep['overall'], levels=levels, test_only=rep['test_only'],
            explanation_rubric_score=rep.get('explanation_rubric_score'),
            policy_rejections=len(rep.get('policy_rejected_ids') or []),
            judge_status=rep.get('judge_status', 'NOT_RUN'))

    # Freeze file lengths before reading. Only complete JSONL records in those
    # prefixes are used; later appends never change this report's denominator.
    root = Q368 / 'qwen38_27b_direct'
    cfg = snapshot(root / 'config.json', 'qwen38_config')
    lock = json.loads((Q368 / 'protocol_lock.json').read_text())
    for path, digest in {**lock['files'], **lock['configs']}.items():
        assert sha(path) == digest, 'FROZEN_CODE_OR_CONFIG_CHANGED:' + path
    source_index.append({'path': str(Q368 / 'protocol_lock.json'), 'sha256': sha(Q368 / 'protocol_lock.json')})
    for filename, digest in HASHES.items():
        assert sha(root / filename) == digest
    gold = {}
    with (root / 'private_gold.jsonl').open() as stream:
        for line in stream:
            g = json.loads(line)
            assert g['sample_id'] not in gold
            gold[g['sample_id']] = {k: g[k] for k in
                ('sample_id', 'gold', 'component', 'pair_id', 'level', 'split', 'global_world_id')}
    with (root / 'requests.jsonl').open() as stream:
        request_ids = [json.loads(line)['sample_id'] for line in stream]
    assert len(request_ids) == len(gold) == 24196 and set(request_ids) == set(gold)
    captured_at = now()
    caps = {i: (root / 'full' / f'predictions_{i:03d}.jsonl').stat().st_size
            if (root / 'full' / f'predictions_{i:03d}.jsonl').exists() else 0 for i in range(16)}
    observed, seen, prefix_index = [], set(), []
    config_sha = sha(root / 'config.json')
    for index, cap in caps.items():
        path = root / 'full' / f'predictions_{index:03d}.jsonl'
        expected_ids = request_ids[index::16]
        used, count, ignored_tail = 0, 0, 0
        digest = hashlib.sha256()
        if path.exists():
            with path.open('rb') as stream:
                while used < cap:
                    raw = stream.readline(cap - used)
                    if not raw:
                        raise ValueError('SNAPSHOT_FILE_SHRANK:' + str(path))
                    if not raw.endswith(b'\n'):
                        ignored_tail = len(raw)
                        break
                    row = json.loads(raw)
                    sid = row['sample_id']
                    assert sid not in seen and sid == expected_ids[count]
                    assert row['requested_samples_sha256'] == HASHES['requests.jsonl']
                    assert row['config_sha256'] == config_sha
                    parsed = parse_prediction(row)
                    label = None if row.get('error') else parsed['label']
                    observed.append(dict(gold[sid], label=label, runtime_error=row.get('error'),
                                         raw_path=str(path), raw_line=count + 1))
                    seen.add(sid)
                    digest.update(raw)
                    used += len(raw)
                    count += 1
        manifest = path.with_suffix('.manifest.json')
        if manifest.exists():
            m = json.loads(manifest.read_text())
            assert m['status'] == 'COMPLETE' and m['count'] == count == len(expected_ids)
            assert m['output_sha256'] == digest.hexdigest() and not ignored_tail
        prefix_index.append(dict(path=str(path), frozen_size=cap, consumed_bytes=used,
            ignored_incomplete_tail_bytes=ignored_tail, count=count, expected=len(expected_ids),
            prefix_sha256=digest.hexdigest(), manifest_sha256=sha(manifest) if manifest.exists() else None))
    assert len(seen) == len(observed)
    levels = {k: metrics([r for r in observed if r['level'] == k]) for k in EXPECTED}
    test = metrics([r for r in observed if r['split'] == 'test'])
    q38 = dict(key='qwen38_27b_direct', name=dict(ORDER)['qwen38_27b_direct'],
        model_id=cfg['model_id'], revision=cfg['revision'], status='PROVISIONAL_CURRENT_PREFIX',
        complete=len(observed) == 24196, n=len(observed), expected=24196,
        source=str(out / 'qwen38_current_snapshot.json'), overall=metrics(observed), levels=levels,
        test_only=test, explanation_rubric_score=None, judge_status='NOT_RUN', policy_rejections=0,
        captured_at=captured_at, missing=len(gold) - len(observed),
        runtime_errors=sum(bool(r['runtime_error']) for r in observed),
        missing_ids=sorted(set(gold) - seen), prefixes=prefix_index)
    write(out / 'qwen38_current_snapshot.json', q38)
    write(out / 'qwen38_current_scored.jsonl', observed, jsonl=True)
    reports[q38['key']] = q38
    assert len(reports) == 17

    lines = ['# SpaceConflict 全模型评测结果汇总', '',
        f'快照时间：{captured_at}（美国印第安纳当地时间）。', '',
        '合并此前 12 个完整模型及新增 Qwen3.6、Qwen3.8、Luna、GPT-5.4、Claude。'
        '仅汇总已有结果，不新增模型推理，不修改 release、gold、提示、解析器或原评分。', '',
        '## 1. 统一口径', '',
        '- 完整评测为 **24,196 条输入**：L1=16,598，L2=2,424，L3=2,602，L4=2,572。'
        '包括 SUPPORTED、CONTRADICTORY、UNKNOWN；不是 24,196 个 pair。',
        '- 主表为标签准确率（正确条数 / 该行实际统计条数）；总体按输入数加权，不是四级准确率的简单平均。',
        '- **Qwen3.8 带 † 的值只统计快照内已返回的完整记录**，未完成部分不充作错误、不补预测；'
        '返回的格式错误/运行错误仍留在分母。它与全量结果的覆盖不同，不能用于最终排名。',
        '- 其余模型均为全量已完成结果；Luna 的 10 条、GPT-5.4 的 7 条策略拒绝保留在完整分母中。',
        '- 沿用 `retained_prefix_512_v1`：只评分保留输出，截断本身不自动判无效；无法取得合法标签按未正确计。',
        '- 主表包含全部 split，是描述性全覆盖结果。既有 test-only 子集另列，不把全量成绩称为独立留出测试成绩。', '',
        '## 2. L1–L4 与总体准确率', '',
        '| 模型 | 状态 | 已统计/总输入 | L1 | L2 | L3 | L4 | 总体 |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    csv_rows = []
    for key, name in ORDER:
        rep = reports[key]
        partial = key == 'qwen38_27b_direct' and not rep['complete']
        flag = '†' if partial else ''
        status = '临时，未完成' if partial else ('完成（含拒绝）' if rep['policy_rejections'] else '完成')
        lines.append('| ' + ' | '.join([name + flag, status, f"{rep['n']:,}/24,196",
            *[pct(rep['levels'][lv]['claim_accuracy']) + flag for lv in EXPECTED],
            pct(rep['overall']['claim_accuracy']) + flag]) + ' |')
        row = dict(model=name, model_id=rep['model_id'], status=rep['status'],
            n=rep['n'], expected=24196, coverage=rep['n']/24196,
            overall_correct=integer_correct(rep['overall']),
            overall_accuracy_pct=100*rep['overall']['claim_accuracy'],
            denominator_policy='observed_prefix_including_invalid' if partial else 'full_expected_inputs')
        for lv in EXPECTED:
            m = rep['levels'][lv]
            row.update({lv+'_n': m['n'], lv+'_correct': integer_correct(m),
                        lv+'_accuracy_pct': 100*m['claim_accuracy']})
        for metric in ('pair_accuracy', 'balanced_accuracy', 'macro_f1', 'unknown_f1'):
            row[metric+'_pct'] = None if rep['overall'][metric] is None else 100*rep['overall'][metric]
        row.update(complete_pairs=rep['overall']['complete_pairs'], test_n=rep['test_only']['n'],
            test_accuracy_pct=100*rep['test_only']['claim_accuracy'],
            explanation_rubric_0_100=rep['explanation_rubric_score'],
            policy_rejections=rep['policy_rejections'], source=rep['source'], revision=rep['revision'])
        csv_rows.append(row)
    lines += ['', 'Llama-4-Scout-17B-16E-Instruct：`ACCESS_BLOCKED / GatedRepoError`，未形成评测结果；不记 0 分，不参与比较。', '',
        '## 3. Qwen3.8 当前快照（跑完后替换这一行即可）', '',
        f"当前 {q38['n']:,}/24,196 条（覆盖率 {100*q38['n']/24196:.2f}%），尚缺 {q38['missing']:,} 条。"
        '快照读取时冻结每个文件的字节上限；之后的新响应不混入本报告。', '',
        '| 范围 | 已统计/应有 | 已正确 | 剩余 | 已返回准确率 | 全量最终值可能区间* |',
        '|---|---:|---:|---:|---:|---:|']
    for lv, expected in [('ALL', 24196), *EXPECTED.items()]:
        m = q38['overall'] if lv == 'ALL' else q38['levels'][lv]
        correct, missing = integer_correct(m), expected-m['n']
        lines.append(f"| {lv} | {m['n']:,}/{expected:,} | {correct:,} | {missing:,} | {pct(m['claim_accuracy'])} | "
                     f'{100*correct/expected:.2f}%–{100*(correct+missing)/expected:.2f}% |')
    lines += ['', '*该区间仅假设剩余全部答错或全部答对，是未完成数据的确定性上下界，不是置信区间。',
        '替代分片为 `8305548_9`，评分任务为 `8303429`；作业状态以实时 Slurm 为准。'
        '本报告没有使用落后的 Qwen3.8 `full_score.json`，也没有覆盖它。', '',
        '## 4. 其他已有指标', '',
        '| 模型 | PairAcc | Balanced Acc | Macro-F1 | UNKNOWN F1 | Test Acc（条数） | 解释分（0–100） |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for key, name in ORDER:
        rep = reports[key]
        flag = '†' if key == 'qwen38_27b_direct' and not rep['complete'] else ''
        score = rep['explanation_rubric_score']
        lines.append('| ' + ' | '.join([name + flag,
            *[pct(rep['overall'][m]) for m in ('pair_accuracy', 'balanced_accuracy', 'macro_f1', 'unknown_f1')],
            pct(rep['test_only']['claim_accuracy']) + f"（{rep['test_only']['n']:,}）" + flag,
            'N/A' if score is None else f'{score:.2f}']) + ' |')
    lines += ['', 'PairAcc 仅在 S/C 两条记录齐全的 pair 上计算，要求两条都正确，UNKNOWN 不参与；'
        'Qwen3.8 的完整 pair 数为 '+str(q38['overall']['complete_pairs'])+'，因此也是临时子集指标。',
        '解释分只是已有 Qwen3.5-4B 自动辅助 rubric 结果，不是独立视觉真值验证，也不进入主准确率。'
        '新增五个模型尚无该项评分，N/A 不代表 0 分。本次没有补跑 judge。',
        '未重算 world-cluster 置信区间或显著性，不据小幅百分比差异作显著性结论。', '',
        '## 5. 源结果与后续更新', '',
        f'- 此前 12 模型：`{LEGACY}/<model_key>/full_score.json`。',
        f'- Qwen3.6：`{Q368}/qwen36_27b_direct/full_score.json`。',
        *[f'- {dict(ORDER)[key]}：`{BASE / folder}/report.json`。' for key, folder in APIS.items()],
        f'- Qwen3.8：`{out}/qwen38_current_snapshot.json`（独立快照）；原始文件前缀 hash、路径及行数可追溯。',
        '- `model_results.csv` 含逐级整数正确数、分母、未四舍五入百分数、模型 revision 和每个模型的来源路径。',
        f'- 完整来源 hash、验收及复现代码记录：`{out}/acceptance.json`。',
        '- Qwen3.8 跑完后，读取它最终 `full_score.json`，替换主表 Qwen3.8 行和附表对应行，去除 †，'
        '将分母更新为 24,196；不要改动本次冻结快照或其他模型的历史成绩。', '']
    report_text = '\n'.join(lines)
    (paper / 'Results_CN.md').write_text(report_text)
    (out / 'Results_CN.md').write_text(report_text)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(csv_rows[0]))
    writer.writeheader()
    writer.writerows(csv_rows)
    for folder in (out, paper):
        (folder / 'model_results.csv').write_text(buffer.getvalue(), encoding='utf-8-sig')
    write(out / 'all_model_metrics.json', reports)
    source_comparison = LEGACY / 'model_comparison.csv'
    with source_comparison.open() as stream:
        blocked = [r for r in csv.DictReader(stream) if r['status'] == 'BLOCKED']
    assert blocked and all('GatedRepoError' in r['blocked_reason'] for r in blocked)
    source_index.append({'path': str(source_comparison), 'sha256': sha(source_comparison)})
    write(out / 'source_index.json', source_index)
    write(out / 'acceptance.json', dict(status='PASS', scope='RESULT_AGGREGATION_NOT_NEW_INFERENCE',
        captured_at=captured_at, completed_at=now(), job_id=os.environ['SLURM_JOB_ID'],
        run_id=args.run_id, seed=args.seed, expected=EXPECTED, models_with_results=17,
        complete_models=sum(r['complete'] for r in reports.values()),
        qwen38_returned=q38['n'], qwen38_missing=q38['missing'], blocked_models=['llama4_scout'],
        source_files_read_only=True, historical_scores_unchanged=True,
        input_hashes=HASHES, source_code_commit='NO_GIT_COMMIT_AVAILABLE_FILE_HASH_PROVENANCE',
        code_hashes={str(p): sha(p) for p in (Path(__file__), CODE/'job.sh', FROZEN/'common.py', FROZEN/'output_policy.py')},
        output_hashes={str(out/name): sha(out/name) for name in
            ('Results_CN.md','model_results.csv','all_model_metrics.json','source_index.json',
             'qwen38_current_snapshot.json','qwen38_current_scored.jsonl')},
        tests='parser truncation/null/pair invariants and integer-count consistency PASS',
        command=['sbatch', str(CODE/'job.sh')], public_outputs=[str(paper/'Results_CN.md'), str(paper/'model_results.csv')]))
    print(json.dumps({'status':'PASS','paper':str(paper),'qwen38_n':q38['n'],
                      'qwen38_accuracy':q38['overall']['claim_accuracy']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--run-id', default='model_results_summary_20260921_v1')
    p.add_argument('--seed', type=int, default=20260904)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--limit', type=int)
    a = p.parse_args()
    assert a.seed == 20260904 and a.limit is None
    assert '/' not in a.run_id and a.run_id.startswith('model_results_summary_')
    build(a)
