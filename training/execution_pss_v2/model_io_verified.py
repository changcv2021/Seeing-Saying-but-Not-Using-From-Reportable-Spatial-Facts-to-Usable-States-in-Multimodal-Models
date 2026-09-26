"""Versioned receipts for the actual tokenizer/processor output; frozen base loader reused."""
from model_io import *
from model_io import encode as original_encode

def encode(processor,sample,target=None,*,task_prompt=None,end_turn=False):
    if task_prompt is not None:
        ctx=sample.get('media_context','')
        if ctx and not task_prompt.startswith(ctx+'\n'):raise ValueError('PUBLIC_MEDIA_CONTEXT_NOT_PRESERVED')
    batch,receipt=original_encode(processor,sample,target,task_prompt=task_prompt,end_turn=end_turn)
    receipt['actual_task_prompt']=task_prompt
    receipt['processed_tensor_hashes']={k:dict(shape=list(v.shape),dtype=str(v.dtype),sha256=hashlib.sha256(v.detach().cpu().contiguous().numpy().tobytes()).hexdigest()) for k,v in batch.items() if hasattr(v,'shape')}
    receipt['tensor_hash_scope']='Actual processor tensors. Training input_ids include appended teacher-forced target.'
    return batch,receipt
