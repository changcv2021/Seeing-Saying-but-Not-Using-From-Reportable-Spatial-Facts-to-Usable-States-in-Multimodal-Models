"""Reuse exact historical scorer on held-out test; report missing/error outputs."""
import csv
import os
from types import SimpleNamespace
from settings import *


def main():
    parser = arguments(__doc__)
    parser.add_argument('--model-index', type=int, required=True)
    args = parser.parse_args()
    validate(args)
    key = KEYS[args.model_index]
    if args.dry_run:
        print(key)
        return
    if not os.environ.get('SLURM_JOB_ID'):
        raise ValueError('SLURM_REQUIRED')
    plan = verify_plan()
    cfg = verify_model(key, plan)
    root = ROOT / key
    for name, digest in cfg['input_hashes'].items():
        if sha(root / name) != digest:
            raise ValueError('SCORE_INPUT_CHANGED:' + name)
    index = []
    complete_shards = []
    for shard in range(SHARDS):
        path = root / 'full' / f'predictions_{shard:03d}.jsonl'
        receipt = root / f'adapter_receipt_{shard:03d}.json'
        done = root / 'full' / f'adapter_completion_{shard:03d}.json'
        rows = load(path) if path.exists() else []
        if rows and not receipt.exists():
            raise ValueError('PREDICTIONS_WITHOUT_ADAPTER_RECEIPT')
        for row in rows:
            if (row['config_sha256'] != plan['configs'][key]
                    or row['requested_samples_sha256'] != cfg['input_hashes']['requests.jsonl']):
                raise ValueError('PREDICTION_PROVENANCE_MISMATCH')
        if done.exists():
            evidence = read(done)
            if evidence['output_sha256'] != sha(path) or evidence['adapter_receipt_sha256'] != sha(receipt):
                raise ValueError('COMPLETED_OUTPUT_CHANGED')
            complete_shards.append(shard)
        index.append(dict(shard=shard, path=str(path), records=len(rows),
                          sha256=sha(path) if path.exists() else None,
                          adapter_receipt=str(receipt), complete=shard in complete_shards))
    from base_score_v2 import score
    score(SimpleNamespace(run_root=root, scope='full', run_id=cfg['run_id'], gate=False))
    report = read(root / 'full_score.json')
    diagnostics = read(root / 'full_diagnostics.json')
    if diagnostics['missing'] or len(complete_shards) != SHARDS:
        status = 'INCOMPLETE_NOT_A_FINAL_RESULT'
    elif diagnostics['runtime_errors']:
        status = 'COMPLETE_WITH_RUNTIME_ERRORS_IN_DENOMINATOR'
    else:
        status = 'COMPLETE_HELDOUT_TEST'
    report.update(status=status, model_id=cfg['model_id'], adapter_provenance=cfg['adapter_provenance'],
                  raw_prediction_index=index, complete_shards=complete_shards,
                  protocol='Unchanged historical prompt, greedy non-thinking, retained 512-token prefix',
                  expected_inputs=N_TEST, expected_worlds=plan['split_worlds']['test'],
                  auxiliary_judge='NOT_RUN_IN_THIS_PRIMARY_TEST_LAUNCH',
                  scorer_sha256=sha(EXTENSION / 'base_score_v2.py'))
    write(root / 'TEST_RESULT.json', report)
    write(root / 'RAW_PREDICTION_INDEX.json', index)
    base = read(ROOT / 'baseline_test_score.json')
    lines = ['# Phase8 held-out test: ' + key, '', '状态：' + status,
             '', '固定最终 step 2237；仅冻结 test 5,608 条 / 1,124 worlds。无 test 选 checkpoint、seed 或提示。',
             '512-token 保留前缀照常评分；格式/运行异常不从分母删除。解释 judge 未在本轮运行，不记为零分。', '',
             '| Level | N | 训练前 ClaimAcc | 训练后 ClaimAcc | Δ pp | 训练前 PairAcc | 训练后 PairAcc | Δ pp |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    table = []
    for level in ('L1', 'L2', 'L3', 'L4', 'Overall'):
        before = base['overall'] if level == 'Overall' else base['by_level'][level]
        after = report['overall'] if level == 'Overall' else report['grouped']['level'][level]
        item = dict(model=key, level=level, n=after['n'], complete_pairs=after['complete_pairs'], status=status)
        values = []
        for metric in ('claim_accuracy', 'pair_accuracy'):
            pre, post = before[metric], after[metric]
            item.update({f'base_{metric}': pre, metric: post,
                         f'delta_{metric}_pp': 100 * (post - pre) if pre is not None and post is not None else None})
            values += ['N/A' if v is None else f'{100*v:.2f}%' for v in (pre, post)]
            values += ['N/A' if pre is None or post is None else f'{100*(post-pre):+.2f}']
        lines.append(f'| {level} | {after["n"]} | ' + ' | '.join(values) + ' |')
        table.append(item)
    lines += ['', f'完成分片：{len(complete_shards)}/{SHARDS}；缺失：{len(diagnostics["missing"])}；'
              f'运行错误：{len(diagnostics["runtime_errors"])}；完整 schema：{diagnostics["complete_schema_valid"]}/{N_TEST}。',
              '', '逐题评分：full_scored.jsonl；原始响应：RAW_PREDICTION_INDEX.json；详细结果：TEST_RESULT.json。', '']
    (root / 'TEST_REPORT_CN.md').write_text('\n'.join(lines))
    # Replace only this new run's legacy template heading, never old reports.
    (root / 'full_score.md').write_text('\n'.join(lines))
    with (root / 'BEFORE_AFTER.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    print(json.dumps(dict(key=key, status=status, overall=report['overall'])), flush=True)
    if status != 'COMPLETE_HELDOUT_TEST':
        raise RuntimeError(status)


if __name__ == '__main__':
    main()
