"""All planned trials, exact raw closure, family bootstrap; never select a mechanism."""
from collections import defaultdict,Counter
from common_i2 import *
def main():
    a=cli(__doc__).parse_args();c,out=setup_i2(a)
    if a.dry_run:print('Full-denominator LOCALIZE results, matched controls, uncertainty and not-run');return
    verify();lock=load(out/'manifest/LOCK.json')
    for ref in lock['private_inputs']:check(ref)
    gold={r['trial_id']:r for r in rows(out/'private_gold/trials.jsonl')};allrows=[];raw=[]
    for t in rows(out/'public_inputs/trials.jsonl'):
        g=gold[t['trial_id']];path=out/'raw/qwen35_9b'/f'shard_{t["shard"]:03}'/'trials'/(t['trial_id']+'.json')
        r=load(path) if path.exists() else {};norm=r.get('normalized',{}).get('normalized',{});valid=norm.get('status')=='VALID'
        pred=norm.get('component_values',{}).get('value');state=r.get('status','NOT_RUN')
        baseline=load(r['baseline_ref']['path']) if 'baseline_ref' in r else {};bn=baseline.get('normalized',{}).get('normalized',{})
        bvalue=bn.get('component_values',{}).get('value');bvalid=bn.get('status')=='VALID'
        row=dict(**t,**{k:v for k,v in g.items() if k not in t},execution_status=state,prediction=pred,normalized_status=norm.get('status'),
            returned=state=='RETURNED',cf_correct=valid and pred==g['expected_counterfactual'],primary_cf_match=valid and pred==g['primary_counterfactual'],
            original_correct=valid and pred==g['recipient_final_gold'],donor_final_copy=valid and pred==g['donor_final_gold'],donor_s1_copy=valid and pred==g['donor_s1'],
            baseline_prediction=bvalue,baseline_cf_match=bvalid and bvalue==g['expected_counterfactual'],
            changed_causal_eligible=state=='RETURNED' and not (bvalid and bvalue==g['expected_counterfactual']),
            null=valid and pred is None,invalid=state=='RETURNED' and not valid,raw_response=r.get('response',{}).get('raw_response'),
            truncated=r.get('response',{}).get('truncated'),raw_ref=entry(path) if path.exists() else None)
        allrows.append(row)
        if path.exists():raw.append(dict(record=r,gold=g,baseline=baseline,donor_baseline=load(r['donor_baseline_ref']['path'])))
    import numpy as np
    rng=np.random.default_rng(20260911)
    def estimate(values):
        # Pairs never cross families; resample the full donor/recipient dependence cluster.
        groups=defaultdict(list)
        for cluster,value in values:groups[cluster].append(float(value))
        if not groups:return dict(n=0,clusters=0,mean=None,ci_low=None,ci_high=None,uncertainty='NO_OBSERVATIONS')
        arrays=list(groups.values());sums=np.array([sum(v) for v in arrays]);ns=np.array([len(v) for v in arrays]);point=float(sums.sum()/ns.sum())
        if len(arrays)<2:return dict(n=int(ns.sum()),clusters=len(arrays),mean=point,ci_low=None,ci_high=None,uncertainty='ONE_FAMILY_NO_CLUSTER_CI')
        idx=rng.integers(0,len(arrays),size=(5000,len(arrays)));boots=sums[idx].sum(1)/ns[idx].sum(1);lo,hi=np.quantile(boots,[.025,.975])
        return dict(n=int(ns.sum()),clusters=len(arrays),mean=point,ci_low=float(lo),ci_high=float(hi),uncertainty='EXPLORATORY_FAMILY_BOOTSTRAP_5000; ZERO_WIDTH_NOT_CERTAINTY' if lo==hi else 'EXPLORATORY_FAMILY_BOOTSTRAP_5000')
    groups=defaultdict(list)
    for r in allrows:groups[(r['control'],r['anchor'],r['depth'])].append(r)
    stats=[]
    for key,rs in sorted(groups.items()):
        returned=[r for r in rs if r['returned']]
        for metric in ['cf_correct','primary_cf_match','baseline_cf_match','original_correct','donor_final_copy','donor_s1_copy','null','invalid']:
            stats.append(dict(control=key[0],anchor=key[1],depth=key[2],metric=metric,planned=len(rs),not_run=len(rs)-len(returned),
                **estimate([(r['cluster_id'],r[metric]) for r in returned])))
    controls=[];primary={(r['base_pair_id'],r['depth']):r for r in allrows if r['control']=='PRIMARY' and r['anchor']=='P_CHECKPOINT'}
    matched=defaultdict(list)
    for r in allrows:
        if r['control'] in ('PRIMARY','SAME_DONOR_DIFFERENT_A2'):continue
        pr=primary[(r['base_pair_id'],r['depth'])]
        if pr['returned'] and r['returned']:matched[(r['control'],r['depth'])].append((r['cluster_id'],int(pr['primary_cf_match'])-int(r['primary_cf_match'])))
    for (control,depth),values in sorted(matched.items()):controls.append(dict(control=control,depth=depth,metric='PRIMARY_CHECKPOINT_CF_MINUS_CONTROL_SAME_TARGET',**estimate(values)))
    dest=out/'reports'/('snapshot_'+os.environ['SLURM_JOB_ID'])
    csvsave(dest/'I2_DIAGNOSTIC_MATRIX.csv',allrows);csvsave(dest/'GROUP_RESULTS.csv',stats);csvsave(dest/'MATCHED_CONTROLS.csv',controls);save(dest/'ALL_RAW_RESPONSES.jsonl',raw,'jsonl')
    counts=Counter(r['execution_status'] for r in allrows)
    report=['# I2 状态互换：首轮 LOCALIZE 结果','',f'执行状态：{dict(counts)}。计划 {len(allrows)} 次干预。',
        '', '本轮仅为冻结 B2 符号程序的探索性实验，不是自然视觉空间机制确认。9B 为主模型；没有运行 SELECT/LOCKED_EVAL，没有根据效果锁定机制。',
        '', '逐样本表保留全部计划项、null、无效输出、引擎不等价与未运行。原始响应文件包含 recipient/donor baseline 全文。',
        '', '分组指标按固定层/锚点全部报告，置信区间按同一 donor/recipient 程序家族聚类。没有按成绩选择展示层。单家族不报告伪造区间；小家族数量和零宽 bootstrap 均不代表确定性。',
        '', '局限：缺少无关寄存器同值对照；同 S1/不同历史等缺项见 CONTROL_COVERAGE。晚层效应不能单独证明 S1，候选复制与原 baseline 恰好等于反事实均单列。',
        '', '完整因果解释需对照和后续冻结验证支持；本报告不自动启动组件定位、训练或留出实验。']
    save(dest/'i2_report_cn.md','\n'.join(report)+'\n','text')
    save(dest/'ACCEPTANCE.json',dict(execution='COMPLETE' if not counts['NOT_RUN'] else 'PARTIAL',counts=dict(counts),scientific_support='UNRESOLVED_PENDING_CONTROL_INTERPRETATION',
        all_planned_retained=True,primary_analysis='EXPLORATORY_LOCALIZE_ONLY',files=[entry(p) for p in dest.iterdir() if p.is_file()]))
    print(json.dumps(dict(report=str(dest),counts=counts)),flush=True)
if __name__=='__main__':main()
