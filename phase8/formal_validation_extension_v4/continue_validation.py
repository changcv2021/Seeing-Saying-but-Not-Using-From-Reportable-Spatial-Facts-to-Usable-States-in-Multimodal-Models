"""Continue only allocation-boundary-unfinished engineering cases; no result selection."""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'formal_training_v4'))
from plan import OUTPUT,METHODS,SEEDS,read,sha
from trainer import check_plan
TRAINER=HERE.parent/'formal_training_v4/trainer.py'
PYTHON='python'


def case_result(root,method,stage):
    run=root/'smoke'/f'{method}__seed_{SEEDS[0]}'
    found=[]
    for attempt in sorted((run/'attempts').glob('*_'+stage)):
        if not all((attempt/f'COMPLETE_RANK_{rank}.json').exists() for rank in (0,1)):continue
        records=[]
        for rank in (0,1):
            r=read(attempt/f'COMPLETE_RANK_{rank}.json')
            if r['status']!='COMPLETE' or r['progress']['step']!=(1 if stage=='first' else 2):
                raise ValueError('BAD_COMPLETION_RECORD')
            if stage=='resume' and not r['full_restore_verified']:raise ValueError('UNVERIFIED_RESTORE')
            operators=read(attempt/f'ATTENTION_RANK_{rank}.json')['operators']
            if not any(any(t in k for t in ('flash_attention','efficient_attention','cudnn_attention')) for k in operators):
                raise ValueError('ACCELERATED_BACKEND_NOT_OBSERVED')
            if read(attempt/f'REPLICA_CHECK_RANK_{rank}.json')['status']!='PASS_IDENTICAL_REPLICAS':
                raise ValueError('REPLICA_CHECK')
            records.append(dict(rank=rank,result=r,attention_operators=operators))
        found.append(dict(method=method,stage=stage,records=records,source_attempt=str(attempt)))
    if len(found)>1:raise ValueError('MULTIPLE_COMPLETED_CASES_NO_BEST_SELECTION')
    return found[0] if found else None


def main():
    if not os.environ.get('SLURM_JOB_ID'):raise ValueError('SLURM_REQUIRED')
    plan=check_plan(OUTPUT);accept=OUTPUT/'GPU_ACCEPTANCE.json'
    if accept.exists():
        r=read(accept)
        if r['status']!='PASS_TWO_GPU_ALL_METHODS_AND_FRESH_RESUME' or r['plan_sha256']!=sha(OUTPUT/'PLAN.json'):
            raise ValueError('EXISTING_ACCEPTANCE_MISMATCH')
        print('ORIGINAL_VALIDATION_ALREADY_COMPLETE_NO_EXTRA_GPU_WORK',flush=True);return
    boundaries=list((OUTPUT/'smoke').glob('*/attempts/*/CONTINUATION_REQUIRED.json'))
    if not boundaries or any(read(p)['reason']!='SIGNAL_OR_ALLOCATION_END' for p in boundaries):
        raise ValueError('NO_ALLOCATION_BOUNDARY_STOP: unknown GPU/code failures need diagnosis, not blind retry')
    retry=OUTPUT/('validation_extension_'+os.environ['SLURM_JOB_ID']);retry.mkdir()
    for name in ('PLAN.json','samples.json','catalog.json','SMOKE_PANEL.json'):
        shutil.copy2(OUTPUT/name,retry/name)
        if sha(OUTPUT/name)!=sha(retry/name):raise ValueError('COPY_HASH_MISMATCH')
    (retry/'logs').mkdir()
    manifest=dict(reason='CONTINUE_PREDECLARED_CASES_AFTER_ALLOCATION_BOUNDARY_ONLY',
        boundaries=[str(p) for p in boundaries],original_plan_sha256=sha(OUTPUT/'PLAN.json'),
        helper_sha256=sha(__file__),created=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        inherited_scientific_runtime_unchanged=True)
    (retry/'EXTENSION.json').write_text(json.dumps(manifest,indent=2)+'\n')
    cases=[(m,'first') for m in METHODS]+[('answer_balanced','resume'),('pss_full','resume')]
    results=[];first={}
    for method,stage in cases:
        existing=case_result(OUTPUT,method,stage)
        if existing:
            print('REUSE_COMPLETE',method,stage,flush=True);r=existing
        else:
            if stage=='resume':
                checkpoint=Path(first[method]['records'][0]['result']['checkpoint'])
                dest=retry/'smoke'/f'{method}__seed_{SEEDS[0]}'/'checkpoints'
                target=dest/checkpoint.name
                if not target.exists():
                    dest.mkdir(parents=True,exist_ok=True);shutil.copytree(checkpoint,target)
                    commit=read(target/'COMMITTED.json')
                    for rel,h in commit['hashes'].items():
                        if sha(target/rel)!=h:raise ValueError('COPIED_CHECKPOINT_CHANGED')
                    (dest/'LATEST.json').write_text(json.dumps(dict(step=1,name=target.name,fingerprint=commit['fingerprint']))+'\n')
            command=[PYTHON,'-m','torch.distributed.run','--standalone','--nnodes=1','--nproc_per_node=2',
                str(TRAINER),'--output',str(retry),'--method',method,'--seed',str(SEEDS[0]),'--smoke',stage]
            log=retry/'logs'/f'{method}_{stage}';print('RUN_REMAINING',method,stage,flush=True)
            with log.with_suffix('.out').open('x') as stdout,log.with_suffix('.err').open('x') as stderr:
                run=subprocess.run(command,stdout=stdout,stderr=stderr)
            if run.returncode:raise ValueError('CONTINUATION_CASE_FAILED:'+method+':'+stage)
            r=case_result(retry,method,stage)
            if not r:raise ValueError('NOT_COMPLETED:'+method+':'+stage)
        results.append(r)
        if stage=='first':first[method]=r
    result=dict(status='PASS_TWO_GPU_ALL_METHODS_AND_FRESH_RESUME',plan_sha256=sha(OUTPUT/'PLAN.json'),
        results=results,strict_bitwise_trajectory_required=False,test_opened=False,
        job_id=os.environ['SLURM_JOB_ID'],original_job_id='8312915',extension_manifest=str(retry/'EXTENSION.json'),
        restore_check='Exact serialized adapter/optimizer/scheduler/RNG plus finite next update; fast backend preserved')
    with accept.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(result['status'],flush=True)


if __name__=='__main__':main()
