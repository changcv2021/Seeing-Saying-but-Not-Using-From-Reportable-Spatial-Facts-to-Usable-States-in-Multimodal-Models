"""Five existing methods, matched steps/global primary batch, two-GPU DDP."""
import argparse
import datetime
import fcntl
import os
import signal
import subprocess
import time
import sys
from plan import *
from data import StepDataset,loader
from checkpoint_ddp import atomic_json,latest_checkpoint,StopAtBoundary,save,restore


def check_plan(output):
    p=read(Path(output)/'PLAN.json');validate_plan(p)
    for file,expected in p['code_hashes'].items():
        if sha(file)!=expected:raise ValueError('FROZEN_CODE_CHANGED:'+file)
    for name in ('samples','catalog'):
        if sha(Path(output)/(name+'.json'))!=p[name+'_sha256']:raise ValueError('FROZEN_DATA_CHANGED:'+name)
    return p


def end_time():
    s=subprocess.run(['scontrol','show','job','-o',os.environ['SLURM_JOB_ID']],text=True,capture_output=True,check=True).stdout
    v=next(t.split('=',1)[1] for t in s.split() if t.startswith('EndTime='))
    return datetime.datetime.fromisoformat(v).timestamp()


def main():
    if not os.environ.get('SLURM_JOB_ID'):raise ValueError('SLURM_REQUIRED')
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--method',choices=METHODS,required=True);parser.add_argument('--seed',type=int,choices=SEEDS,required=True)
    parser.add_argument('--smoke',choices=('first','resume'))
    args=parser.parse_args();p=check_plan(args.output)
    import torch
    from engine import build,update
    rank=int(os.environ['LOCAL_RANK']);torch.cuda.set_device(rank)
    if int(os.environ['WORLD_SIZE'])!=2:raise ValueError('EXACTLY_TWO_GPUS')
    torch.distributed.init_process_group('nccl',timeout=datetime.timedelta(minutes=30))
    run=f'{args.method}__seed_{args.seed}'
    base=args.output/('smoke' if args.smoke else 'runs')/run;base.mkdir(parents=True,exist_ok=True)
    if not args.smoke:
        accepted=read(args.output/'GPU_ACCEPTANCE.json')
        if accepted['status']!='PASS_TWO_GPU_ALL_METHODS_AND_FRESH_RESUME' or accepted['plan_sha256']!=sha(args.output/'PLAN.json'):
            raise ValueError('NOT_GPU_VALIDATED')
    fingerprint=digest([sha(args.output/'PLAN.json'),args.method,args.seed,'smoke' if args.smoke else 'formal'])
    lock=None
    if rank==0:
        lock=(base/'RUN.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    torch.distributed.barrier()
    attempt=base/'attempts'/(os.environ['SLURM_JOB_ID']+('_'+args.smoke if args.smoke else ''))
    attempt.mkdir(parents=True,exist_ok=True)
    if (attempt/f'COMPLETE_RANK_{rank}.json').exists():raise ValueError('DO_NOT_REPEAT_ATTEMPT')
    if rank==0:
        sys.path.insert(0,str(HERE.parents[1]/'SpaceConflict/scripts/full_multimodel_split_v5'))
        from gpu_health import check
        check(attempt)
    torch.distributed.barrier()
    ddp,opt,sched,engine=build(p,args.seed,rank)
    ckpt=latest_checkpoint(base/'checkpoints',fingerprint)
    progress=dict(step=0,base_examples=0,supervised_tokens=0,processed_tokens=0,forward_records=0)
    if ckpt:progress=restore(ckpt,ddp,opt,sched,fingerprint,rank)
    if args.smoke=='resume' and progress['step']!=1:raise ValueError('SMOKE_RESUME_REQUIRES_FIRST_STEP')
    if args.smoke=='first' and ckpt:raise ValueError('PRESERVE_FIRST_SMOKE')
    fixed_ids=read(args.output/'SMOKE_PANEL.json')['sample_ids'] if args.smoke else None
    stop=(1 if args.smoke=='first' else 2) if args.smoke else p['optimizer_updates']
    dataset=StepDataset(args.output,args.method,args.seed,rank,progress['step'],stop,fixed_ids)
    batches=loader(dataset);ddp.train();flag=StopAtBoundary().install();end=end_time()
    atomic_json(attempt/f'START_RANK_{rank}.json',dict(engine=engine,fingerprint=fingerprint,
        method=args.method,seed=args.seed,start_step=progress['step'],resumed_from=str(ckpt),rank=rank,
        full_restore_verified=bool(ckpt),effective_batch_size=p['effective_batch_size']))
    last_save=time.monotonic();last_step=progress['step'] if ckpt else -1;max_step=0.
    log=(attempt/f'updates_rank_{rank}.jsonl').open('x')
    it=iter(batches)
    while progress['step']<stop:
        request=torch.tensor([int(flag.requested or end-time.time()<max(1800,max_step*2+600)),int(flag.signal==signal.SIGTERM)],device=rank)
        torch.distributed.all_reduce(request,op=torch.distributed.ReduceOp.MAX)
        if int(request[0]):
            if last_step!=progress['step']:ckpt=save(base/'checkpoints',ddp,opt,sched,progress,fingerprint,rank)
            if rank==0:
                name='TERMINATED_NO_AUTORETRY.json' if int(request[1]) else 'CONTINUATION_REQUIRED.json'
                atomic_json(attempt/name,dict(step=progress['step'],checkpoint=str(ckpt),fingerprint=fingerprint,
                    reason='CANCELLED' if int(request[1]) else 'SIGNAL_OR_ALLOCATION_END'))
            torch.distributed.barrier();return 143 if int(request[1]) else 0
        data_start=time.monotonic();item=next(it);data_wait=time.monotonic()-data_start
        if item['step']!=progress['step']:raise ValueError('SCHEDULE_CURSOR')
        if args.smoke:
            # Record actual attention operators on the first real batched update.
            with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU]) as profiler:
                result=update(ddp,opt,sched,item,p,rank)
            kernels=[v.key for v in profiler.key_averages() if 'attention' in v.key.lower() or 'flash' in v.key.lower()]
            atomic_json(attempt/f'ATTENTION_RANK_{rank}.json',dict(operators=kernels))
        else:result=update(ddp,opt,sched,item,p,rank)
        progress['step']+=1;progress['base_examples']+=p['effective_batch_size']
        for key in ('supervised_tokens','processed_tokens','forward_records'):progress[key]+=result[key]
        max_step=max(max_step,result['seconds']+data_wait)
        row=dict(step=progress['step'],data_wait_seconds=data_wait,lr=opt.param_groups[0]['lr'],**result)
        log.write(json.dumps(row)+'\n');log.flush()
        if rank==0:
            atomic_json(base/'LIVE_STATUS.json',dict(job_id=os.environ['SLURM_JOB_ID'],progress=progress,
                optimizer_updates=p['optimizer_updates'],last_step_seconds=result['seconds'],data_wait_seconds=data_wait,loss=result['loss']))
            print({k:row[k] for k in ('step','seconds','data_wait_seconds','loss','supervised_tokens')},flush=True)
        # All ranks must enter the same checkpoint collectives.
        do_save=torch.tensor(int(rank==0 and (time.monotonic()-last_save>=p['checkpoint_seconds'] or progress['step']==stop)),device=rank)
        torch.distributed.broadcast(do_save,src=0)
        if int(do_save):
            ckpt=save(base/'checkpoints',ddp,opt,sched,progress,fingerprint,rank);last_step=progress['step'];last_save=time.monotonic()
    log.close()
    if args.smoke:
        from peft import get_peft_model_state_dict
        h=hashlib.sha256()
        for key,value in sorted(get_peft_model_state_dict(ddp.module.model).items()):
            h.update(key.encode());h.update(value.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes())
        hashes=[None,None];torch.distributed.all_gather_object(hashes,h.hexdigest())
        if len(set(hashes))!=1:raise ValueError('DDP_RANK_WEIGHTS_DIVERGED')
        atomic_json(attempt/f'REPLICA_CHECK_RANK_{rank}.json',dict(status='PASS_IDENTICAL_REPLICAS',hashes=hashes))
    if not args.smoke:
        expected=p['expected_exposure'][run]
        for key in ('base_examples','supervised_tokens','forward_records'):
            if progress[key]!=expected[key]:raise ValueError('FINAL_EXPOSURE_MISMATCH:'+key)
    atomic_json(attempt/f'COMPLETE_RANK_{rank}.json',dict(status='COMPLETE',progress=progress,
        checkpoint=str(ckpt),full_restore_verified=bool(args.smoke=='resume'),peak_gpu_bytes=torch.cuda.max_memory_allocated(rank)))
    if rank==0 and not args.smoke:
        atomic_json(base/'TRAINING_COMPLETE.json',dict(status='COMPLETE_FIXED_UPDATE_BUDGET',progress=progress,
            checkpoint=str(ckpt),final_adapter=str(ckpt/'adapter'),fingerprint=fingerprint,held_out_test_run=False))
    torch.distributed.barrier();torch.distributed.destroy_process_group()
    return 0


if __name__=='__main__':raise SystemExit(main())
