"""Actual fixed two-GPU ingress for five arms and fresh-process full restores."""
import os
import subprocess
import time
from plan import *

PYTHON='python'


def main():
    if not os.environ.get('SLURM_JOB_ID'):raise ValueError('SLURM_REQUIRED')
    from trainer import check_plan
    p=check_plan(OUTPUT);accept=OUTPUT/'GPU_ACCEPTANCE.json'
    if accept.exists():raise FileExistsError('PRESERVE_ACCEPTANCE')
    results=[]
    cases=[(m,'first') for m in METHODS]+[('answer_balanced','resume'),('pss_full','resume')]
    for method,stage in cases:
        command=[PYTHON,'-m','torch.distributed.run','--standalone','--nnodes=1','--nproc_per_node=2',
            str(HERE/'trainer.py'),'--method',method,'--seed',str(SEEDS[0]),'--smoke',stage]
        print('RUN',method,stage,flush=True);start=time.monotonic()
        log=OUTPUT/'logs'/f"smoke_{os.environ['SLURM_JOB_ID']}_{method}_{stage}"
        with log.with_suffix('.out').open('x') as out,log.with_suffix('.err').open('x') as err:
            done=subprocess.run(command,stdout=out,stderr=err)
        if done.returncode:raise RuntimeError('GPU_SMOKE_FAILED:'+method+':'+stage+':'+str(done.returncode))
        attempt=OUTPUT/'smoke'/f'{method}__seed_{SEEDS[0]}'/'attempts'/(os.environ['SLURM_JOB_ID']+'_'+stage)
        records=[]
        for rank in (0,1):
            r=read(attempt/f'COMPLETE_RANK_{rank}.json')
            if r['status']!='COMPLETE' or (stage=='resume' and not r['full_restore_verified']):raise ValueError('RESTORE_NOT_VERIFIED')
            kernels=read(attempt/f'ATTENTION_RANK_{rank}.json')['operators']
            accelerated=any(any(token in k for token in ('flash_attention','efficient_attention','cudnn_attention')) for k in kernels)
            if not accelerated:raise ValueError('NO_ACCELERATED_SDPA_OBSERVED:'+str(kernels))
            if read(attempt/f'REPLICA_CHECK_RANK_{rank}.json')['status']!='PASS_IDENTICAL_REPLICAS':raise ValueError('REPLICA_SYNC')
            records.append(dict(rank=rank,result=r,attention_operators=kernels))
        results.append(dict(method=method,stage=stage,seconds=time.monotonic()-start,records=records,raw_log=str(log)))
    result=dict(status='PASS_TWO_GPU_ALL_METHODS_AND_FRESH_RESUME',plan_sha256=sha(OUTPUT/'PLAN.json'),
        job_id=os.environ['SLURM_JOB_ID'],results=results,strict_bitwise_trajectory_required=False,
        restore_check='Exact serialized adapter/optimizer/scheduler/RNG immediately after restore; continued step finite; no slow backend requirement',
        test_opened=False)
    accept.write_text(json.dumps(result,indent=2)+'\n');print(result['status'],flush=True)


if __name__=='__main__':main()
