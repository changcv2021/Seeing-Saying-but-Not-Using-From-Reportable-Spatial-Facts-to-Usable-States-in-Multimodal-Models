"""Requeue only this incomplete run after a committed allocation-boundary stop."""
import argparse
import datetime
import os
import subprocess
import sys
from paths import *
from core import digest
from checkpoint import latest_checkpoint


def continuation_command(index):
    if type(index) is not int or index not in range(10): raise ValueError('ARRAY_INDEX')
    return ['sbatch','--parsable','--array='+str(index),str(RESOURCE_CODE/'train_array.sbatch')]


def main():
    compute()
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--index',type=int,required=True)
    args=parser.parse_args();command=continuation_command(args.index)
    sys.path.insert(0,str(RESOURCE_CODE))
    from resource_tools import load, prerequisites
    plan,runs=load();blocked=prerequisites(plan)
    if blocked: raise ValueError('CONTINUATION_NOT_READY:'+str(blocked))
    config=read(runs[args.index]['config']);runtime=read(config['runtime_manifest'])
    budget=read(runtime['budget_plan'])['runs'][config['run_id']]
    fingerprint=digest([runtime,config,budget]);output=Path(config['output_dir'])
    if (output/'TRAINING_COMPLETE.json').exists(): raise ValueError('DO_NOT_RESUBMIT_COMPLETED_RUN')
    attempt=output/'attempts'/os.environ['SLURM_JOB_ID']
    boundary=read(attempt/'CONTINUATION_REQUIRED.json')
    ckpt=latest_checkpoint(config['checkpoint_dir'],fingerprint)
    if (not ckpt or str(ckpt)!=boundary['checkpoint'] or boundary['fingerprint']!=fingerprint or
        boundary['step']>=budget['optimizer_updates'] or boundary['reason']!='SIGNAL_OR_ALLOCATION_END'):
        raise ValueError('NO_VALID_BOUNDARY_CHECKPOINT')
    # A failed/ambiguous submission is left for diagnosis, not blindly retried.
    write(attempt/'CONTINUATION_SUBMISSION_INTENT.json',dict(command=command,
        checkpoint=str(ckpt),step=boundary['step'],global_runtime_cap=None))
    submitted=subprocess.run(command,capture_output=True,text=True)
    if submitted.returncode:
        write(attempt/'CONTINUATION_SUBMISSION_FAILED.json',dict(code=submitted.returncode,stdout=submitted.stdout,stderr=submitted.stderr))
        raise RuntimeError('CONTINUATION_SUBMISSION_FAILED')
    job=submitted.stdout.strip().split(';')[0]
    if not job.isdigit(): raise ValueError('AMBIGUOUS_CONTINUATION_SUBMISSION:'+submitted.stdout)
    write(attempt/'CONTINUATION_SUBMITTED.json',dict(job_id=job,array_index=args.index,
        checkpoint=str(ckpt),step=boundary['step'],submitted_at=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    print('CONTINUATION_SUBMITTED',job,'index',args.index,flush=True)


if __name__=='__main__': main()

