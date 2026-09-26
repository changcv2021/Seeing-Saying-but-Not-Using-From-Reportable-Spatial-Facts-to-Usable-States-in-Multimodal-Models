"""Submit independent validated runs and checkpoint-only continuations."""
import argparse
import datetime
import os
import subprocess
from plan import *


def submit(command, intent, receipt):
    if intent.exists() or receipt.exists():raise FileExistsError('NO_DUPLICATE_SUBMISSION')
    intent.parent.mkdir(parents=True,exist_ok=True)
    intent.write_text(json.dumps(dict(command=command,time=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2)+'\n')
    r=subprocess.run(command,capture_output=True,text=True,check=True)
    job=r.stdout.strip().split(';')[0]
    if not job.isdigit():raise ValueError('AMBIGUOUS_SUBMISSION:'+r.stdout)
    receipt.write_text(json.dumps(dict(job_id=job,command=command,submitted_not_completed=True),indent=2)+'\n')
    print('SUBMITTED',job,flush=True)


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('action',choices=('admit','finish'))
    parser.add_argument('--index',type=int);args=parser.parse_args()
    from trainer import check_plan
    p=check_plan(OUTPUT)
    a=read(OUTPUT/'GPU_ACCEPTANCE.json')
    if a['status']!='PASS_TWO_GPU_ALL_METHODS_AND_FRESH_RESUME' or a['plan_sha256']!=sha(OUTPUT/'PLAN.json'):
        raise ValueError('TWO_GPU_ACCEPTANCE_REQUIRED')
    if args.action=='admit':
        submit(['sbatch','--parsable',str(HERE/'train_array.sbatch')],OUTPUT/'SUBMISSION_INTENT.json',OUTPUT/'SUBMITTED.json')
        return
    if args.index not in range(10):raise ValueError('ARRAY_INDEX')
    method=METHODS[args.index//2];seed=SEEDS[args.index%2]
    base=OUTPUT/'runs'/f'{method}__seed_{seed}'
    if (base/'TRAINING_COMPLETE.json').exists():return
    attempt=base/'attempts'/os.environ['SLURM_JOB_ID']
    boundary=read(attempt/'CONTINUATION_REQUIRED.json')
    if boundary['reason']!='SIGNAL_OR_ALLOCATION_END' or boundary['step']>=p['optimizer_updates']:
        raise ValueError('NO_CONTINUATION_AUTHORITY')
    from checkpoint_ddp import latest_checkpoint
    fingerprint=digest([sha(OUTPUT/'PLAN.json'),method,seed,'formal'])
    ckpt=latest_checkpoint(base/'checkpoints',fingerprint)
    if str(ckpt)!=boundary['checkpoint'] or boundary['fingerprint']!=fingerprint:raise ValueError('BOUNDARY_CHECKPOINT')
    submit(['sbatch','--parsable','--array='+str(args.index),str(HERE/'train_array.sbatch')],
        attempt/'CONTINUATION_SUBMISSION_INTENT.json',attempt/'CONTINUATION_SUBMITTED.json')


if __name__=='__main__':main()
