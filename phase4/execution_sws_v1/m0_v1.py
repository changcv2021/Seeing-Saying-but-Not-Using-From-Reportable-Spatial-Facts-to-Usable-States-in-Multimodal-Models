"""Bounded 9B infrastructure equivalence, not mechanism localization or model training."""
import copy
import sys
import time
from common import *

CANONICAL=['{"value":0}','{"value":1}','{"value":2}','{"value":3}','{"value":null}']
TOLERANCE=dict(noop_answer_logprob_abs=1e-5,prefill_incremental_token_logprob_abs=0.15,incremental_argmax_differences=0)

def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    lockpath=root/'manifest/M0_LOCK_V1.json'; lock=load(lockpath)
    if a.dry_run: print(json.dumps(dict(status='DRY_RUN',requests=4,model='qwen35_9b',canonical_answers=CANONICAL,tolerance=TOLERANCE))); return
    if not load(root/'scheduler/resource_authorization.json').get('approved'): raise ValueError('NO_RESOURCE_AUTHORITY')
    for e in lock['code']+lock['inputs']:
        if sha(e['path'])!=e['sha256']: raise ValueError('M0_LOCK_CHANGED:'+e['path'])
    p=Path(c['project']); sys.path.insert(0,str(p/'src')); sys.path.insert(0,str(p/'research/state_binding_phase_a1/core_execution_v3'))
    from pipeline_v3 import Pipeline,tensor_hash,install_gold_guard
    import importlib.util
    spec=importlib.util.spec_from_file_location('m0_health',p/'scripts/full_multimodel_split_v5/gpu_health.py'); health=importlib.util.module_from_spec(spec); spec.loader.exec_module(health)
    folder=root/'whitebox/M0_v1'; health.check(folder)
    audit=install_gold_guard()
    import torch
    import transformers
    from transformers import AutoModelForMultimodalLM
    if torch.cuda.device_count()!=1: raise ValueError('M0_REQUIRES_ONE_9B_GPU')
    pipeline=Pipeline(dict(c,visual_hash_version='PURE_MEDIA_TENSORS_V3_SHARED_RUNTIME'),'qwen35_9b')
    torch.manual_seed(c['seed']); torch.cuda.manual_seed_all(c['seed']); torch.set_float32_matmul_precision('high')
    started=time.monotonic(); model=AutoModelForMultimodalLM.from_pretrained(pipeline.mc['model_path'],local_files_only=True,dtype=torch.bfloat16,device_map='cuda',attn_implementation='sdpa',low_cpu_mem_usage=True); model.eval()
    layers=model.model.language_model.layers; selected=sorted({0,len(layers)//2,len(layers)-1})
    modules=[dict(layer=i,name=f'model.language_model.layers.{i}',class_name=type(x).__name__,block_type=x.block_type,
                  submodules=[n for n,_ in x.named_children()]) for i,x in enumerate(layers)]
    save(folder/'module_manifest.json',dict(model=pipeline.mc,torch=torch.__version__,transformers=transformers.__version__,selected_noop_layers=selected,
        modules=modules,model_config=model.config.to_dict(),load_seconds=time.monotonic()-started,allocated_gpu_uuids=health.allocated_uuids()))
    requests=[r for r in rows(root/'public_inputs/smoke/requests.jsonl') if r['experiment']=='M0_SMOKE']
    expected={r['request_id']:r for r in rows(root/'review/smoke/qwen35_9b_processor.jsonl')}
    results=[]
    def cache_fingerprint(cache):
        out=[]
        for i,layer in enumerate(cache.layers):
            fields={}
            for name in ('keys','values','conv_states','recurrent_states'):
                obj=getattr(layer,name,None)
                values=obj if isinstance(obj,dict) else {0:obj}
                for key,value in values.items():
                    if torch.is_tensor(value): fields[f'{name}.{key}']=dict(shape=list(value.shape),dtype=str(value.dtype),sha256=tensor_hash(value))
            out.append(dict(layer=i,cache_class=type(layer).__name__,fields=fields))
        return dict(layers=out,seq_length=int(cache.get_seq_length()))
    def cache_pointers(cache):
        pointers=set()
        for layer in cache.layers:
            for name in ('keys','values','conv_states','recurrent_states'):
                obj=getattr(layer,name,None)
                for v in (obj.values() if isinstance(obj,dict) else [obj]):
                    if torch.is_tensor(v) and v.numel(): pointers.add(v.data_ptr())
        return pointers
    for request in requests:
        rid='m0_'+request['request_id']; target=folder/'raw'/(rid+'.json')
        if target.exists(): results.append(load(target)); continue
        batch,pres,_=pipeline.process(request); want=expected[request['request_id']]
        if (pres['presentation_hash'],pres['rendered_prompt_sha256'])!=(want['presentation_hash'],want['rendered_prompt_sha256']): raise ValueError('M0_PROCESSOR_BRIDGE_MISMATCH')
        inputs=batch.to(model.device); length=inputs['input_ids'].shape[-1]
        record=dict(request_id=rid,source_request_id=request['source_request_id'],source_sws_request_id=request['request_id'],world_cluster_id=request['world_cluster_id'],model_id='qwen35_9b',model_revision=pipeline.mc['revision'],
                    experiment='M0_TECHNICAL_EQUIVALENCE',split='history',prompt=pres['rendered_prompt'],prompt_hash=pres['rendered_prompt_sha256'],
                    visual_tensor_sha256=pres['presentation_hash'],media_refs=request['payload']['media'],input_token_ids=inputs['input_ids'][0].tolist(),
                    reviewed_task_unchanged=True,selected_noop_layers=selected,tolerances=TOLERANCE,slurm_job_id=os.environ['SLURM_JOB_ID'])
        try:
            with torch.inference_mode():
                model.model.rope_deltas=None
                output=model.generate(**inputs,max_new_tokens=512,do_sample=False,use_cache=True)
                off=output[0,length:].tolist(); del output
                handles=[layers[i].register_forward_hook(lambda module,args,output:output.clone()) for i in selected]
                try:
                    model.model.rope_deltas=None
                    output=model.generate(**inputs,max_new_tokens=512,do_sample=False,use_cache=True)
                    on=output[0,length:].tolist(); del output
                finally:
                    for h in handles: h.remove()
                record.update(raw_response=pipeline.processor.decode(off,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip(),output_token_ids=off,
                    noop_raw_response=pipeline.processor.decode(on,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip(),noop_output_token_ids=on,
                    hook_generate_exact=off==on)
                oldpath=Path(c['b0'])/'raw/core/qwen35_9b'/(request['source_request_id']+'.json')
                old=load(oldpath)
                record.update(legacy_raw_path=str(oldpath),legacy_raw_sha256=sha(oldpath),legacy_output_token_ids=old.get('output_token_ids'),
                              original_runner_generated_exact=off==old.get('output_token_ids'),legacy_model_revision=old.get('model_revision'))
                canonical_results=[]
                for answer in CANONICAL:
                    tokens=torch.tensor([pipeline.processor.tokenizer.encode(answer,add_special_tokens=False)],device=model.device)
                    n=tokens.shape[1]; full=dict(inputs); full['input_ids']=torch.cat([inputs['input_ids'],tokens],dim=1)
                    full['attention_mask']=torch.cat([inputs['attention_mask'],torch.ones_like(tokens)],dim=1)
                    if 'mm_token_type_ids' in inputs: full['mm_token_type_ids']=torch.cat([inputs['mm_token_type_ids'],torch.zeros_like(tokens)],dim=1)
                    model.model.rope_deltas=None
                    res=model(**full,use_cache=False,logits_to_keep=n+1)
                    logits=res.logits[0,:n].float(); del res
                    token_lp=torch.log_softmax(logits,dim=-1).gather(-1,tokens[0,:,None]).squeeze(-1)
                    off_argmax=logits.argmax(-1).tolist(); del logits
                    handles=[layers[i].register_forward_hook(lambda module,args,output:output.clone()) for i in selected]
                    try:
                        model.model.rope_deltas=None
                        res=model(**full,use_cache=False,logits_to_keep=n+1)
                        hook_logits=res.logits[0,:n].float(); del res
                        hook_lp=torch.log_softmax(hook_logits,dim=-1).gather(-1,tokens[0,:,None]).squeeze(-1); hook_argmax=hook_logits.argmax(-1).tolist(); del hook_logits
                    finally:
                        for h in handles: h.remove()
                    # Clone the full hybrid cache, including convolution and recurrent state, not KV only.
                    model.model.rope_deltas=None
                    pre=model(**inputs,use_cache=True,logits_to_keep=1); original=pre.past_key_values
                    source_before=cache_fingerprint(original); clone=copy.deepcopy(original)
                    clone_before=cache_fingerprint(clone); no_alias=not(cache_pointers(original)&cache_pointers(clone))
                    deltas=model.model.rope_deltas.detach().clone()
                    next_logits=pre.logits[0,-1].float(); del pre
                    incremental=[]; incremental_argmax=[]
                    for j in range(n):
                        incremental.append(float(torch.log_softmax(next_logits,dim=-1)[tokens[0,j]])); incremental_argmax.append(int(next_logits.argmax()))
                        if j<n-1:
                            model.model.rope_deltas=deltas.clone()
                            position=(torch.tensor([[[length+j]]],device=model.device).expand(3,1,1)+deltas.to(model.device).view(1,1,1))
                            step=model(input_ids=tokens[:,j:j+1],attention_mask=torch.ones((1,length+j+1),device=model.device,dtype=inputs['attention_mask'].dtype),
                                position_ids=position,past_key_values=clone,use_cache=True,logits_to_keep=1)
                            next_logits=step.logits[0,-1].float(); clone=step.past_key_values; del step
                    source_after=cache_fingerprint(original)
                    diff=max(abs(float(x)-y) for x,y in zip(token_lp,incremental)); argdiff=sum(x!=y for x,y in zip(off_argmax,incremental_argmax))
                    canonical_results.append(dict(canonical_answer=answer,answer_token_ids=tokens[0].tolist(),full_logprob=float(token_lp.sum()),noop_logprob=float(hook_lp.sum()),
                        incremental_logprob=sum(incremental),full_token_logprobs=token_lp.tolist(),noop_token_logprobs=hook_lp.tolist(),incremental_token_logprobs=incremental,
                        noop_argmax_differences=sum(x!=y for x,y in zip(off_argmax,hook_argmax)),full_incremental_argmax_differences=argdiff,max_full_incremental_token_logprob_difference=diff,
                        cache_copy_values_equal=source_before==clone_before,cache_copy_has_no_tensor_alias=no_alias,source_cache_unchanged_after_clone_decode=source_before==source_after,
                        source_cache_manifest=source_before,rope_deltas=deltas.tolist(),last_clone_seq_length=int(clone.get_seq_length())))
                    del original,clone,full,next_logits
                record['canonical_answers']=canonical_results
                record['hook_equivalence_pass']=record['hook_generate_exact'] and all(abs(x['full_logprob']-x['noop_logprob'])<=TOLERANCE['noop_answer_logprob_abs'] and x['noop_argmax_differences']==0 for x in canonical_results)
                record['cache_equivalence_pass']=all(x['cache_copy_values_equal'] and x['cache_copy_has_no_tensor_alias'] and x['source_cache_unchanged_after_clone_decode'] and x['max_full_incremental_token_logprob_difference']<=TOLERANCE['prefill_incremental_token_logprob_abs'] and x['full_incremental_argmax_differences']==0 for x in canonical_results)
                record['status']='PASS' if record['hook_equivalence_pass'] and record['cache_equivalence_pass'] and record['original_runner_generated_exact'] else 'NOT_EQUIVALENT_NO_PATCH_AUTHORIZATION'
        except Exception as exc:
            record.update(status='INFRASTRUCTURE_FAILED_NO_PATCH_AUTHORIZATION',error=type(exc).__name__+': '+str(exc))
        record.update(gold_access_audit=dict(audit),timestamp=now()); save(target,record); results.append(record)
        print(json.dumps(dict(request_id=rid,status=record['status'],error=record.get('error'))),flush=True)
        if record['status'].startswith('INFRASTRUCTURE'): break
    report=dict(status='PASS' if len(results)==4 and all(r['status']=='PASS' for r in results) else 'BLOCKED_PATCH_BRANCH',model='qwen35_9b',
        requests_run=len(results),requests_planned=4,worlds=len({r['world_cluster_id'] for r in results}),
        raw_index=[entry(folder/'raw'/(r['request_id']+'.json')) for r in results],tolerances=TOLERANCE,
        canonical_answers_are_fixed_technical_comparison_strings_not_gold=True,actual_mechanism_identified=False,
        no_M1_M2_or_confirmation_submitted_by_this_job=True,job_id=os.environ['SLURM_JOB_ID'],gold_access_audit=dict(audit))
    save(folder/'M0_ACCEPTANCE.json',report); print(json.dumps(report),flush=True)

if __name__=='__main__': main()
