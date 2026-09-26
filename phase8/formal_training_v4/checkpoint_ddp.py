"""Atomic two-rank checkpoints; never restore incompatible v1 token budgets."""
import os
import random
import sys
import uuid
from plan import *
sys.path.insert(0,str(LEGACY))
from checkpoint import atomic_json, latest_checkpoint, StopAtBoundary


def rng_capture(rank):
    import torch,numpy as np
    return dict(python=random.getstate(),numpy=np.random.get_state(),torch=torch.get_rng_state(),
        cuda=torch.cuda.get_rng_state(rank))


def rng_restore(value,rank):
    import torch,numpy as np
    random.setstate(value['python']);np.random.set_state(value['numpy'])
    torch.set_rng_state(value['torch']);torch.cuda.set_rng_state(value['cuda'],rank)


def save(directory,ddp,optimizer,scheduler,progress,fingerprint,rank):
    import torch
    dist=torch.distributed;directory=Path(directory);rng=rng_capture(rank)
    name=f"step_{progress['step']:07d}";final=directory/name
    token=[uuid.uuid4().hex if rank==0 else None];dist.broadcast_object_list(token,src=0)
    temp=directory/(name+'.incomplete.'+token[0])
    if rank==0:
        directory.mkdir(parents=True,exist_ok=True)
        if final.exists():raise FileExistsError('PRESERVE_CHECKPOINT:'+str(final))
        temp.mkdir();ddp.module.model.save_pretrained(temp/'adapter',safe_serialization=True)
    dist.barrier()
    payload=dict(format_version=4,fingerprint=fingerprint,rank=rank,world_size=2,
        progress=progress,optimizer=optimizer.state_dict(),scheduler=scheduler.state_dict(),rng=rng)
    torch.save(payload,temp/f'rank_{rank}.pt')
    dist.barrier()
    if rank==0:
        hashes={str(p.relative_to(temp)):sha(p) for p in temp.rglob('*') if p.is_file()}
        for rel in hashes:
            with (temp/rel).open('rb') as f:os.fsync(f.fileno())
        atomic_json(temp/'COMMITTED.json',dict(step=progress['step'],fingerprint=fingerprint,hashes=hashes,
            world_size=2,full_optimizer_scheduler_per_rank_rng=True))
        os.replace(temp,final)
        atomic_json(directory/'LATEST.json',dict(step=progress['step'],name=name,fingerprint=fingerprint))
    dist.barrier();rng_restore(rng,rank)
    return final


def restore(path,ddp,optimizer,scheduler,fingerprint,rank):
    import torch
    from safetensors.torch import load_file
    from peft import set_peft_model_state_dict,get_peft_model_state_dict
    path=Path(path);commit=read(path/'COMMITTED.json')
    if commit['fingerprint']!=fingerprint or commit['world_size']!=2:raise ValueError('INCOMPATIBLE_CHECKPOINT')
    for rel,expected in commit['hashes'].items():
        if sha(path/rel)!=expected:raise ValueError('CHECKPOINT_CORRUPT:'+rel)
    payload=torch.load(path/f'rank_{rank}.pt',map_location='cpu',weights_only=False)
    if payload['fingerprint']!=fingerprint or payload['rank']!=rank:raise ValueError('RANK_STATE_MISMATCH')
    weights=load_file(path/'adapter/adapter_model.safetensors')
    set_peft_model_state_dict(ddp.module.model,weights)
    actual=get_peft_model_state_dict(ddp.module.model)
    if any(not torch.equal(actual[k].cpu(),v) for k,v in weights.items()):raise ValueError('ADAPTER_RESTORE_MISMATCH')
    optimizer.load_state_dict(payload['optimizer']);scheduler.load_state_dict(payload['scheduler'])
    def equal(a,b):
        if isinstance(a,torch.Tensor):return torch.equal(a.cpu(),b.cpu())
        if isinstance(a,dict):return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
        if isinstance(a,(list,tuple)):return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
        return a==b
    if not equal(optimizer.state_dict(),payload['optimizer']) or scheduler.state_dict()!=payload['scheduler']:
        raise ValueError('OPTIMIZER_SCHEDULER_RESTORE_MISMATCH')
    rng_restore(payload['rng'],rank)
    if not torch.equal(torch.get_rng_state(),payload['rng']['torch']):raise ValueError('CPU_RNG_RESTORE')
    if not torch.equal(torch.cuda.get_rng_state(rank),payload['rng']['cuda']):raise ValueError('GPU_RNG_RESTORE')
    return payload['progress']
