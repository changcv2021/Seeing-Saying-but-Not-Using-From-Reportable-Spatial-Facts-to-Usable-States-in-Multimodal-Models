"""Launch-only recovery; preserve all original B0 artifacts and frozen scientific content."""
import shutil
import subprocess
import ast
from b0common import *

ORIGINAL_CODE=CODE.parent/'spaceconflict_b0'
ORIGINAL_ROOT=Path('artifacts/model_results/spaceconflict_b0/b0_20260908_r1')


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('Preserve original B0; same requests, gold, model, parser and analysis; fix launch only.'); return
    compute(); prior=ORIGINAL_ROOT; original=load(ORIGINAL_CODE/'config.json')
    differences={k for k in set(c)|set(original) if c.get(k)!=original.get(k)}
    if differences!={'root','run_id'}: raise ValueError('SCIENTIFIC_CONFIGURATION_CHANGED')
    oldlock=load(prior/'manifest/core_lock.json'); check_entries(oldlock['code'])
    for path in ORIGINAL_CODE.glob('*.py'):
        if path.name in ['dispatch.py','publish.py']: continue
        if sha(path)!=sha(CODE/path.name): raise ValueError('FROZEN_SCIENTIFIC_CODE_CHANGED:'+path.name)
    for path in CODE.glob('*.py'): ast.parse(path.read_text(),filename=str(path))
    olddecision=load(prior/'B0_NEXT_STAGE_DECISION.json')
    if any(v['responses']!=0 or v['not_run']!=1424 for v in olddecision['counts'].values()):
        raise ValueError('RECOVERY_REQUIRES_ZERO_PRIOR_CORE_GENERATIONS')
    if (prior/'raw/core').exists() and any((prior/'raw/core').rglob('*.json')):
        raise ValueError('PRIOR_RAW_CORE_FOUND_REQUIRES_EXPLICIT_ATTEMPT_RECONCILIATION')
    evidence=[]
    for key,jid in [('qwen35_4b','8171351'),('qwen35_9b','8171352'),('qwen35_27b','8171353')]:
        log=prior/'logs'/f'core_{key}_{jid}.err'
        if 'CPU binding outside of job step allocation' not in log.read_text():
            raise ValueError('PRIOR_FAILURE_NOT_PROVEN_PRE_PYTHON_CPU_BIND')
        evidence.append(dict(model=key,failed_job=jid,error_log=entry(log),prior_model_generations=0))
    measurement=load(prior/'reports/resource_measurement.json')
    if measurement['status']!='PASS' or not all(x['estimated_within_6h'] for x in measurement['models']):
        raise ValueError('PRIOR_ACTUAL_RESOURCE_MEASUREMENT_NOT_PASS')
    for key in c['models']:
        comp=load(prior/'raw/smoke'/key/'completion.json'); check_entries([comp['responses_file']])
        raw=list(rows(comp['responses_file']['path']))
        if len(raw)!=8 or any(r.get('infrastructure_error') for r in raw): raise ValueError('SMOKE_NOT_REUSABLE')
    copied=[]
    def copy(name):
        source=prior/name; out=root/name; out.parent.mkdir(parents=True,exist_ok=True)
        before=entry(source)
        if out.exists():
            if sha(out)!=before['sha256']: raise ValueError('RECOVERY_COPY_CHANGED:'+name)
        else: shutil.copy2(source,out)
        after=entry(out)
        if after['sha256']!=before['sha256']: raise ValueError('COPY_HASH_MISMATCH')
        copied.append(dict(source=before,destination=after))
    names=['02_B0_PANEL_MANIFEST.jsonl','inputs/core/requests.jsonl','private_gold/core.jsonl',
        'manifest/matched_pairs.jsonl','manifest/build_summary.json','manifest/source_inventory.json','manifest/model_inventory.json',
        'manifest/analysis_rules.json','manifest/breadth_snapshot.json','reports/resource_measurement.json',
        'reports/native_extension_source_audit.json','review/processor_checks.csv','review/assistant_visual_inspection.json',
        'tables/not_applicable_offsets.csv','tables/source_eligibility_rejections.csv','tables/native_extension_source_audit.csv',
        'benchmark_breadth_inventory.csv','benchmark_breadth_analysis_plan.md','reports/breadth_read_rejections.csv']
    for name in names: copy(name)
    preflight=load(prior/'manifest/preflight_index.json')
    check_entries(preflight['files'])
    for key in c['models']: copy('preflight/'+key+'.jsonl')
    preflight['files']=[entry(root/'preflight'/f'{key}.jsonl') for key in c['models']]
    preflight['reused_from']=entry(prior/'manifest/preflight_index.json')
    save(root/'manifest/preflight_index.json',preflight)
    if sha(root/'inputs/core/requests.jsonl')!=oldlock['inputs_sha256'] or sha(root/'private_gold/core.jsonl')!=oldlock['private_gold_sha256']:
        raise ValueError('FROZEN_REQUESTS_OR_GOLD_CHANGED')
    protected={r['path']:r for r in rows(prior/'manifest/history_before.jsonl')}
    for path in sorted(prior.rglob('*')):
        if path.is_file(): protected[str(path)]=entry(path)
    save(root/'manifest/history_before.jsonl',list(protected.values()),'jsonl')
    authorized=load(prior/'resources/core_authorization.json')
    authorized.update(run_id=c['run_id'],source_authorization=entry(prior/'resources/core_authorization.json'),
        recovery_authority='User requested 继续工作 after the B0 job chain; launch-only recovery within prior authorized resource ceiling.',
        failed_slurm_launches_are_not_model_attempts=True)
    save(root/'resources/core_authorization.json',authorized)
    save(root/'resources/gpu_smoke_submissions.json',dict(load(prior/'resources/gpu_smoke_submissions.json'),
        reused_read_only_from=str(prior),new_smoke_inference_calls=0))
    test=subprocess.run([sys.executable,'-m','unittest','-v','test_b0'],capture_output=True,text=True)
    save(root/'reports'/f'recovery_tests_{os.environ["SLURM_JOB_ID"]}.json',dict(returncode=test.returncode,
        stdout=test.stdout,stderr=test.stderr,affinity=sorted(os.sched_getaffinity(0)),
        cpu_bind=os.environ.get('SLURM_CPU_BIND'),job_id=os.environ['SLURM_JOB_ID']))
    if test.returncode: raise ValueError('RECOVERY_ENGINEERING_TEST_FAILED')
    lineage=dict(status='LAUNCH_REPAIR_READY_NOT_EXPERIMENT_COMPLETE',source_run=original['run_id'],recovery_run=c['run_id'],
        prior_core_lock=entry(prior/'manifest/core_lock.json'),prior_partial_report=entry(prior/'00_B0_REPORT_CN.md'),
        reason='sbatch invoked from a CPU srun inherited explicit CPU binding for a different allocation; three core Python processes never started.',
        fixes=['New versioned launcher clears inherited CPU/memory binding and sets srun --cpu-bind=cores.',
               'New dispatcher sanitizes binding variables in child sbatch environment.'],
        copied_files=copied,prior_launch_failures=evidence,reused_smoke_responses=24,new_smoke_generations=0,
        core_request_ids_payload_order_gold_byte_identical=True,scientific_config_changes=[],
        parser_inference_analysis_byte_identical=True,prior_b0_files_preserved=True,
        generated_responses_not_selected_or_retried=True,stop_after_b0=True)
    save(root/'reports/launch_recovery_manifest.json',lineage)
    files=dependency_files(c)+[entry(Path(c['campaign'])/'config.json')]
    for record in files:
        path=Path(record['path']); save(root/'code_snapshot'/(digest(str(path))[:10]+'_'+path.name),path.read_text(),'text')
    lock=dict(oldlock,run_id=c['run_id'],frozen_at_utc=now(),config_sha256=sha(a.config),code=files,
        preflight=entry(root/'manifest/preflight_index.json'),resource_measurement=entry(root/'reports/resource_measurement.json'),
        source_inventory=entry(root/'manifest/source_inventory.json'),history_baseline=entry(root/'manifest/history_before.jsonl'),
        assistant_render_inspection=entry(root/'review/assistant_visual_inspection.json'),
        launch_recovery=entry(root/'reports/launch_recovery_manifest.json'),parent_protocol_lock=entry(prior/'manifest/core_lock.json'),
        request_metadata_run_id_is_parent=True)
    save(root/'manifest/core_lock.json',lock); save(root/'01_B0_PROTOCOL_LOCK.json',lock)
    readme='# B0 启动修复续跑（非新实验设计）\n\n'
    readme+='原 B0 的 24 条 smoke 已实际完成；三个 core Slurm 作业在 Python 启动前因继承的 CPU 绑定失败，未产生核心回答。原 0 响应的 PARTIAL 报告及全部原文件保留，不冒充完成，也不覆盖。\n\n'
    readme+='本目录复用原先冻结的 1,424 条/模型请求，世界、顺序、提示、gold、解析器、统计规则和模型设置不变；请求中的原 run_id 保留用于溯源。只有输出 namespace 与 Slurm 启动/提交绑定处理变更。原失败是分配启动失败，不是按成绩重试模型。\n\n'
    readme+='实际工程差异与复制 hash 见 reports/launch_recovery_manifest.json。原 24 条 smoke 仍在 '+str(prior/'raw/smoke')+'，未重复语义测试。最终核心响应和验收状态以本目录为准。\n\n'
    readme+='当前代码：'+str(CODE)+'；当前配置：'+str(a.config)+'。\n\nSTOP：B0 报告和决策完成后不启动白盒、训练或 confirmation/test。\n'
    save(root/'RECOVERY_README_CN.md',readme,'text')
    save(root/'LIVE_STATUS.json',dict(status='LAUNCH_REPAIR_CORE_FROZEN_READY',core_responses=0,
        planned_responses=lock['requests_total'],run_id=c['run_id'],old_outputs_preserved=True,stop_after_b0=True),frozen=False)
    print(json.dumps(dict(status='LAUNCH_REPAIR_PRECHECK_PASS',requests_per_model=lock['requests_per_model'],
        reused_smoke=24,core_generations=0,source_hash_unchanged=True)),flush=True)


if __name__=='__main__': main()
