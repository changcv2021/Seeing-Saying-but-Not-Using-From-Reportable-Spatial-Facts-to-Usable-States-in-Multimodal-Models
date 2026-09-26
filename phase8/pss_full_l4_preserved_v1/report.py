"""Fixed comparisons; never change inference or scoring based on outcomes."""
import csv
import statistics
from plan import *


def generate_report():
    results={}
    baseline=ROOT/'label_rescore_v2'
    keys=['base_qwen35_9b']+[f'{m}__seed_{s}' for m in ('answer_balanced','pss_l4','pss_full') for s in SEEDS]
    sources={k:baseline/k/'RESULT.json' for k in keys}
    sources.update({f'{METHOD}__seed_{s}':OUTPUT/'evaluation'/f'seed_{s}'/'label_rescore_v2'/f'{METHOD}__seed_{s}'/'RESULT.json' for s in SEEDS})
    missing=[str(p) for p in sources.values() if not p.exists()]
    if missing:
        print(json.dumps(dict(status='WAITING_FOR_BOTH_SEEDS_NOT_COMPLETE',missing=missing)));return
    for key,path in sources.items():
        r=read(path)
        if r['status']!='COMPLETE_VERSIONED_LABEL_RESCORING' or r['n']!=5608 or r['worlds']!=1124:
            raise ValueError('NOT_COMPLETE_SAME_TEST')
        if r['policy_version']!='observed_first_label_v2':raise ValueError('SCORING_CHANGED')
        results[key]=r
    levels=('L1','L2','L3','L4','Overall')
    def metric(key,level):return results[key]['overall']['corrected'] if level=='Overall' else results[key]['by_level'][level]['corrected']
    fields=('claim_accuracy','pair_accuracy')
    methods=('answer_balanced','pss_l4','pss_full',METHOD)
    stats={m:{l:{f:dict(mean=statistics.mean(metric(f'{m}__seed_{s}',l)[f] for s in SEEDS),
        sd=statistics.stdev(metric(f'{m}__seed_{s}',l)[f] for s in SEEDS)) for f in fields} for l in levels} for m in methods}
    lines=['# Preserved-L4 Full PSS：固定 test 结果报告','',
        '状态：两 seeds 的训练、实际 exposure 复核、完整 5,608 输入测试及 label_rescore_v2 评分完成。所有旧结果只读。','',
        '## 1. 每个 seed 与旧模型并列','',
        '每格为 ClaimAcc / PairAcc（%）。同一 test 1,124 worlds；UNKNOWN 保留在 ClaimAcc 分母，完整二元 pair 单独计算 PairAcc。','',
        '| 配置 / seed | L1 | L2 | L3 | L4 | Overall |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for key in results:
        lines.append('| '+key+' | '+' | '.join(f'{100*metric(key,l)["claim_accuracy"]:.2f} / {100*metric(key,l)["pair_accuracy"]:.2f}' for l in levels)+' |')
    lines+=['','## 2. 两 seed 均值与标准差','','± 是样本 SD，不是 world-clustered CI；不作未经检验的显著性宣称。','',
            '| 方法 | 层级 | ClaimAcc mean ± SD (%) | PairAcc mean ± SD (%) |','| --- | --- | ---: | ---: |']
    for m in methods:
        for l in levels:
            d=stats[m][l];lines.append(f'| {m} | {l} | {100*d["claim_accuracy"]["mean"]:.2f} ± {100*d["claim_accuracy"]["sd"]:.2f} | {100*d["pair_accuracy"]["mean"]:.2f} ± {100*d["pair_accuracy"]["sd"]:.2f} |')
    lines+=['','## 3. 三个研究问题','','### (1) 是否超过 PSS-L4？','',
            '按预定两个 seed 均值分别报告，不用最好 seed 或单一指标代替全部结果。','',
            '| 层级 | Δ ClaimAcc (pp) | Δ PairAcc (pp) |','| --- | ---: | ---: |']
    deltas={}
    for l in levels:
        d={f:100*(stats[METHOD][l][f]['mean']-stats['pss_l4'][l][f]['mean']) for f in fields}
        deltas[l]=d;lines.append(f'| {l} | {d["claim_accuracy"]:+.2f} | {d["pair_accuracy"]:+.2f} |')
    both=all(deltas[l][f]>0 for l in ('L4','Overall') for f in fields)
    lines+=['', 'L4 与 Overall 的两项主指标均提高。' if both else '不能概括为 L4 与 Overall 两指标一致超过 PSS-L4；差异方向以上表为准。', '',
        '### (2) 不稀释 L4 时，跨上下文监督是否有增益？','',
        '本实验可以检验“PSS-L4 原曝光 + 原 Full PSS 的 L1/L3 辅助监督”的整体添加效果。'+
        ('当前四项核心比较均为正向，属于该添加方案的行为证据。' if both else '当前结果不是一致正向的添加收益，必须保留无增益或负向的层级。'),
        '每条 L4 监督的次数、权重与原 seed 完全一致；但新增监督伴随更多 optimizer updates、额外 same-world answer exposures 和按新长度重算的 LR schedule。未加训练长度/额外答案等量对照，因此不能把差异单独归因于 alignment，也不能从行为分数推出内部机制。','',
        '### (3) 下降发生在哪些 level / label type？','',
        '按真值标签分组的 ClaimAcc 等于该类别 recall；未解析回答计错。下表为新方法均值减 PSS-L4 均值（pp），负值为下降。','',
        '| 层级 | SUPPORTED | CONTRADICTORY | UNKNOWN |','| --- | ---: | ---: | ---: |']
    label_deltas={}
    for l in levels:
        parts=[];label_deltas[l]={}
        for label in ('SUPPORTED','CONTRADICTORY','UNKNOWN'):
            support=metric(f'{METHOD}__seed_{SEEDS[0]}',l)['per_label'][label]['support']
            delta=None if not support else 100*statistics.mean(metric(f'{METHOD}__seed_{s}',l)['per_label'][label]['recall']-metric(f'pss_l4__seed_{s}',l)['per_label'][label]['recall'] for s in SEEDS)
            label_deltas[l][label]=delta;parts.append('N/A' if delta is None else f'{delta:+.2f}')
        lines.append('| '+l+' | '+' | '.join(parts)+' |')
    declines=[(v,l,label) for l,d in label_deltas.items() if l!='Overall' for label,v in d.items() if v is not None and v<0]
    if declines:
        lines+=['','负向类别按百分点降幅排序：'+ '；'.join(f'{l}/{label} {v:+.2f} pp' for v,l,label in sorted(declines))+ '。这描述分数位置，不预断因果。']
    else:lines+=['','未观察到各层真值标签分组 ClaimAcc 的均值下降；PairAcc 与接口仍需分别读取。']
    lines+=['','## 4. 输出接口与证据','','| 配置 | 可识别标签 | 未识别（计错） | 完整 schema |','| --- | ---: | ---: | ---: |']
    for k,r in results.items():
        d=r['diagnostics'];lines.append(f'| {k} | {d["label_identified_v2"]}/5608 | {r["unresolved"]} | {d["complete_schema_valid"]}/5608 |')
    lines+=['','只恢复已完整输出且无歧义的 label，不补 gold/解释或 JSON；使用旧已冻结 label_rescore_v2，不据当前 test 扩展解析规则。解释 judge 未运行，不记零分。', '',
            '训练前审计：audit/DATASET_EXPOSURE_AUDIT_CN.md；逐 key exposure：audit/EXPOSURE_AUDIT.json；训练后复核：seed_<seed>/ACTUAL_EXPOSURE_CONFIRMED.json；原始响应：evaluation/seed_<seed>/<model_key>/full/；逐条新旧评分与 label audit：evaluation/seed_<seed>/label_rescore_v2/<model_key>/。','',
            '本次结果仅回答冻结方案；不自动改 test、提示、评分、checkpoint 或增开调参实验。']
    output=OUTPUT/'final_report'
    if (output/'REPORT_CN.md').exists():return
    output.mkdir(exist_ok=True)
    write(output/'SUMMARY.json',dict(status='COMPLETE',methods=stats,deltas_vs_pss_l4=deltas,
        label_recall_deltas_pp=label_deltas,sources={str(p):sha(p) for p in sources.values()},
        test_n=5608,test_worlds=1124,scoring_policy='observed_first_label_v2',seed_sd_not_ci=True))
    with (output/'ALL_MODEL_LEVEL_SCORES.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['model','level','n','pairs','claim_accuracy','pair_accuracy',
            'supported_recall','contradictory_recall','unknown_recall','unknown_f1'])
        writer.writeheader()
        for key in results:
            for l in levels:
                a=metric(key,l)
                writer.writerow(dict(model=key,level=l,n=a['n'],pairs=a['complete_pairs'],
                    claim_accuracy=a['claim_accuracy'],pair_accuracy=a['pair_accuracy'],
                    supported_recall=a['per_label']['SUPPORTED']['recall'],contradictory_recall=a['per_label']['CONTRADICTORY']['recall'],
                    unknown_recall=a['per_label']['UNKNOWN']['recall'] if a['per_label']['UNKNOWN']['support'] else None,unknown_f1=a['unknown_f1']))
    (output/'REPORT_CN.md').write_text('\n'.join(lines)+'\n')
    print('COMPLETE_REPORT',output,flush=True)


def main():
    import fcntl
    with (OUTPUT/'REPORT.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        generate_report()


if __name__=='__main__':main()
