"""CPU compile/import checks and immutable first-wave runtime lock; no semantic selection."""
import ast
import subprocess
import sys
from common import *

def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('Freeze SWS first GPU wave code/input hashes after engineering tests'); return
    assert load(root/'scheduler/resource_authorization.json')['approved']
    assert load(root/'reports/engineering_tests.json')['status']=='PASS'
    for name in ('gpu_worker_v1.py','freeze_gpu_v1.py'):
        ast.parse((CODE/name).read_text(),filename=name)
    p=Path(c['project']); a1=p/'research/state_binding_phase_a1/core_execution_v3'
    codes=[CODE/x for x in ('common.py','contracts.py','gpu_worker_v1.py','job_gpu_v1.sh','config.json')]
    codes += [a1/x for x in ('pipeline_v3.py','v3common.py')]
    codes += [p/'scripts/full_multimodel_split_v5/gpu_health.py',p/'src/spaceconflict/mllm_l4.py']
    codes += [Path(c['campaign'])/'code'/x for x in ('protocol.py','vision_process_frozen.py')]
    codes += [Path(c['campaign'])/'config.json']
    inputs=[root/'public_inputs/smoke/requests.jsonl',root/'public_inputs/E9/requests.jsonl',root/'manifest/smoke_request_lock.json',root/'manifest/E9_request_lock.json']
    for m in c['models']:
        report=load(root/'reports'/f'smoke_processor_{m}.json'); assert report['status']=='PASS'
        path=root/'review/smoke'/f'{m}_processor.jsonl'
        assert sha(path)==report['record_file']['sha256']; inputs.append(path)
    lock=dict(run_id=c['run_id'],status='READY_FOR_OWN_MODEL_SMOKE_THEN_E9',timestamp=now(),code=[entry(x) for x in codes],inputs=[entry(x) for x in inputs],
        authorization=entry(root/'scheduler/resource_authorization.json'),models=c['models'],unique_requests_per_model=772,
        stage_requests=dict(smoke=12,E9=768),smoke_E9_exact_request_overlap_reused=8,
        real_media_status='ONLY_4_UNCHANGED_PRIOR_REVIEWED_B0_A_TASKS_PER_MODEL_FOR_SMOKE_NOT_NEW_MAIN_STUDY',
        no_cross_model_dependencies=True,never_retry_null_wrong_or_invalid=True)
    save(root/'manifest/gpu_runtime_lock_v1.json',lock)
    checks=[]
    for m in c['models']:
        cmd=[sys.executable,'-B',str(CODE/'gpu_worker_v1.py'),'--model',m,'--dry-run']
        r=subprocess.run(cmd,capture_output=True,text=True); checks.append(dict(command=cmd,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr))
    result=dict(status='PASS' if all(x['returncode']==0 for x in checks) else 'FAIL',checks=checks,job_id=os.environ['SLURM_JOB_ID'],runtime_lock=entry(root/'manifest/gpu_runtime_lock_v1.json'))
    save(root/'reports/GPU_LAUNCH_PREFLIGHT_V1.json',result); print(json.dumps(result,ensure_ascii=False),flush=True)
    if result['status']!='PASS': raise SystemExit(2)

if __name__=='__main__': main()
