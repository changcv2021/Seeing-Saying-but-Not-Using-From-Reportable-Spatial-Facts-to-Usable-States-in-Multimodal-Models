"""Accelerated BF16 two-rank training. No math-only/determinism speed restriction."""
import math
import os
import random
import sys
from plan import *


def configure(rank, backend='sdpa_auto'):
    import torch
    torch.cuda.set_device(rank)
    torch.use_deterministic_algorithms(False)
    torch.backends.cudnn.benchmark=True
    torch.backends.cudnn.deterministic=False
    torch.backends.cuda.enable_flash_sdp(True)
    torch.backends.cuda.enable_mem_efficient_sdp(True)
    torch.backends.cuda.enable_cudnn_sdp(True)
    torch.backends.cuda.enable_math_sdp(True)  # fallback only; never force math
    torch.backends.cuda.matmul.allow_tf32=True
    torch.backends.cudnn.allow_tf32=True
    return dict(flash_enabled=torch.backends.cuda.flash_sdp_enabled(),
        efficient_enabled=torch.backends.cuda.mem_efficient_sdp_enabled(),
        cudnn_enabled=torch.backends.cuda.cudnn_sdp_enabled(),math_fallback=True,
        deterministic_algorithms=False,tf32=True,requested=backend)


def build(plan,seed,rank):
    sys.path.insert(0,str(ENGINE))
    from model_io import load_engine
    import torch
    from torch.nn.parallel import DistributedDataParallel
    backend=configure(rank,plan['attention_backend'])
    model,processor,engine=load_engine(ROOT,seed)
    # Identical initialization, then independent per-rank stochastic streams.
    import numpy as np
    random.seed(seed+rank);np.random.seed(seed+rank);torch.manual_seed(seed+rank)
    torch.cuda.manual_seed(seed+rank)
    wrapped=LossModule(model)
    ddp=DistributedDataParallel(wrapped,device_ids=[rank],output_device=rank,
        broadcast_buffers=False,find_unused_parameters=False,gradient_as_bucket_view=True)
    optimizer=torch.optim.AdamW([p for p in ddp.parameters() if p.requires_grad],
        lr=plan['learning_rate'],weight_decay=plan['weight_decay'])
    warmup=max(1,math.ceil(plan['optimizer_updates']*plan['warmup_fraction']))
    def rate(step):
        if step<warmup:return (step+1)/warmup
        return max(0.,(plan['optimizer_updates']-step)/max(1,plan['optimizer_updates']-warmup))
    scheduler=torch.optim.lr_scheduler.LambdaLR(optimizer,rate)
    engine['backend']=backend
    return ddp,optimizer,scheduler,engine


import torch


class LossModule(torch.nn.Module):
    def __init__(self,model): super().__init__();self.model=model
    def forward(self,batch,target_lengths):
        n=batch['input_ids'].shape[-1];m=int(target_lengths.max())
        positions=torch.arange(n-m-1,n-1,device=batch['input_ids'].device)
        out=self.model(**batch,use_cache=False,logits_to_keep=positions)
        labels=batch['input_ids'][:,-m:]
        loss=torch.nn.functional.cross_entropy(out.logits.float().transpose(1,2),labels,reduction='none')
        mask=torch.arange(m,device=labels.device)[None,:]>=m-target_lengths[:,None]
        return (loss*mask).sum(dim=1)/target_lengths


def update(ddp,optimizer,scheduler,item,plan,rank):
    import contextlib,time
    start=time.monotonic();optimizer.zero_grad(set_to_none=True)
    microbatches=item['microbatches'];loss_total=0.;tokens=0;processed=0;records=0;receipts=[]
    local_batch=plan['effective_batch_size']//2
    if len(item['sample_ids'])!=local_batch:raise ValueError('EFFECTIVE_BATCH_MISMATCH')
    total_weight=sum(float(m['weights'].sum()) for m in microbatches)
    if total_weight!=local_batch:raise ValueError('PRIMARY_UNIT_WEIGHT_MISMATCH')
    for i,m in enumerate(microbatches):
        ctx=ddp.no_sync() if i<len(microbatches)-1 else contextlib.nullcontext()
        with ctx:
            batch={k:v.to(rank,non_blocking=True) for k,v in m['batch'].items()}
            lengths=m['target_lengths'].to(rank,non_blocking=True)
            weights=m['weights'].to(rank,non_blocking=True)
            losses=ddp(batch,lengths)
            loss=(losses*weights).sum()/local_batch
            if not torch.isfinite(loss):raise ValueError('NONFINITE_LOSS')
            loss.backward();loss_total+=float(loss.detach())
        tokens+=int(lengths.sum());processed+=int(batch['attention_mask'].sum());records+=len(lengths)
        receipts.extend(m['receipts'])
        del batch,lengths,weights,losses,loss
    norm=torch.nn.utils.clip_grad_norm_(ddp.parameters(),plan['max_grad_norm'])
    if not torch.isfinite(norm):raise ValueError('NONFINITE_GRADIENT')
    optimizer.step();scheduler.step();optimizer.zero_grad(set_to_none=True)
    stats=torch.tensor([loss_total,tokens,processed,records],dtype=torch.float64,device=rank)
    torch.distributed.all_reduce(stats)
    torch.cuda.synchronize(rank)
    return dict(loss=float(stats[0])/2,supervised_tokens=int(stats[1]),processed_tokens=int(stats[2]),
        forward_records=int(stats[3]),gradient_norm=float(norm),seconds=time.monotonic()-start,
        peak_gpu_bytes=torch.cuda.max_memory_allocated(rank),sample_ids=item['sample_ids'],receipts=receipts)
