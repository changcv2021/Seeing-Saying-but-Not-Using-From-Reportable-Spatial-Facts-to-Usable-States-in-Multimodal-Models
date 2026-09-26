"""Real dependencies only; no cross-seed barrier or accuracy-based retries."""
import argparse
import datetime
import os
import re
import subprocess
from plan import *


def verify_freeze():
    frozen=read(OUTPUT/'FREEZE.json')
    for path,expected in frozen['code_hashes'].items():
        if sha(path)!=expected:raise ValueError('FROZEN_CODE_CHANGED:'+path)
    return frozen


def resource_check(gpu=False):
    partition='gpu' if gpu else 'general'
    r=subprocess.run(['sinfo','-h','-p',partition,'-o','%a %l %G'],capture_output=True,text=True,check=True)
    if not r.stdout.strip() or any(not line.startswith('up ') for line in r.stdout.splitlines()):
        raise ValueError('PARTITION_UNAVAILABLE:'+r.stdout)
    assoc=subprocess.run(['sacctmgr','-nP','show','assoc','where','user=anonymous','format=Account,QOS'],capture_output=True,text=True,check=True)
    if not any(line.startswith('YOUR_ACCOUNT|') and 'allocated' in line for line in assoc.stdout.splitlines()):
        raise ValueError('ALLOCATION_NOT_VISIBLE')
    if gpu:
        policy=(HERE.parents[1]/'dataset/GPU_NODE_AVOIDANCE.md').read_text()
        required=set()
        for match in re.findall(r'--exclude=([a-z0-9,]+)',policy):required.update(match.split(','))
        if not required.issubset(set(EXCLUDE.split(','))):raise ValueError('GPU_QUARANTINE_CHANGED')


def submit(command, tag):
    directory=OUTPUT/'submissions';directory.mkdir(exist_ok=True)
    intent=directory/(tag+'_INTENT.json');receipt=directory/(tag+'.json')
    if receipt.exists():return read(receipt)['job_id']
    if intent.exists():raise ValueError('AMBIGUOUS_SUBMISSION_REQUIRES_RECONCILIATION:'+tag)
    write(intent,dict(command=command,time=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    result=subprocess.run(command,capture_output=True,text=True,check=True)
    job=result.stdout.strip().split(';')[0]
    if not job.isdigit():raise ValueError('AMBIGUOUS_SBATCH_RESULT:'+result.stdout)
    write(receipt,dict(job_id=job,command=command,submitted_not_completed=True))
    print('SUBMITTED',tag,job,flush=True);return job


def cpu_command(name, stage, seed=None):
    command=['sbatch','--parsable','--partition=general','--account=YOUR_ACCOUNT','--qos=allocated',
        '--nodes=1','--ntasks=1','--cpus-per-task=2','--mem=16G','--time=01:00:00',
        '--job-name='+name,'--output='+str(OUTPUT/'logs'/(name+'_%j.out')),
        '--error='+str(OUTPUT/'logs'/(name+'_%j.err')),str(HERE/'job.sbatch'),stage]
    if seed is not None:command+=['--seed',str(seed)]
    return command


def submit_evaluation(seed):
    verify_freeze();resource_check(True)
    name='sc_preserved_test_'+str(seed)
    cmd=['sbatch','--parsable','--partition=gpu','--account=YOUR_ACCOUNT','--qos=allocated',
         '--nodes=1','--ntasks=1','--cpus-per-task=4','--mem=64G','--gpus-per-node=1',
         '--time=2-00:00:00','--array=0-3','--exclude='+EXCLUDE,'--job-name='+name,
         '--output='+str(OUTPUT/'logs'/(name+'_%A_%a.out')),'--error='+str(OUTPUT/'logs'/(name+'_%A_%a.err')),
         str(HERE/'job.sbatch'),'infer','--seed',str(seed)]
    inference=submit(cmd,'inference_'+str(seed))
    resource_check(False)
    score=cpu_command('sc_preserved_score_'+str(seed),'score',seed)
    score.insert(2,'--dependency=afterok:'+inference)
    submit(score,'score_'+str(seed))


def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('action',choices=('admit','finish'))
    parser.add_argument('--seed',type=int,choices=SEEDS);args=parser.parse_args();verify_freeze()
    if args.action=='admit':
        resource_check(True)
        submit(['sbatch','--parsable',str(HERE/'train_array.sbatch')],'training_two_seeds');return
    seed=args.seed
    if seed not in SEEDS:raise ValueError('SEED_REQUIRED')
    run=seed_output(seed)/'runs'/f'{METHOD}__seed_{seed}'
    if (run/'TRAINING_COMPLETE.json').exists():
        resource_check(False)
        submit(cpu_command('sc_preserved_finish_'+str(seed),'finish',seed),'finish_'+str(seed));return
    attempt=run/'attempts'/os.environ['SLURM_JOB_ID']
    boundary=read(attempt/'CONTINUATION_REQUIRED.json')
    if boundary['reason']!='SIGNAL_OR_ALLOCATION_END' or not (Path(boundary['checkpoint'])/'COMMITTED.json').exists():
        raise ValueError('NO_VERIFIED_BOUNDARY_CONTINUATION')
    resource_check(True)
    submit(['sbatch','--parsable','--array='+str(SEEDS.index(seed)),str(HERE/'train_array.sbatch')],
           'continuation_'+str(seed)+'_'+os.environ['SLURM_JOB_ID'])


if __name__=='__main__':main()
