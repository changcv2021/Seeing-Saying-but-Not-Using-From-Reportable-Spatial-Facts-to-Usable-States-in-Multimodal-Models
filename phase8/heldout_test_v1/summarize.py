"""Collect eight independent results, explicitly retaining incomplete runs."""
import csv
import os
import statistics
from settings import *


def main():
    args = arguments(__doc__).parse_args()
    validate(args)
    if args.dry_run:
        print(json.dumps(list(KEYS)))
        return
    if not os.environ.get('SLURM_JOB_ID'):
        raise ValueError('SLURM_REQUIRED')
    verify_plan()
    base = read(ROOT / 'baseline_test_score.json')
    statuses, rows, finished = {}, [], {}
    for key in KEYS:
        path = ROOT / key / 'TEST_RESULT.json'
        result = read(path) if path.exists() else None
        statuses[key] = result['status'] if result else 'NOT_SCORED'
        if result:
            with (ROOT / key / 'BEFORE_AFTER.csv').open() as stream:
                rows.extend(csv.DictReader(stream))
        if result and result['status'] == 'COMPLETE_HELDOUT_TEST':
            finished[key] = result
    if rows:
        with (ROOT / 'ALL_BEFORE_AFTER.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    lines = ['# Phase8：八个已完成训练模型的 held-out test', '',
             f'完整完成：{len(finished)}/8。每项 5,608 条，固定 test 1,124 个 underlying worlds。',
             '八项是四种训练方法 × 两个训练 seeds，基础模型均为 Qwen3.5-9B。Full PSS 不在本次八项之内。',
             '沿用历史 512-token retained-prefix 评分；没有 test 选优；解释 judge 未运行。', '',
             '| 模型/seed | 状态 | Overall ClaimAcc | Overall PairAcc |', '|---|---|---:|---:|',
             f'| Base Qwen3.5-9B | 同一 test 的历史预测 | {100*base["overall"]["claim_accuracy"]:.2f}% | {100*base["overall"]["pair_accuracy"]:.2f}% |']
    for key in KEYS:
        result = finished.get(key)
        values = [f'{100*result["overall"][m]:.2f}%' for m in ('claim_accuracy', 'pair_accuracy')] if result else ['待完成', '待完成']
        lines.append(f'| {key} | {statuses[key]} | ' + ' | '.join(values) + ' |')
    aggregated = {}
    for method in METHODS:
        members = [finished.get(f'{method}__seed_{seed}') for seed in TRAIN_SEEDS]
        if all(members):
            aggregated[method] = {}
            for level in ('L1', 'L2', 'L3', 'L4', 'Overall'):
                selected = [m['overall'] if level == 'Overall' else m['grouped']['level'][level] for m in members]
                aggregated[method][level] = {metric: dict(mean=statistics.mean(m[metric] for m in selected),
                       seed_sample_sd=statistics.stdev(m[metric] for m in selected), n_seeds=2)
                       for metric in ('claim_accuracy', 'pair_accuracy')}
    lines += ['', 'L1–L4 每项 ClaimAcc / PairAcc 和相对基线差值在 ALL_BEFORE_AFTER.csv；',
              '每模型 TEST_REPORT_CN.md、TEST_RESULT.json、RAW_PREDICTION_INDEX.json 保留完整证据。',
              '两个 seed 的均值/标准差在 SUMMARY.json；seed 标准差不是 world-level 置信区间。', '']
    write(ROOT / 'SUMMARY.json', dict(status='COMPLETE' if len(finished) == 8 else 'INCOMPLETE',
          complete=len(finished), expected=8, statuses=statuses, by_method=aggregated))
    (ROOT / 'TEST_SUMMARY_CN.md').write_text('\n'.join(lines))
    print(json.dumps(statuses), flush=True)


if __name__ == '__main__':
    main()
