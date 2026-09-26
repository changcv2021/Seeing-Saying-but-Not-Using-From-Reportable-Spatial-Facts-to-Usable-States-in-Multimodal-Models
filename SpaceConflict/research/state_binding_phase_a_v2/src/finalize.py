"""Post-execution integrity, accounting and A5 report, then stop (no submissions)."""
import subprocess
from datetime import datetime, timezone
from base import *
from request_identity import execution_identity
from accounting import summarize


def verify_raw(root, model, request, raw, model_info, cfg, plan):
    """A missing/corrupt evidence file is a recorded failure, never a silent skip."""
    rid = request['request_id']
    rendered = load(root/'rendered/discovery'/model/(rid+'.json'))
    prompt_hash = hashlib.sha256(rendered['rendered_prompt'].encode()).hexdigest()
    pixels = digest(rendered['visual'])
    actual_key = execution_identity(model_info['revision'],request,cfg,pixels,prompt_hash)
    env = load(raw['environment_path'])
    ok = prompt_hash == raw['rendered_prompt_sha256'] == rendered['rendered_prompt_sha256'] and pixels == raw['presentation_hash'] and actual_key == raw['execution_key']
    ok = ok and sha(raw['environment_path']) == raw['environment_sha256'] and env['request_manifest_sha256'] == plan['input_hash']
    ok = ok and env['model']['revision'] == model_info['revision'] and raw['output_tokens'] <= cfg['max_new_tokens'] and not env['effective_mode']['enable_thinking']
    if not ok: raise ValueError('HASH_OR_MODE_MISMATCH')
    return dict(model=model,rendered_prompt_sha256=prompt_hash,presentation_hash=pixels)


def main():
    a=args(__doc__).parse_args(); cfg,root,project=setup(a)
    if a.dry_run: print(json.dumps(dict(status='PLANNED',action='finalize_and_stop'))); return
    checks=[]; by_request={}; requests=list(rows(root/'inputs/discovery/requests.jsonl')) if (root/'inputs/discovery/requests.jsonl').exists() else []
    tests=subprocess.run([sys.executable,'-m','unittest','discover','-v','-s',str(CODE/'tests')],capture_output=True,text=True)
    write(root/'reports/final_scorer_tests.json',dict(status='PASS' if not tests.returncode else 'FAIL',stdout=tests.stdout,stderr=tests.stderr,returncode=tests.returncode))
    checks.append(dict(check='final_scorer_unit_and_synthetic_fixture_tests',status='PASS' if not tests.returncode else 'FAIL',evidence='reports/final_scorer_tests.json'))
    extra=root/'manifest/discovery_additional_dependency_hashes.json'
    if extra.exists():
        for d in load(extra)['dependencies']:
            checks.append(dict(check='dependency_unchanged:'+d['path'],status='PASS' if Path(d['path']).is_file() and sha(d['path'])==d['sha256'] else 'FAIL',evidence=str(extra)))
    plan=load(root/'manifest/discovery/request_plan.json') if requests else {}
    model_cfg={m['key']:m for m in load(Path(cfg['campaign'])/'config.json')['models']}
    for model in cfg['models']:
        expected=[r for r in requests if model in r['models']]; matched=0; failures=[]
        for request in expected:
            rid=request['request_id']; path=root/'raw/discovery'/model/(rid+'.json')
            if not path.exists(): continue
            try:
                r=load(path)
                if r.get('infrastructure_error'): raise ValueError('INFRASTRUCTURE_ERROR:'+r['infrastructure_error'])
                verified=verify_raw(root,model,request,r,model_cfg[model],cfg,plan)
                matched+=1
                by_request.setdefault(rid,[]).append(dict(**verified,raw_path=str(path),raw_sha256=sha(path)))
            except (OSError, ValueError, KeyError, TypeError) as error:
                failures.append(dict(request_id=rid,reason=type(error).__name__+':'+str(error),raw_path=str(path)))
        checks.append(dict(check='discovery_integrity:'+model,status='FAIL' if failures else 'PASS' if expected and matched==len(expected) else 'NOT_RUN',matched=matched,expected=len(expected),failures=failures))
    common_failures=[rid for rid,rs in by_request.items() if len({(r['rendered_prompt_sha256'],r['presentation_hash']) for r in rs})!=1]
    checks.append(dict(check='actual_shared_inputs_identical',status='FAIL' if common_failures else 'PASS' if requests and all(c['status']=='PASS' for c in checks) else 'NOT_RUN',mismatch_ids=common_failures))
    result=dict(status='PASS' if all(c['status']=='PASS' for c in checks) else 'FAIL' if any(c['status']=='FAIL' for c in checks) else 'NOT_RUN',checks=checks,
        request_count=len(requests),review='MACHINE_INTEGRITY_ONLY_DERIVED_HUMAN_REVIEW_PROVISIONAL',stop_after_report=True)
    write(root/'reports/discovery_execution_checks.json',result)
    write(root/'reports/discovery_actual_input_index.json',by_request)
    ledger=[]
    for name in ['minimal_measurement_jobs.json','full_smoke_jobs.json','discovery_jobs_cancelled_before_execution.json','discovery_jobs.json']:
        p=root/'manifest'/name
        if p.exists():
            data=load(p)
            records=data.get('jobs',[]) if isinstance(data,dict) else data
            ledger.extend(r for r in records if r.get('job_id'))
    ids=','.join(sorted({str(r['job_id']) for r in ledger},key=int))
    if ids:
        accounting=subprocess.run(['sacct','-j',ids,'-X','-n','-P','--format=JobIDRaw,State,ExitCode,ElapsedRaw,AllocCPUS,AllocTRES,NodeList'],capture_output=True,text=True)
        write(root/'reports/slurm_accounting.txt',accounting.stdout,'text')
        write(root/'reports/slurm_accounting_status.json',dict(returncode=accounting.returncode,stderr=accounting.stderr,job_ids=ids,
            note='Raw scheduler accounting, not token-generation timing; no jobs submitted by finalizer.'))
        allocation=summarize(accounting.stdout,ids.split(','))
        allocation['scheduler_query_returncode']=accounting.returncode
        allocation['authorized_gpu_hours']=cfg['resources']['authorized_gpu_hours']
        allocation['under_authorized_budget_so_far']=allocation['allocated_gpu_hours_to_query']<=cfg['resources']['authorized_gpu_hours']
        write(root/'reports/gpu_accounting_summary.json',allocation)
    from design_audit import audit
    audit(cfg,root)
    import report
    report.main()
    manifest=load(root/'run_manifest.json')
    write(root/'LIVE_STATUS.md','# Phase A 自动验收状态\n\n'+
        '报告生成时间（UTC）：'+datetime.now(timezone.utc).isoformat()+'；CPU job '+os.environ.get('SLURM_JOB_ID','N/A')+'。\n\n'+
        '状态：'+manifest['status']+'。提交不计为实验完成。\n\n'+
        '\n'.join('- '+c['model']+': '+str(c['completed'])+'/'+str(c['expected'])+'，'+c['status'] for c in manifest['completion'])+
        '\n\n详见 phase_a_report_cn.md、acceptance_checks.json 和 reports/gpu_accounting_summary.json。'+
        'COMPLETE_PROVISIONAL 仅表示冻结请求和报告完成，不表示所有科学设计条件或人工复核通过。\n\n'+
        '本程序不提交作业；不进入 Phase B、白盒、训练、确认集或正式 test 新实验。\n','text')
    if manifest['status']=='COMPLETE_PROVISIONAL':
        print(json.dumps(dict(status='COMPLETE_PROVISIONAL',phase='PHASE_A_ONLY',next_phase_started=False,report=str(root/'phase_a_report_cn.md'))))
    else:
        print(json.dumps(dict(status='PHASE_A_INCOMPLETE',phase='PHASE_A_ONLY',next_phase_started=False,report=str(root/'phase_a_report_cn.md'))))
        raise SystemExit(2)


if __name__=='__main__': main()
