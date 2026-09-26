"""Freeze behavioral-closure scope and statistics before new confirmation outputs."""
from bc_common import *

def main():
    a=cli(__doc__).parse_args();c,sws,out=context(a)
    if a.dry_run:print('Freeze Phase5 protocol, source roots, model set, and source-only C1 ranking.');return
    record=dict(run_id=RUN,created_at=now(),seed=c['seed'],guide=entry(GUIDE),
        protocol=entry(HERE.parent/'BEHAVIORAL_CLOSURE_PROTOCOL_v1_CN.md'),base_config=entry(BASE_CONFIG),
        root=str(out),read_only_sws_root=str(sws),models=c['models'],primary_model='qwen35_9b',
        sampling='ALL_SOURCE_READY_CANDIDATES_THAT_PASS_EXPOSURE_AND_MEDIA_OVERLAP_AUDIT; NO_MODEL_ERROR_SELECTION',
        C1='NEW_REGISTERED_HISTORY_UNEXPOSED_WORLDS_ONLY; SMALL_COUNT_COHORT_ALLOWED_WITH_EXPLICIT_LIMITS',
        hypotheses=['H1_CLAIM_PRESERVATION','H2_LICENSED_UPDATE','H3_BRANCH_RETENTION','H4_STATE_SELECTION'],
        conditional_H5='ONLY_IF_SOURCE_CERTIFIED_NONCOUNT_OR_MULTIVIEW_AVAILABLE',
        statistics=dict(unit='underlying_world',bootstrap_repetitions=5000,seed=c['seed'],confidence=.95,
            report=['numerator','denominator','worlds','estimate','ci95','invalid','null','not_run'],
            exploratory_and_confirmation_separate=True,significance='NO_SIGNIFICANCE_CLAIM_FROM_DISCOVERY_OR_CI_ALONE'),
        resources=dict(account='YOUR_ACCOUNT',qos='allocated',cpu_partition='general',gpu_partition='gpu',total_gpu_budget=None,
            per_job_walltime='MEASURED_NEED_WITHIN_SITE_LIMIT',exclusions=c['resources']['exclusions']),
        no_M2_C2_expansion=True,no_E0_regeneration=True,no_original_release_write=True,
        review_status='HUMAN_REVIEW_WAIVED_BY_RESEARCHER',grade='AUTO_ONLY_PROVISIONAL',job_id=os.environ['SLURM_JOB_ID'])
    save(out/'manifest/BEHAVIORAL_CLOSURE_LOCK.json',record)
    save(out/'scheduler/resource_authorization.json',dict(approved=True,models=c['models'],source='USER_DIRECT_MESSAGE_PHASE5_START',
        scopes=['CPU_EVIDENCE_CLOSURE','SOURCE_RECONSTRUCTION','QUALIFIED_FROZEN_BEHAVIORAL_INFERENCE'],no_M2_C2=True))
    save(out/'README_CN.md','# Phase5 行为证据闭合\n\n本目录保存 bc_20260910_v1 新工作。旧 SWS 数据与结果只读。\n\nP1_E2、P2_E5、P3_E8 为逐 world 分析；P4_C1 为历史曝光核查；P5/P6/P7 为源证据盘点。batches 保存获资格并冻结的新推理。\n\n当前是进行中的工作目录，不是最终 REVIEW 包。\n','text')
    print('BEHAVIORAL_CLOSURE_PROTOCOL_FROZEN',flush=True)

if __name__=='__main__':main()
