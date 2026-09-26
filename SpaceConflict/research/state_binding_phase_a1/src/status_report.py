"""Honest interim A1 deliverables. Never labels queued jobs or pending review as completed science."""
import time
import subprocess
from collections import Counter,defaultdict
from common import *
from scorer import score

MATRIX_FIELDS=['model','world_id','level','state_dimension','source','operator','review_status',
 'PRE_gold','PRE_pred','PRE_correct','action_gold','action_pred','action_correct',
 'POST_gold','POST_pred','POST_correct','JOINT_PRE','JOINT_POST','joint_exact','joint_binding_pattern',
 'oracle_target_PRE_pred','oracle_target_POST_pred','target_flip_pair_correct','sham_correct',
 'distractor_replacement_tracking','verdict_target_match','verdict_other_state','verdict_neither_state',
 'interface_valid','failure_tags','notes','group_id','stratum','execution_status']

def main():
    a=arguments(__doc__).parse_args(); cfg,root=setup(a)
    if a.dry_run: print('PLANNED: interim report only; no mechanism conclusions invented'); return
    require_compute()
    registry=load(CODE/'jobs.json')
    accounting=subprocess.run(['sacct','-j',','.join(str(j['id']) for j in registry['jobs']),
        '--format=JobID,JobName,State,ExitCode,Elapsed,AllocCPUS,ReqMem,AllocTRES','-P'],text=True,capture_output=True,timeout=30)
    save(root/'reports/slurm_accounting_latest.txt',accounting.stdout+'\n'+accounting.stderr,'text')
    save(root/'slurm_jobs.json',registry)
    if any((root/'raw/core').glob('*/*.json')): raise ValueError('ACTUAL_CORE_OUTPUTS_REQUIRE_FULL_ANALYSIS_NOT_INTERIM_REPORT')
    old=Path(cfg['phase_a_root']); source_groups=list(rows(old/'manifest/discovery/state_group_manifest.jsonl'))
    gids={g['group_id'] for g in source_groups}; csvlevels=defaultdict(set)
    with Path(cfg['phase_a_csv']).open(newline='') as f:
        for r in csv.DictReader(f):
            if r['group_id'] in gids: csvlevels[r['group_id']].add(r['level'])
    for g in source_groups:
        if csvlevels[g['group_id']]!={g['original_level']}: raise ValueError('CSV_LEVEL_MISMATCH')
    candidatefile=root/'review/candidate_panel.jsonl'
    candidates={p['group_id']:p for p in rows(candidatefile)} if candidatefile.exists() else {}
    reviewfile=root/'derived_input_review.csv'
    if not reviewfile.exists():
        csvsave(reviewfile,[dict(group_id=g['group_id'],world_id=g['world_id'],level=g['original_level'],state_dimension=g['state_dimension'],
            review_status='PENDING_REVIEW',note='WAITING_FOR_SETUP_CALIBRATION_BEFORE_DERIVED_REVIEW') for g in source_groups])
    with reviewfile.open(newline='') as f: reviews={r['group_id']:r for r in csv.DictReader(f)}
    matrix=[]
    for model in cfg['models']:
        for g in source_groups:
            c=candidates.get(g['group_id'],{}); vals=c.get('values',{})
            row={k:None for k in MATRIX_FIELDS}
            row.update(model=model,world_id=g['world_id'],level=g['original_level'],state_dimension=g['state_dimension'],
                source=g['source'],operator=g['operator'],group_id=g['group_id'],review_status=reviews[g['group_id']]['review_status'],
                PRE_gold=vals.get('PRE'),POST_gold=vals.get('POST'),action_gold=c.get('action_expected'),
                stratum='L1_OBJECT_ARGUMENT_CONTROL' if g['original_level']=='L1' else 'L4_BINARY_RELATION_SECONDARY' if g['domain']['binary_degenerate'] else 'L4_COUNT_PRIMARY',
                failure_tags=['UNRESOLVED_NO_A1_MECHANISM_MEASUREMENTS'],execution_status='NOT_RUN',
                notes='No mechanism attribution. Pending derived-input review. L1 OBJECT_ARGUMENT is not PRE/POST; its PRE/POST fields are intentionally NA.')
            matrix.append(row)
    csvsave(root/'tables/a1_failure_matrix.csv',matrix,MATRIX_FIELDS)
    # This file is the verified scientific panel, not the unreviewed candidate list.
    save(root/'a1_panel_manifest.jsonl',[],'jsonl')
    inp=list(rows(root/'inputs/setup_v1/requests.jsonl')); gold={r['request_id']:r for r in rows(root/'gold/setup_v1.jsonl')}
    records=[]; idx=[]
    for model in cfg['models']:
        for r in inp:
            p=root/'raw/setup_v1'/model/(r['request_id']+'.json'); raw=load(p) if p.exists() else None
            s=score(raw,gold[r['request_id']])
            records.append(dict(model=model,request_id=r['request_id'],condition=r['condition'],level='SETUP_ONLY',world_id=r['group_id'],**s))
            if raw is not None:
                idx.append(dict(stage='setup_v1',model=model,request_id=r['request_id'],**entry(p),
                    rendered_path=str(root/'rendered/setup_v1'/model/(r['request_id']+'.json')),presentation_hash=raw.get('presentation_hash')))
    save(root/'raw_predictions_index.jsonl',idx,'jsonl')
    if not (root/'setup_interface_calibration.csv').exists(): csvsave(root/'setup_interface_calibration.csv',records)
    gatepath=root/'reports/setup_calibration_acceptance.json'; gate=load(gatepath) if gatepath.exists() else {'status':'NOT_RUN'}
    engpath=root/'reports/engineering_acceptance.json'; eng=load(engpath) if engpath.exists() else {'status':'NOT_RUN'}
    pp=root/'review/processor_acceptance.json'; presentation=load(pp) if pp.exists() else {'status':'NOT_RUN'}
    if presentation['status']=='PASS': status='BLOCKED_ON_DERIVED_INPUT_REVIEW'
    elif gate['status']=='FAIL': status='SETUP_INTERFACE_FAILED_NO_REAL_WORLD_INFERENCE'
    elif gate['status']=='PASS': status='SETUP_PASSED_DERIVED_REVIEW_PREPARATION_PENDING'
    else: status='GPU_SETUP_PENDING_NOT_A1_COMPLETE'
    if any(k in accounting.stdout for k in ['|FAILED|','|TIMEOUT|','|OUT_OF_MEMORY|','|NODE_FAIL|']):
        status='INFRASTRUCTURE_OR_PREPARATION_FAILURE_A1_INCOMPLETE'
    validity=[]
    for model in cfg['models']:
        for condition in sorted({r['condition'] for r in records}):
            rr=[r for r in records if r['model']==model and r['condition']==condition and r['status']!='NOT_RUN']
            n=len(rr)
            validity.append(dict(model=model,level='SETUP_ONLY',condition=condition,requests=n,
                unique_synthetic_worlds=len({r['world_id'] for r in rr}),schema_valid=sum(r['schema_valid'] for r in rr) if n else None,
                schema_validity=sum(r['schema_valid'] for r in rr)/n if n else None,null=sum(r['status']=='NULL' for r in rr),
                invalid=sum(r['status']=='INVALID' for r in rr),status='OBSERVED_SETUP_ONLY' if n else 'NOT_RUN'))
    csvsave(root/'tables/schema_validity.csv',validity)
    for name in ['pre_action_post_summary','joint_state_summary','target_selection_summary','neither_state_claims','distractor_replacement']:
        csvsave(root/'tables'/f'{name}.csv',[dict(model=m,level=level,requests=0,worlds=0,estimate=None,ci95=None,status='NOT_RUN_NOT_ZERO_ACCURACY') for m in cfg['models'] for level in ['L4','L1']])
    acceptance=dict(status='INCOMPLETE',run_status=status,phase_a_preservation=load(root/'phase_a_preservation_check.json')['status'],
        engineering=eng['status'],setup_gate=gate['status'],actual_processor_presentation=presentation['status'],
        reviewed_verified_worlds=0,core_frozen=False,core_responses=0,stop_criteria_met=False,
        no_test_or_confirmation=True,no_whitebox_or_training=True,common_candidate_ids_not_outcome_selected=True)
    save(root/'reports/a1_acceptance.json',acceptance)
    decision=dict(status=status,primary_candidate='MIXED_UNRESOLVED_NOT_MEASURED',secondary_candidates=[],
        wrong_state_selection_support='UNRESOLVED',state_update_support='UNRESOLVED',comparison_gap_support='UNRESOLVED',
        interface_confound_remaining=True,verified_worlds=0,recommended_phase_b='NONE_BEFORE_A1_COMPLETE',
        reasons=['No verified real-world A1 core predictions yet. Submission is not experiment completion.',
                 'Finish setup and actual derived-input review before any primary attribution.'],
        excluded_competing_explanations=[],remaining_competing_explanations=['PRE fact report','action understanding','POST update','state selection/binding','claim comparison/acceptance','answer interface','input/query problems'],
        do_not_auto_execute=True)
    save(root/'next_stage_decision.json',decision)
    if not (root/'protocol_lock_a1.json').exists():
        save(root/'protocol_lock_a1.json',dict(status='SETUP_FROZEN_CORE_NOT_FROZEN',setup_lock_sha256=sha(root/'manifest/setup_v1_lock.json'),
            gate_pass=False,core_frozen=False,core_inference_authorized=False))
    bymodel={m:sum(r['model']==m for r in idx) for m in cfg['models']}
    report=f'''# SpaceConflict Phase A.1 阶段报告（未完成）

更新时间：{time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}。运行：`{cfg['run_id']}`。

**状态：{status}。这不是完成版 Phase A.1 科学结论。**

## 已完成与尚未完成

- Phase A 保护：{acceptance['phase_a_preservation']}；基线覆盖 4,362 个原运行／工程／指定 CSV 文件。旧 raw、gold、scorer、results 未静默重评分。
- 工程验收：{eng['status']}。纯合成 setup 已冻结，每模型 {len(inp)} 请求、14 个合成 world；不是 benchmark 机制 world。
- 已记录真实 setup raw 数：{json.dumps(bymodel)}。接口门槛：{gate['status']}。以完成文件和评分验收为准，不能用 Slurm 提交替代完成。
- 实际 processor 呈现复核包：{presentation['status']}。人工 VERIFIED world：0。真实 A1 核心推理：0 请求／0 world。
- 候选范围固定为旧 16 个已暴露 discovery world：7 个 L4 count 主候选、4 个 L4 二元 relation 次级、5 个 L1 OBJECT_ARGUMENT 低阶控制。依据指定 CSV 的 level 交叉核对；不按小模型错误挑选 27B。

## 主结论与不确定性

当前没有足够的新实验数据选择某一种机制 failure。`MIXED / UNRESOLVED` 在这里表示**尚未完成测量**，不是发现了混合因果机制。
最优先的是完成 A1 的接口和实际派生输入校准，不能据旧 FACT_SEPARATE/SELECT_VALUE 零分或二元 relation swaps 直接进入 wrong-state-selection 白盒研究。
PRE fact、action、POST update、selection/binding、comparison/acceptance、answer interface 和输入问题均未被本轮排除。

实验条件：本阶段已提交的推理作业仅限 setup-only explicit synthetic tables，greedy、thinking 关闭、512 新 token 上限；截断评分只用完整显式字段。主机制有效样本/world 分母均为 0，指标及 CI 必须 NA，不能写成 0% 或 [0,0]。

## 七个必答问题

1. 旧低分多少在简化接口后消失？尚未取得同 world 的新真实预测，不能量化；将来的配对 rescue/harm 也须区分接口和派生输入共同变化。
2. L4 在 PRE、action、POST 哪一步开始失败？暂无 VERIFIED L4 推理，不能定位。
3. JOINT exact 但 oracle target-select 错的 world 数？NA，未运行，不能报告为零。
4. 非退化错误是否跟随 non-target value？NA，匹配控制待执行；LEFT/RIGHT 不作为主要证据。
5. neither-state 是否仍被支持？NA；必须分别保留媒体版和 oracle-table 版。
6. 27B 与 4B/9B 差异来自何处？暂无三模型相同 VERIFIED world 的结果，不能归因于规模。
7. 下一阶段研究哪类 failure？暂不进入 Phase B。先补齐 A1 测量；没有竞争解释已被科学排除。

## 可追溯证据

- `manifest/phase_a_files_before.jsonl`、`phase_a_preservation_check.json`：原文件 SHA256 及比较结果。
- `manifest/setup_v1_lock.json`：接口／合成请求／gold／代码冻结；`reports/engineering_acceptance.json`：实际 CPU 验收。
- `setup_interface_calibration.csv`、`raw_predictions_index.jsonl`、`raw/setup_v1/`：真实输出，不存在的请求明确 NOT_RUN。
- `derived_input_review.csv`：未复核不能写 VERIFIED；实际呈现生成后见 `review/review_package/index.html`、`review/rendered_drafts_index.jsonl`。
- `tables/a1_failure_matrix.csv`：48 行模型×候选 world；此时只是完整保留候选的 NOT_RUN 台账，不是48项失败实测。
- `reports/a1_acceptance.json`、`next_stage_decision.json`：未满足 STOP 完成标准；不允许用本报告冒充已完成实验。

## 后续自动推进边界

已提交的依赖链：校准成功后生成全部候选派生 query 与实际 processor 呈现，然后刷新本报告。接口失败保留输出并停止于真实 world 之前。
新派生输入缺少具体复核时，只生成复核包并标 PENDING_REVIEW，不能继承原数据审核声明为本次人工复核，也不能凭 AI 猜测补 gold。
只有 VERIFIED 面板冻结并依据实测明确小规模预算后，才允许真实核心条件。未启动白盒、训练、confirmation、正式 test 或新增模型。
'''
    save(root/'phase_a1_report_cn.md',report,'text')
    save(root/'reproduce.md',(CODE/'reproduce.md').read_text(),'text')
    snap=root/'reports/status_snapshots'/('job_'+os.environ['SLURM_JOB_ID'])
    save(snap/'phase_a1_report_cn.md',report,'text',frozen=True); save(snap/'acceptance.json',acceptance,frozen=True)
    save(root/'LIVE_STATUS.json',dict(status=status,setup_actual_responses=bymodel,mechanism_responses=0,verified_worlds=0,complete=False))
    print(json.dumps(dict(status=status,setup_responses=bymodel,core_responses=0)))

if __name__=='__main__': main()
