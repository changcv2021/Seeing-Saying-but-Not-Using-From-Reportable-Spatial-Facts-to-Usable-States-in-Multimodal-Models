"""Snapshot report of measured evidence and explicit pending branches; no fake completion."""
from collections import defaultdict,Counter
from v2_common import *
def main():
    a=cli(__doc__).parse_args();context(a);dest=ROOT/'reports'/('snapshot_'+os.environ['SLURM_JOB_ID']);sources=[];summary=[];matched=[];index=[]
    for batch in ['W1_TARGET','NONCOUNT']:
        for model in MODELS:
            paths=sorted((ROOT/'batches'/batch/'scores'/model).glob('snapshot_*/DIAGNOSTIC_MATRIX.csv'))
            if not paths:
                summary.append(dict(batch=batch,model=model,status='NOT_YET_SCORED'));continue
            assert len(paths)==1,'AMBIGUOUS_SCORE_HISTORY_REQUIRES_EXPLICIT_SELECTION'
            p=paths[0];rs=csvrows(p);sources.append(entry(p))
            for r in rs:
                for k in ['prediction','expected']:
                    r[k]=json.loads(r[k]) if r[k] else None
                index.append(dict(batch=batch,model=model,request_id=r['request_id'],raw=json.loads(r['raw']) if r.get('raw') else None,status=r['status']))
            conditions=sorted({r['condition'] for r in rs});groups={condition:[r for r in rs if r['condition']==condition] for condition in conditions}
            for condition,group in groups.items():
                for subset in (['ALL','S1_NE_S2'] if batch=='W1_TARGET' else ['ALL']):
                    rr=[r for r in group if subset=='ALL' or r['s1']!=r['s2']]
                    values=[dict(world_cluster_id=r['program_family'] if batch=='W1_TARGET' else r['world_cluster_id'],value=int(r['correct']=='True')) for r in rr]
                    summary.append(dict(batch=batch,model=model,condition=condition,subset=subset,status='SCORED',planned=len(rr),returned=sum(r['status']=='RETURNED' for r in rr),
                        correct=sum(r['correct']=='True' for r in rr),invalid=sum(r['valid']=='False' for r in rr),null=sum(r['prediction']=={'value':None} for r in rr),
                        terminal_copy=sum(r['target_state']!='S2' and r['prediction'] is not None and str(r['prediction'].get('value'))==r['s2'] and r['s1']!=r['s2'] for r in rr),**cluster_ci(values)))
            if batch=='NONCOUNT':
                lookup={(r['world_cluster_id'],r['condition']):r for r in rs};worlds=sorted({r['world_cluster_id'] for r in rs})
                for right,left in [('EXPLICIT_S0','FULL_TRANSITION'),('MATCHED_SHAM','FULL_TRANSITION'),('EXPLICIT_S0','MATCHED_SHAM')]:
                    vals=[]
                    for w in worlds:
                        r,l=lookup[(w,right)],lookup[(w,left)]
                        if r['status']==l['status']=='RETURNED':vals.append(dict(world_cluster_id=w,value=int(r['correct']=='True')-int(l['correct']=='True')))
                    matched.append(dict(batch=batch,model=model,contrast=right+' - '+left,**cluster_ci(vals)))
                cohort=[]
                for w in worlds:
                    rr={cond:lookup[(w,cond)] for cond in conditions}
                    if rr['DIRECT_S0']['correct']=='True' and rr['FULL_TRANSITION']['correct']=='False':cohort.append(dict(world_cluster_id=w,value=int(rr['EXPLICIT_S0']['correct']=='True')))
                matched.append(dict(batch=batch,model=model,contrast='EXPLICIT_RESCUE_GIVEN_DIRECT_CORRECT_FULL_WRONG',**cluster_ci(cohort)))
    csvsave(dest/'BEHAVIOR_GROUP_RESULTS.csv',summary);csvsave(dest/'NONCOUNT_MATCHED_RESULTS.csv',matched);save(dest/'RAW_RESPONSE_INDEX.jsonl',index,'jsonl')
    w0=load(ROOT/'W0/ACCEPTANCE.json');i2=load(ROOT/'W2/I2_CLOSURE.json');sourcei2=ROOT/'W2/same_target_closure/CLOSURE.json'
    nexti2=load(sourcei2) if sourcei2.exists() else {'decision':'PENDING_SAME_TARGET_MATCHING'}
    branches={}
    for name,path in [('I1_TECHNICAL',ROOT/'I1/technical/qwen35_9b/TECHNICAL_ACCEPTANCE.json'),('I1_INPUT_AUDIT',ROOT/'I1/input_audit/ACCEPTANCE.json'),
        ('I1_CANDIDATES',ROOT/'I1/selection/CANDIDATE_LOCK.json'),('I1_SELECT',ROOT/'I1/selection/SELECT_DECISION.json'),('I2_TECHNICAL_REFRESH',ROOT/'W2/technical_followup/ACCEPTANCE.json')]:
        branches[name]=load(path) if path.exists() else {'status':'NOT_COMPLETED'}
    lines=['# SSM NextStage v2 执行与证据快照','',f'生成时间：{now()}。本文件是进行中快照，不是最终机制结论。',
        '',f'结果根目录：`{ROOT}`。历史 Phase A–6、release、gold、旧预测均未覆盖。',
        '', '## 已完成的历史证据整理','',f'- W0：{w0["rows"]} 个模型×序列病例，{w0["worlds"]} 个 world，三模型。',
        '- 9B：Type A 50 条、Type B 54 条、Type C 50 条、Type D 6 条；独立 S0 可报告不等于完整任务中已形成可操作内部状态。',
        f'- I2：主 384 条未重跑；Δlog P(CF)={i2["primary_delta_cf_lp"]["mean"]:.6f}，95% 家族聚类区间 [{i2["primary_delta_cf_lp"]["ci_low"]:.6f}, {i2["primary_delta_cf_lp"]["ci_high"]:.6f}]；10 个家族。',
        f'- 同目标匹配控制结论：`{nexti2["decision"]}`。未评分候选和 16 条技术缺项均单列；不把负结果推广为不存在任何状态表示。',
        '', '## 本轮行为结果','', '| 批次 | 模型 | 条件 | 子集 | 正确/计划 | 95% 聚类区间 |','| --- | --- | --- | --- | --- | --- |']
    for r in summary:
        if r['status']!='SCORED':lines.append(f'| {r["batch"]} | {r["model"]} | 未评分 | — | — | — |');continue
        lo,hi=r['ci_low'],r['ci_high'];ci=f'{lo:.3f}–{hi:.3f}' if lo is not None else 'N/A'
        lines.append(f'| {r["batch"]} | {r["model"]} | {r["condition"]} | {r["subset"]} | {r["correct"]}/{r["planned"]} | {ci} |')
    lines += ['', 'B2 区间按 16 个程序家族聚类；96 个程序不当作 96 个完全独立生成家族。全对/全错时经验 bootstrap 可退化为零宽，绝不代表总体成功率确定为 100%/0%。分数是冻结解析器的 typed exact match，null、无效和截断原文保留。S1=S2 的退化程序不能区分选择了哪一个状态。',
        '', '非计数控制为 47 个已使用过的来源 world：34 水平、6 垂直、7 深度。它们是单轴坐标框架反射后保持不变的行为控制，不是复杂物理运动、身份跟踪或正式留出验证。',
        '', '## I1 与后续分支','', '- 输入冻结：30 LOCALIZE Type A、20 SELECT Type A；Type B 分别34/20；成功控制28/22。同 world 两条序列不跨分区。',
        '- 9B 首轮网格：8 深度×4语义锚点×3 donor，LOCALIZE 上限 6,144 条干预。最多冻结2个候选窗口，再运行 SELECT、S0/保护事实/成功病例和反向干预。',
        '- 新 SELECT 是干预选择留出，而非未曝光确认集。所有这些来源 world 已有历史行为实验。',
        '- I3 尚未授权通过实验门槛：只有 I1 SELECT GO 后才评估组件定位；跨规模内部干预须先有机制锁。没有自动训练、全层扫描或新模型。',
        '', '当前分支状态：','', '```json',json.dumps({k:v.get('status',v.get('decision','RECORDED')) for k,v in branches.items()},ensure_ascii=False,indent=2),'```',
        '', '## 可复现入口','',f'代码：`{HERE}`。每个提交的完整 sbatch 命令、账户、资源、日志路径见结果根目录 `scheduler/*.json`。',
        'CPU 构建/汇总须在 Slurm 计算节点执行；launcher 仅做轻量校验和 sbatch 提交。不要在登录节点直接运行模型或统计脚本。',
        '', '证据文件：`BEHAVIOR_GROUP_RESULTS.csv`、`NONCOUNT_MATCHED_RESULTS.csv`、`RAW_RESPONSE_INDEX.jsonl`、`SOURCE_INDEX.json`；原始模型输出均保存在各批次 `raw/`。',
        '', '## 当前结论范围','', '现在只能分开讨论事实报告、初值利用、目标问法和技术接口。I1 未结束前不能断言内部瓶颈位置，更不能宣称干预修复已通过独立验证。最终精简回传 ZIP 在合格分支完成/明确停止后生成；本快照不冒充最终交付。']
    save(dest/'phase_v2_progress_report_cn.md','\n'.join(lines)+'\n','text')
    save(dest/'SOURCE_INDEX.json',dict(sources=sources,W0=entry(ROOT/'W0/ACCEPTANCE.json'),W2=entry(ROOT/'W2/I2_CLOSURE.json'),branches=branches,guide=entry(GUIDE)))
    print(str(dest/'phase_v2_progress_report_cn.md'),flush=True)
if __name__=='__main__':main()
