"""Combine all ten held-out results without changing the original eight reports."""
import csv
import os
import statistics
from full_common import *


def main():
    args = parser(__doc__).parse_args()
    validate(args)
    if args.dry_run:
        print('TEN_MODEL_PRIMARY_SCORE_SUMMARY_ONLY')
        return
    if not os.environ.get('SLURM_JOB_ID'):
        raise ValueError('SLURM_REQUIRED')
    verify_extension()
    previous.verify_plan()
    directories = {k: EIGHT_ROOT / k for k in previous.KEYS}
    directories.update({key(s): ROOT / f'seed_{s}' / key(s) for s in SEEDS})
    base = read(EIGHT_ROOT / 'baseline_test_score.json')
    records, statuses, completed = [], {}, {}
    for k, directory in directories.items():
        path = directory / 'TEST_RESULT.json'
        result = read(path) if path.exists() else None
        statuses[k] = result['status'] if result else 'NOT_SCORED'
        if result and result['status'] == 'COMPLETE_HELDOUT_TEST':
            completed[k] = result
        table = directory / 'BEFORE_AFTER.csv'
        if table.exists():
            with table.open() as stream:
                records.extend(csv.DictReader(stream))
    if records:
        with (ROOT / 'ALL_TEN_BEFORE_AFTER.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    aggregate = {}
    for method in (*previous.METHODS, 'pss_full'):
        members = [completed.get(f'{method}__seed_{s}') for s in SEEDS]
        if all(members):
            aggregate[method] = {}
            for level in ('L1', 'L2', 'L3', 'L4', 'Overall'):
                rows = [r['overall'] if level == 'Overall' else r['grouped']['level'][level] for r in members]
                aggregate[method][level] = {m: dict(mean=statistics.mean(r[m] for r in rows),
                    seed_sample_sd=statistics.stdev(r[m] for r in rows), n_seeds=2)
                    for m in ('claim_accuracy', 'pair_accuracy')}
    lines = ['# Phase8 十项训练后的 held-out test 汇总', '',
             f'完整完成 {len(completed)}/10。每项 test 5,608 输入 / 1,124 worlds；不混入 train/dev。',
             '同一 Qwen3.5-9B base，五方法 × 两训练 seeds；固定最终 step 2237，512-token retained-prefix 评分。',
             '未完成项不作为最终方法结果；解释 judge 未运行，不填零分。', '',
             '| 方法/seed | 状态 | ClaimAcc | PairAcc |', '|---|---|---:|---:|',
             f'| Base，同一 test | 历史预测 | {100*base["overall"]["claim_accuracy"]:.2f}% | {100*base["overall"]["pair_accuracy"]:.2f}% |']
    for k in directories:
        result = completed.get(k)
        values = [f'{100*result["overall"][m]:.2f}%' for m in ('claim_accuracy', 'pair_accuracy')] if result else ['待完成', '待完成']
        lines.append(f'| {k} | {statuses[k]} | ' + ' | '.join(values) + ' |')
    lines += ['', 'L1–L4/Overall 每级 ClaimAcc、PairAcc、相对基线差值见 ALL_TEN_BEFORE_AFTER.csv。',
              '逐项原始响应与模型加载/评分证据位于各模型目录；路径映射见 TEN_MODEL_SUMMARY.json。',
              '两个 seeds 的均值/样本标准差在 JSON 中；该标准差不是 world-level 置信区间。', '']
    write(ROOT / 'TEN_MODEL_SUMMARY.json', dict(status='COMPLETE' if len(completed) == 10 else 'INCOMPLETE',
          complete=len(completed), expected=10, statuses=statuses, by_method=aggregate,
          paths={k: str(v) for k, v in directories.items()}))
    (ROOT / 'TEN_MODEL_TEST_SUMMARY_CN.md').write_text('\n'.join(lines))
    print(json.dumps(statuses), flush=True)


if __name__ == '__main__':
    main()
