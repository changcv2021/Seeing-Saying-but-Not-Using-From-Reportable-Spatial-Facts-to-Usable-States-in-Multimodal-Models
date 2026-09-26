"""Final authorized core freeze with membership, matched-group and history checks."""
import subprocess
from v3common import *


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run:
        print('PLANNED: validate authorized core panel and freeze; no inference')
        return
    compute()
    authorization=load(root/'resources/core_authorization.json')
    resource=load(root/'resources/resource_lock.json')
    assert authorization['approved'] and authorization['stage']=='core'
    assert authorization['run_id']==resource['run_id']==c['run_id']
    assert authorization['models']==c['models'] and authorization['max_allocated_gpu_hours']==24
    assert all(j['walltime']=='06:00:00' for j in authorization['jobs'])
    assert authorization['automatic_retries']==0 and not authorization['requeue']
    assert resource['jobs']==authorization['jobs']
    gpu=load(root/'reports/gpu_engineering.json')
    assert gpu['status']=='PASS'
    assert all(gpu['per_model'][m]['generated']==82 and gpu['per_model'][m]['infra']==0 for m in c['models'])
    check_entries(load(root/'manifest/precore_lock.json')['code'])
    tests=subprocess.run([sys.executable,'-m','unittest','test_v3','-v'],cwd=CODE,text=True,capture_output=True)
    if tests.returncode:
        save(root/'reports/core_launch_tests_failure.json',dict(returncode=tests.returncode,stdout=tests.stdout,stderr=tests.stderr))
        raise RuntimeError('FROZEN_RUNNER_SCORER_TEST_FAILURE')
    save(root/'reports/core_launch_tests.json',dict(status='PASS',stdout=tests.stdout,stderr=tests.stderr))
    protected=check_entries(list(rows(root/'manifest/history_before.jsonl')))
    cmd=[sys.executable,str(CODE/'freeze_v3.py'),'--config',str(a.config),'--run-id',a.run_id,'--seed',str(a.seed),'--resume']
    result=subprocess.run(cmd,text=True,capture_output=True,check=True)
    lock=load(root/'manifest/core_lock.json'); plan=load(root/'manifest/reviewed_core_plan.json')
    req=list(rows(root/'inputs/core/requests.jsonl')); gold=list(rows(root/'private_gold/core.jsonl'))
    ids=[r['request_id'] for r in req]
    assert ids==plan['request_ids'] and len(ids)==len(set(ids))==312
    assert [g['request_id'] for g in gold]==ids
    assert all(g['condition_eligible'] for g in gold)
    assert lock['review_sha256']==plan['review_sha256']
    assert lock['resource_authorization_sha256']==sha(root/'resources/core_authorization.json')
    matches=list(rows(root/'manifest/reviewed_matched_controls.jsonl'))
    assert len(matches)==192 and all(m['base_request_id'] in ids and m['control_request_id'] in ids for m in matches)
    for m in c['models']:
        probe=subprocess.run([sys.executable,str(CODE/'infer_v3.py'),'--config',str(a.config),'--run-id',a.run_id,
                              '--seed',str(a.seed),'--resume','--dry-run','--stage','core','--model',m],text=True,capture_output=True,check=True)
        assert json.loads(probe.stdout)['requests']==312
    files=lock['code']
    snapshot=[]
    for n,record in enumerate(files):
        source=Path(record['path']); target=root/'manifest/core_code_snapshot'/f'{n:03d}_{source.name}'
        save(target,source.read_text(),'text')
        assert sha(target)==record['sha256']
        snapshot.append(dict(original=record,copy=entry(target)))
    save(root/'manifest/core_code_snapshot_index.json',snapshot)
    save(root/'manifest/core_protocol_lock.json',dict(run_id=c['run_id'],scope='REVIEWED_A1_CORE_ONLY',
         generation=c['generation'],core_lock=entry(root/'manifest/core_lock.json'),
         resource_lock=entry(root/'resources/resource_lock.json'),authorization=entry(root/'resources/core_authorization.json'),
         processor_review=entry(root/'review/review_bundle_manifest.json'),model_inventory=entry(root/'current_state_inventory.json'),
         matched_controls=entry(root/'manifest/reviewed_matched_controls.jsonl'),
         world_selection='EXACT_REVIEWED_MEMBERSHIP_NO_SCORE_BASED_SELECTION',
         primary_model='qwen35_9b',bootstrap_repetitions=2000,seed=c['seed'],
         analysis_rules='User v3 guide sections 10-12; analysis code version locked separately before inspecting core responses',
         source_revision='CONTENT_ADDRESSED_SOURCE_SNAPSHOT_NO_GIT_COMMIT_CLAIM',stop_after_a1=True))
    acceptance=dict(status='PASS_AUTHORIZED_CORE_FROZEN',history_files_checked=protected,history_changed_files=[],
        requests_per_model=312,requests_total=936,worlds=12,l4_worlds=7,l1_worlds=5,matched_groups=192,
        core_generated=0,freeze_stdout=result.stdout,job_id=os.environ['SLURM_JOB_ID'])
    save(root/'reports/core_launch_acceptance.json',acceptance)
    live=load(root/'LIVE_STATUS.json')
    live.update(status='CORE_FROZEN_READY_FOR_SUBMISSION',core_budget_approved=True,core_max_allocated_gpu_hours=24,
                core_responses=0,updated_at_utc=now(),core_lock=str(root/'manifest/core_lock.json'))
    save(root/'LIVE_STATUS.json',live,frozen=False)
    print(json.dumps(acceptance),flush=True)


if __name__=='__main__': main()
