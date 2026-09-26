"""Collect CPU-stage outcomes without promoting submission/preflight to inference."""
import subprocess
from common import *

def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('CPU startup collector; does not submit GPU jobs or finalize the SWS study'); return
    artifacts={}
    for key,name in [('engineering','engineering_tests.json'),('sources','source_inventory.json'),('history','history_and_model_audit.json'),('E0','E0_snapshot_acceptance.json')]+[(m,'smoke_processor_'+m+'.json') for m in c['models']]:
        p=root/'reports'/name
        artifacts[key]=dict(path=str(p),available=p.exists(),report=load(p) if p.exists() else None)
    ids=['8178872','8178873','8178897','8178898','8178899','8178900','8178901','8178926','8178931','8178932']
    cmd=['sacct','-X','-nP','-j',','.join(ids),'--format=JobID,State,ExitCode,ElapsedRaw,AllocTRES,NodeList']
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
    save(root/'scheduler/startup_accounting.json',dict(command=cmd,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,timestamp=now()))
    estimate=root/'scheduler/resource_estimate_initial.json'
    save(root/'manifest/RESOURCE_PLAN_INITIAL.json',dict(**c['resources'],run_id=c['run_id'],
        site_snapshot=str(root/'scheduler/site_snapshot.json'),disk_quota_snapshot=dict(filesystem='external/project',project_id=12886,used='3.145 TiB',hard_limit='30 TiB',verified_at='2026-09-09T09:24_LOCAL_APPROX'),
        actual_new_gpu_hours=0,empirical_prior_estimate=load(estimate) if estimate.exists() else None,
        resource_budget_is_not_granted_by_this_file=True,legacy_B0_24h_does_not_authorize_SWS=True,
        conditional_submission_rule='EACH_REVIEWED_FROZEN_BATCH_PER_MODEL_SMOKE_PASS_AND_BUDGET_AVAILABLE; NO_CROSS_MODEL_BARRIER',
        whitebox_rule='M0_BEFORE_PATCH; DISCOVERY_VALIDATION_LOCK_BEFORE_C2',
        total_concurrency_scope='SWS_E_MODULES_M_MODULES_C1_C2_SHARE_ONE_LEDGER; E0_REUSES_EXISTING_CAMPAIGN_WITHOUT_NEW_ALLOCATION',
        outside_campaign_resources_must_be_requeried_before_GPU_wave=True))
    source=artifacts['sources']['report'] or {}
    authority=root/'scheduler/resource_authorization.json'
    authority_record=load(authority) if authority.exists() else None
    status=dict(run_id=c['run_id'],timestamp=now(),status='STARTUP_ONLY_PARTIAL_STUDY',execution='PARTIAL',measurement='NEW_REAL_INPUTS_NOT_VERIFIED',scientific='NOT_IDENTIFIABLE_NO_NEW_SWS_MODEL_OUTPUT',
        artifacts=artifacts,source_candidate_worlds=source.get('candidate_worlds'),human_verified_sws_real_worlds=0,
        E9_frozen_requests_per_model=768,smoke_frozen_requests_per_model=12,cpu_processor_requests=36,
        new_model_generations=0,new_gpu_jobs=0,gpu_budget='SEE_LATER_AUTHORIZATION_RECORD' if authority_record else 'WAIT_SINGLE_USER_ANSWER',
        authorization_record=authority_record,counts_scope='CPU_STARTUP_WAVE_ONLY_NOT_ANY_LATER_GPU_WAVE',
        full_final_review_zip='NOT_CREATED_STUDY_NOT_FINISHED',training_or_publication=False)
    save(root/'reports/startup_acceptance.json',status)
    text='''# SWS 启动阶段记录（不是最终研究报告）

当前执行 PARTIAL；新真实输入尚未 VERIFIED；没有新的 SWS 模型响应，因此不能报告机制结论。

已经按顺序完整阅读入口和主指南，源包保留。新命名空间独立于 release、Phase A/A.1/B0 和正在运行的完整 benchmark。

实际完成：33 项包内工具测试和 16 项新解析器/部分真值/符号编译测试通过；冻结 E9 的 24 个符号 world、每模型 768 请求；冻结三模型共同 smoke，每模型 12 请求（8 符号 + 4 个保持原题/媒体不变的旧 B0-A 请求）。三模型 CPU processor 实际运行共 36 请求。CPU processor 检查不等于模型推理，也不构成新媒体人工审核。

source_inventory.json 给出允许来源的原生事实盘点及缺口；它不是合格主样本清单，最终抽样仍需完整身份/媒体重复核对和派生输入审核。source graph 的 test 与旧 sealed confirmation 内容禁止用于新研究编译；已提交完整 benchmark 的 world 也按 exposed 处理，不重命名为新留出集。

history_and_model_audit.json 检查旧文件、三个模型 revision/config/shard 元数据和 B0 全部 raw 索引。E0_snapshot_acceptance.json 和 E0 表格只分析历史全量推理的定时快照，不新增 test 调用，不影响新样本选择；若预测未齐，不能当作最终 benchmark 得分。

资源：扩大后的 GPU 总预算尚待用户一次性答复，建议 500 GPU·小时只是待确认上限。旧 B0 的 24 GPU·小时不能继承。总 GPU 小时不等于单任务 wall time；没有新增 6 小时硬限制，按实测需要及 gpu 分区 48 小时站点上限分片。

未完成：新真实样本/模块提示/全部批次冻结，研究者审核，三模型 GPU smoke 与 E1–E9 实际推理，M0 hook 等价性、合格 M1/M2、C1/C2、主统计与第 23 节最终闭合回传 ZIP。没有将 queued/submitted 状态升级为实验完成。

启动失败均保留：Slurm spool 路径导致首次 CPU 启动失败；复用旧 protocol 时缺少项目 src 导入路径导致三份 CPU processor 失败。修复只改变启动路径/导入环境，没有修改媒体、请求、gold 或旧代码，也没有按答案重试。

下一步仅在已有明确预算后启动三个模型的独立 smoke 和旧审核任务 M0；合格新批次审核/冻结后按自身依赖提交。任何分支不具备条件时单独标记，不阻塞无关分支。最终完整研究尚未完成，当前不生成冒充完成的 REVIEW ZIP。
'''
    save(root/'reports/STARTUP_STATUS_CN.md',text,'text')
    # Code/guide snapshots are small. No copied media, caches or historical predictions here.
    snapshots=[entry(p) for p in sorted(CODE.glob('*')) if p.is_file()]
    snapshots.extend(entry(Path(c['package'])/x) for x in ['START_HERE_CODEX.md','SpaceConflict_Spatial_World_State_Study_CN.md','config/study.yaml','templates/RETURN_CONTRACT.json'])
    save(root/'manifest/startup_source_hashes.json',snapshots)
    print(json.dumps({k:status[k] for k in ['status','source_candidate_worlds','human_verified_sws_real_worlds','new_model_generations','gpu_budget']},ensure_ascii=False),flush=True)

if __name__=='__main__': main()
