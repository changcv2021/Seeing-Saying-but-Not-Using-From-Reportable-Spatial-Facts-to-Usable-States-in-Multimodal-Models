"""CPU final integrity, reproducibility, and B0-only handoff. STOP afterwards."""
import io
import re
import shutil
import zipfile
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'spaceconflict_b0_launchfix_v1'))
from b0common import *


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('Validate and package B0 results only; no new inference'); return
    compute(); lock=load(root/'manifest/core_lock.json'); check_entries(lock['code'])
    protocol=load(root/'resources/gpu_retry_v2_protocol.json'); check_entries(protocol['guard_files'])
    if protocol['status']!='PASS' or sha(root/'manifest/core_lock.json')!=protocol['unchanged_core_lock_sha256']:
        raise ValueError('RETRY_PROTOCOL_INTEGRITY_FAILURE')
    submitted_retry=load(root/'resources/gpu_retry_v2_submissions.json')
    attempt_relative='resources/gpu_retry_v2/'+str(submitted_retry['qwen35_27b'])
    retry_attempt=load(root/attempt_relative/'attempt.json')
    retry_done=load(root/attempt_relative/'supervisor_status.json')
    if retry_done['status']!='COMPLETE' or retry_done['completed']!=lock['requests_per_model']:
        raise ValueError('RETRY_NOT_COMPLETE')
    protected=list(rows(root/'manifest/history_before.jsonl'))
    for offset in range(0,len(protected),500):
        check_entries(protected[offset:offset+500]); print(json.dumps(dict(history_rechecked=min(offset+500,len(protected)),total=len(protected))),flush=True)
    decision=load(root/'B0_NEXT_STAGE_DECISION.json')
    required=['00_B0_REPORT_CN.md','01_B0_PROTOCOL_LOCK.json','02_B0_PANEL_MANIFEST.jsonl','03_B0_RAW_RESPONSES_WITH_PROMPTS.csv',
              'benchmark_breadth_inventory.csv','benchmark_breadth_analysis_plan.md','future_whitebox_pair_candidates.jsonl','B0_NEXT_STAGE_DECISION.json']
    required+=['tables/'+name for name in ['b0_same_run_fact_verdict.csv','b0_claim_conditioned_fact.csv','b0_intervention_ablation.csv',
        'b0_numeric_offset_summary.csv','b0_missing_target_factorial.csv','b0_world_failure_matrix.csv','b0_model_summary.csv','b0_matched_controls.csv','b0_candidate_summary.csv']]
    missing=[name for name in required if not (root/name).is_file()]
    if missing: raise ValueError('MISSING_REQUIRED_B0_ARTIFACTS:'+json.dumps(missing))
    models={}
    for key in c['models']:
        path=root/'raw/core'/key/'completion.json'
        if path.exists():
            comp=load(path); check_entries([comp['responses_file']]); raw=list(rows(root/'raw/core'/key/'responses.jsonl'))
            if any(r['gold_access_audit']['private_gold_open_attempts'] or r['normal_attempt']!=1 or r.get('output_tokens',0)>512 for r in raw): raise ValueError('RUNTIME_PROTOCOL_VIOLATION')
            models[key]=dict(responses=len(raw),completion=entry(path))
        else: models[key]=dict(status='INCOMPLETE_NO_COMPLETION_RECORD')
    text='# B0 复现与来源\n\n本文件记录流程，不授权自动重跑模型。若重算分析，须用新的输出 namespace，不能覆盖已冻结结果。\n\n'
    text+='代码目录：'+str(CODE)+'\n\n结果目录：'+str(root)+'\n\n配置：config.json；种子 '+str(c['seed'])+'；完整代码文件 hash 与只读依赖在 01_B0_PROTOCOL_LOCK.json。code_snapshot/ 保留实际版本；本项目不是 Git worktree 时以文件 hash 为准，不虚构 commit。\n\n'
    text+='执行顺序：inventory → prepare → 三模型各一次 smoke → freeze → 三模型各一次 core → analyze；breadth 在来源选择后独立 CPU 执行；最后 publish。\n\n'
    text+='基础设施例外：27B 原作业 8173347 因 GPU Recovery Action=Reset 停止，未产生任何可保留回答。研究者明确要求在排除 nid0688 后重交一次；这是第二次物理执行、第一次保留回答，不是按答案效果重试。4B/9B 原有全部响应保持不变。恢复的实际命令见 resources/gpu_retry_v2_submissions.json，健康记录、超时保护与原事故证据随包保留。\n\n'
    text+='```bash\ncd "'+str(CODE)+'"\n'
    for action in ['inventory','prepare','freeze','breadth','analyze','publish']:
        text+='python '+action+'.py --config config.json --run-id '+c['run_id']+' --seed '+str(c['seed'])+' --resume --dry-run\n'
    text+='```\n\n实际计算须通过 job.sh 在 Slurm 分配中运行，不能在 login 节点执行大批量处理。资源和实际 job ID/命令见 resources/ 下各提交记录；core 每模型最多 6 小时，4B/9B 单卡、27B 双卡，提前完成即释放。\n\n'
    text+='新推理只读取 inputs/ 和经过金标准隔离的 model_inventory/preflight，不读 private_gold/。03 表包含 gold 供分析使用，不是模型输入。所有模型响应、无效输出、null 与 token ID 留在 raw/；聚合 JSONL 及其校验值方便完整重放评分。分组 CSV 不是重新采样的新实验。\n\n'
    text+='Phase A/A.1 只读。历史文件完整性重哈希并不把 sealed 内容用于选择、提示或分析；B0 只在许可的 dev/discovery world 上产生新请求。旧全量预测只在 breadth 盘点阶段用于可用性元数据，未进行新 test 推理。\n'
    save(root/'REPRODUCE.md',text,'text')
    resource_path=root/'reports/slurm_resource_usage.json'
    if not resource_path.exists():
        ids=set()
        for stage in ['smoke','core']:
            submitted=root/'resources'/f'gpu_{stage}_submissions.json'
            if submitted.exists():
                obj=load(submitted)
                ids.update(str(obj[k]) for k in c['models'] if k in obj)
        ids.add(str(submitted_retry['qwen35_27b']))
        cmd=['sacct','--parsable2','--noheader','--jobs',','.join(sorted(ids)),
             '--format=JobIDRaw,JobName,State,ExitCode,ElapsedRaw,AllocCPUS,ReqMem,AllocTRES,MaxRSS']
        usage=subprocess.run(cmd,capture_output=True,text=True,timeout=45) if ids else None
        save(resource_path,dict(command=cmd,returncode=usage.returncode if usage else None,
            stdout=usage.stdout if usage else '',stderr=usage.stderr if usage else '',
            status='SLURM_SNAPSHOT' if usage and usage.returncode==0 else 'UNAVAILABLE',read_at_utc=now()))
    acceptance=load(root/'reports/final_acceptance.json') if (root/'reports/final_acceptance.json').exists() else dict(status='PASS' if decision['execution_status']=='COMPLETE' else 'PARTIAL_NOT_FULLY_COMPLETE',
        run_id=c['run_id'],validated_at_utc=now(),historical_files_rechecked=len(protected),historical_changes=[],
        models=models,required_files_checked=len(required),code_lock_verified=True,private_gold_access_attempts=0,
        no_model_retries=False,no_answer_based_retries=True,infrastructure_retry_count=1,
        infrastructure_retry=retry_attempt,retry_protocol=entry(root/'resources/gpu_retry_v2_protocol.json'),
        no_whitebox_or_training=True,breadth_snapshot=entry(root/'manifest/breadth_snapshot.json'),
        limitations=['B0_B auto proof/processor qualification is not a new human review','Finite dev/discovery sample, not confirmation'],stop_after_b0=True)
    save(root/'reports/final_acceptance.json',acceptance)
    files=set(required+['REPRODUCE.md','reports/final_acceptance.json','review/processor_checks.csv','manifest/analysis_rules.json',
        'manifest/build_summary.json','manifest/source_inventory.json','manifest/breadth_snapshot.json','manifest/raw_response_index.json','reports/resource_measurement.json',
        'reports/native_extension_source_audit.json','review/assistant_visual_inspection.json','reports/slurm_resource_usage.json',
        'reports/launch_recovery_manifest.json','RECOVERY_README_CN.md'])
    files.update(['reports/27B_GPU_Incident_CN.md','reports/gpu_reset_incident_8173347.json',
        'reports/27B_Explicit_Retry_CN.md','resources/gpu_retry_v2_protocol.json',
        'resources/gpu_retry_v2_submissions.json'])
    files.update(str(p.relative_to(root)) for p in (root/attempt_relative).glob('*') if p.is_file())
    files.update(str(p.relative_to(root)) for p in (root/'tables').glob('*.csv'))
    for target in re.findall(r'\]\(([^)]+)\)',(root/'00_B0_REPORT_CN.md').read_text()):
        if not (root/target).is_file(): raise ValueError('BROKEN_REPORT_LINK:'+target)
    hashes=''.join(f'{sha(root/name)}  {name}\n' for name in sorted(files))
    save(root/'SHA256SUMS.txt',hashes,'text'); files.add('SHA256SUMS.txt')
    memory=io.BytesIO()
    with zipfile.ZipFile(memory,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in sorted(files): z.write(root/name,arcname=name)
    data=memory.getvalue(); archive=root/'SpaceConflict_B0_Decision_Package_20260908.zip'
    if archive.exists():
        if archive.read_bytes()!=data: raise ValueError('EXISTING_B0_PACKAGE_DIFFERS')
    else: archive.write_bytes(data)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None: raise ValueError('ZIP_INTEGRITY_FAILURE')
    destination=Path(c['phase3'])/('B0_results_'+c['run_id']); destination.mkdir(parents=True,exist_ok=True)
    for name in sorted(files|{archive.name}):
        source=root/name; out=destination/name
        out.parent.mkdir(parents=True,exist_ok=True)
        if out.exists() and sha(out)!=sha(source): raise ValueError('EXISTING_PHASE3_OUTPUT_PRESERVED')
        if not out.exists(): shutil.copy2(source,out)
    save(root/'reports/package_manifest.json',dict(archive=entry(archive),files=len(files),phase3_copy=str(destination),status='PASS'))
    save(root/'LIVE_STATUS.json',dict(status='COMPLETE_STOP_AFTER_B0' if acceptance['status']=='PASS' else 'PARTIAL_STOP_AFTER_B0',
        counts=decision['counts'],report=str(root/'00_B0_REPORT_CN.md'),decision=str(root/'B0_NEXT_STAGE_DECISION.json'),
        archive=str(archive),phase3=str(destination),acceptance=acceptance['status'],stop_after_b0=True),frozen=False)
    print(json.dumps(dict(status=acceptance['status'],archive=str(archive),phase3=str(destination),stop_after_b0=True)),flush=True)


if __name__=='__main__': main()
