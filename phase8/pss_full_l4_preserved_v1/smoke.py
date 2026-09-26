"""Per-seed two-update fresh-process DDP ingress/resume, never used for scoring."""
import argparse
import os
import subprocess
from plan import *


def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--seed',type=int,choices=SEEDS,required=True)
    args=parser.parse_args();dest=seed_output(args.seed)
    from trainer import check_plan
    check_plan(dest)
    receipt=dest/'GPU_ACCEPTANCE.json'
    if receipt.exists():
        r=read(receipt)
        if r['status']!='PASS_TWO_GPU_ALL_METHODS_AND_FRESH_RESUME' or r['plan_sha256']!=sha(dest/'PLAN.json'):
            raise ValueError('ACCEPTANCE_CHANGED')
        return
    results=[]
    for stage in ('first','resume'):
        cmd=[PYTHON,'-m','torch.distributed.run','--standalone','--nnodes=1','--nproc_per_node=2',
             str(HERE/'trainer.py'),'--output',str(dest),'--method',METHOD,'--seed',str(args.seed),'--smoke',stage]
        log=dest/'logs'/f'smoke_{os.environ["SLURM_JOB_ID"]}_{stage}'
        with log.with_suffix('.out').open('x') as out,log.with_suffix('.err').open('x') as err:
            subprocess.run(cmd,stdout=out,stderr=err,check=True)
        attempt=dest/'smoke'/f'{METHOD}__seed_{args.seed}'/'attempts'/(os.environ['SLURM_JOB_ID']+'_'+stage)
        ranks=[]
        for rank in (0,1):
            done=read(attempt/f'COMPLETE_RANK_{rank}.json')
            attention=read(attempt/f'ATTENTION_RANK_{rank}.json')
            if done['status']!='COMPLETE' or (stage=='resume' and not done['full_restore_verified']):
                raise ValueError('FRESH_RESTORE_FAILED')
            if not any(any(t in k for t in ('flash_attention','efficient_attention','cudnn_attention')) for k in attention['operators']):
                raise ValueError('NO_FAST_ATTENTION')
            if read(attempt/f'REPLICA_CHECK_RANK_{rank}.json')['status']!='PASS_IDENTICAL_REPLICAS':
                raise ValueError('DDP_REPLICAS')
            ranks.append(dict(rank=rank,complete=done,attention=attention))
        results.append(dict(stage=stage,ranks=ranks))
    write(receipt,dict(status='PASS_TWO_GPU_ALL_METHODS_AND_FRESH_RESUME',methods=[METHOD],seed=args.seed,
          plan_sha256=sha(dest/'PLAN.json'),results=results,job_id=os.environ['SLURM_JOB_ID'],
          engineering_only=True,test_opened=False,formal_initialization='fresh base, NOT smoke adapter'))


if __name__=='__main__':
    main()
