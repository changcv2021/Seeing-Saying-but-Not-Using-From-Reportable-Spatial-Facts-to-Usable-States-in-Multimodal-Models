"""Seal the validated runtime and submit all ten independent training elements once."""
import argparse
import datetime
import os
import subprocess
import sys
from paths import *


def main():
    compute()
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--submit',action='store_true')
    args=parser.parse_args()
    validation=read(OUTPUT/'runtime_validation_v1/ACCEPTANCE.json')
    if validation['status']!='PASS_FULL_RESUME_AND_ALL_METHOD_INGRESS': raise ValueError('RESUME_NOT_ACCEPTED')
    if read(ROOT/'state_interface_repair_v2/gpu_validation/ACCEPTANCE.json')['status']!='PASS_STATE_INTERFACE_DEV_SMOKE':
        raise ValueError('STATE_INTERFACE_NOT_ACCEPTED')
    budget=PREPARED/'BUDGET_PLAN.json'
    if sha(budget)!=validation['budget_sha256']: raise ValueError('BUDGET_CHANGED_AFTER_VALIDATION')
    for path,value in validation['code_hashes'].items():
        if sha(path)!=value: raise ValueError('VALIDATED_CODE_CHANGED:'+path)
    sys.path.insert(0,str(RESOURCE_CODE))
    from resource_tools import load, prerequisites
    plan,runs=load()
    runtime=dict(status='FROZEN_AND_VALIDATED',entrypoint=str(HERE/'trainer.py'),
        entrypoint_sha256=sha(HERE/'trainer.py'),budget_plan=str(budget),budget_plan_sha256=sha(budget),
        resources_sha256=sha(RESOURCE_CODE/'resource_plan.json'),
        state_interface_version='state_interface_v2',state_interface_sha256=sha(ENGINE_CODE/'state_interface_v2.py'),
        resume_and_signal_handlers_validated=True,code_hashes=validation['code_hashes'],
        run_config_hashes={r['config']:sha(r['config']) for r in runs},
        resource_launcher_hashes={str(p):sha(p) for p in [RESOURCE_CODE/'resource_tools.py',RESOURCE_CODE/'train_array.sbatch']},
        validation_record=str(OUTPUT/'runtime_validation_v1/ACCEPTANCE.json'),
        validation_sha256=sha(OUTPUT/'runtime_validation_v1/ACCEPTANCE.json'),
        primary_checkpoint='FIXED_FINAL_BUDGET',test_scope='HELD_OUT_TEST_ONLY_AFTER_TRAINING',
        original_train_samples=13476,held_out_test_inputs=5608,
        formal_training_complete=False)
    target=OUTPUT/'TRAINING_RUNTIME.json'
    if target.exists():
        if read(target)!=runtime: raise ValueError('EXISTING_RUNTIME_DIFFERS')
    else: write(target,runtime)
    blocked=prerequisites(plan)
    if blocked: raise ValueError('ADMISSION_FAILED:'+str(blocked))
    write(OUTPUT/'RUNTIME_ACCEPTANCE.json',dict(status='PASS_READY_TO_SUBMIT_TEN_RUNS',
        budget_sha256=sha(budget),validation_sha256=runtime['validation_sha256'],job_id=os.environ['SLURM_JOB_ID']))
    if not args.submit: print('READY_NOT_SUBMITTED',flush=True);return
    command=['sbatch','--parsable',str(RESOURCE_CODE/'train_array.sbatch')]
    (OUTPUT/'logs').mkdir(exist_ok=True)
    write(OUTPUT/'SUBMISSION_INTENT.json',dict(command=command,array='0-9',dependencies=[],
        array_throttle=None,resources=plan['resources'],runtime_sha256=sha(target)))
    result=subprocess.run(command,capture_output=True,text=True)
    if result.returncode:
        write(OUTPUT/'SUBMISSION_FAILED.json',dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
        raise RuntimeError('FORMAL_SUBMISSION_FAILED')
    job=result.stdout.strip().split(';')[0]
    if not job.isdigit(): raise ValueError('AMBIGUOUS_SBATCH_RESULT:'+result.stdout)
    write(OUTPUT/'SUBMITTED.json',dict(array_job_id=job,array_indices=list(range(10)),
        submitted_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),runs=runs,
        formal_training_complete=False,all_seeds_reported=True))
    print('FORMAL_TEN_RUN_ARRAY_SUBMITTED',job,flush=True)


if __name__=='__main__': main()
