"""Independent E7 worker; only within-bundle own-response dependencies."""
import fcntl
import sys
import time
from common_auto_v2 import *
from contracts import parse
from e7_design_v1 import BATCH,render
from real_processor_v1 import verify


def main():
    p=arguments(__doc__);p.add_argument('--model',required=True);p.add_argument('--shard',type=int)
    a=p.parse_args();c,root=setup(a)
    if a.model not in c['models']:raise ValueError('UNAUTHORIZED_MODEL')
    sid=a.shard if a.shard is not None else int(os.environ['SLURM_ARRAY_TASK_ID'])
    out=root/'batches'/BATCH; lockpath=out/'manifest/REQUEST_LOCK.json'; lock=load(lockpath); verify(lock['code']+lock['public_inputs'])
    if not load(root/'scheduler/resource_authorization.json')['approved']:raise ValueError('RESOURCE_AUTHORIZATION_REQUIRED')
    shard=next(s for s in load(out/'manifest/shards.json') if s['shard']==sid);requests=list(rows(shard['request_file']['path']))
    pre=load(out/'review'/a.model/'PROCESSOR_ACCEPTANCE.json');verify([pre['records'],pre['request_lock']])
    if pre['status']!='PASS_STATIC_AND_MEDIA_TEMPLATES':raise ValueError('PROCESSOR_NOT_READY')
    dest=out/'raw'/a.model/f'shard_{sid:03}';dest.mkdir(parents=True,exist_ok=True)
    owner=(dest/'writer.lock').open('a');fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
    sys.path.insert(0,str(Path(c['project'])/'src'));sys.path.insert(0,str(Path(c['project'])/'research/state_binding_phase_a1/core_execution_v3'))
    import pipeline_v3,importlib.util
    spec=importlib.util.spec_from_file_location('e7_health',Path(c['project'])/'scripts/full_multimodel_split_v5/gpu_health.py')
    health=importlib.util.module_from_spec(spec);spec.loader.exec_module(health);health.check(dest)
    inventory=load(Path(c['b0'])/'manifest/model_inventory.json');mc0=next(m for m in inventory if m['key']==a.model)
    verify([mc0[k] for k in ('manifest','index','config')])
    if any(not Path(r['path']).is_file() or Path(r['path']).stat().st_size!=r['bytes'] for r in mc0['shard_sizes']):raise ValueError('MODEL_SHARD_CHANGED')
    audit=pipeline_v3.install_gold_guard()
    import torch,transformers
    from transformers import AutoModelForMultimodalLM
    torch.manual_seed(c['seed']);torch.cuda.manual_seed_all(c['seed']);torch.set_float32_matmul_precision('high')
    pipe=pipeline_v3.Pipeline(dict(c,visual_hash_version='PURE_MEDIA_TENSORS_V3_SHARED_RUNTIME'),a.model);mc=pipe.mc
    if torch.cuda.device_count()!=mc['gpus']:raise ValueError('MODEL_GPU_ALLOCATION_MISMATCH')
    kw=dict(local_files_only=True,dtype=torch.bfloat16,low_cpu_mem_usage=True,attn_implementation='sdpa')
    if mc['gpus']==1:kw['device_map']='cuda'
    else:kw.update(device_map='balanced',max_memory={i:'38GiB' for i in range(mc['gpus'])})
    started=time.monotonic();model=AutoModelForMultimodalLM.from_pretrained(mc['model_path'],**kw);model.eval()
    if any(str(v) in ('cpu','disk') for v in getattr(model,'hf_device_map',{}).values()):raise ValueError('CPU_OFFLOAD_NOT_ALLOWED')
    job=os.environ['SLURM_JOB_ID'];lockhash=sha(lockpath)
    save(dest/f'environment_{job}.json',dict(model=mc,job_id=job,torch=torch.__version__,transformers=transformers.__version__,
        device_map=getattr(model,'hf_device_map',{}),load_seconds=time.monotonic()-started,gpu_uuids=health.allocated_uuids(),
        runtime_lock_sha256=lockhash,actual_processor=pipe.processor.to_dict(),generation=c['generation']))
    expected={r['request_id']:r for r in rows(pre['records']['path'])};retained={};previous=None;times=[]
    for n,template in enumerate(requests,1):
        rid=template['request_id'];path=dest/'records'/(rid+'.json')
        r,ancestry=render(template,retained)
        if any(v['model_id']!=a.model for v in ancestry):raise ValueError('CROSS_MODEL_PARENT')
        if path.exists():
            raw=load(path)
            if (raw['request_hash'],raw['runtime_lock_sha256'],raw['parent_ancestry'])!=(template['model_independent_request_hash'],lockhash,ancestry):raise ValueError('RETAINED_RESPONSE_CHANGED')
            retained[rid]=raw;continue
        if previous!=r['world_cluster_id']:pipe.image_cache.clear();previous=r['world_cluster_id']
        raw=dict(request_id=rid,model_id=a.model,model_revision=mc['revision'],world_cluster_id=r['world_cluster_id'],
            condition=r['condition'],sample_family=r['sample_family'],split='discovery',schema=r['schema'],
            request_hash=template['model_independent_request_hash'],runtime_lock_sha256=lockhash,parent_ancestry=ancestry,
            actual_payload_hash=digest(r['payload']),actual_payload=r['payload'],slurm_job_id=job,shard=sid,
            review_status=c['review']['default_review_status'],scientific_review_grade='AUTO_ONLY_PROVISIONAL',
            raw_response='',first_retained_response=True,physical_cache_reused=False)
        attempts=list((dest/'attempts').glob(rid+'.*.json')) if (dest/'attempts').exists() else []
        if len(attempts)>c['resources']['infrastructure_retry_max']:raise ValueError('INFRA_RETRY_EXHAUSTED')
        try:
            batch,pres,_=pipe.process(r);want=expected[rid]
            if pres['presentation_hash']!=want['presentation_hash']:raise ValueError('MEDIA_PROCESSOR_BRIDGE_FAILED')
            if not ancestry and (pres['rendered_prompt_sha256'],batch['input_ids'][0].tolist())!=(want['rendered_prompt_sha256'],want['input_token_ids']):raise ValueError('STATIC_TEXT_PROCESSOR_BRIDGE_FAILED')
            raw.update(prompt=pres['rendered_prompt'],prompt_hash=pres['rendered_prompt_sha256'],
                visual_tensor_sha256=pres['presentation_hash'],visual_tensors=pres['visual'],text_auxiliary=pres['text_auxiliary'],
                input_token_ids=batch['input_ids'][0].tolist(),attention_mask=batch['attention_mask'][0].tolist(),input_tokens=pres['input_tokens'],
                processor_check='DYNAMIC_ACTUAL_RECORDED_MEDIA_IDENTICAL' if ancestry else 'CPU_GPU_EXACT')
            inputs=batch.to(model.device)
            for d in range(mc['gpus']):torch.cuda.reset_peak_memory_stats(d)
            model.model.rope_deltas=None;t=time.monotonic()
            with torch.inference_mode():generated=model.generate(**inputs,do_sample=False,max_new_tokens=512,use_cache=True)
            for d in range(mc['gpus']):torch.cuda.synchronize(d)
            if not torch.equal(generated[0,:pres['input_tokens']],inputs['input_ids'][0]):raise ValueError('OUTPUT_PREFIX_CHANGED')
            ids,discarded=pipeline_v3.generated_suffix(generated[0].tolist(),pres['input_tokens'],512)
            eos=model.generation_config.eos_token_id or pipe.processor.tokenizer.eos_token_id;eos=[eos] if isinstance(eos,int) else list(eos)
            ended=bool(ids and ids[-1] in eos);truncated=discarded>0 or len(ids)==512 and not ended
            raw.update(raw_response=pipe.processor.decode(ids,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip(),
                output_token_ids=ids,output_tokens=len(ids),discarded_tokens=discarded,truncated=truncated,
                generation_seconds=time.monotonic()-t,peak_memory_bytes=[torch.cuda.max_memory_allocated(d) for d in range(mc['gpus'])],
                finish_reason='length' if truncated else 'eos' if ended else 'stop')
            raw['parsed']=parse(raw['raw_response'],r['schema']);raw['schema_status']=raw['parsed']['status']
            del inputs,batch,generated
        except Exception as exc:
            save(dest/'attempts'/f'{rid}.{job}.json',dict(raw,error=type(exc).__name__+': '+str(exc),first_retained_response=False))
            raise
        raw.update(timestamp=now(),gold_access_audit=dict(audit));save(path,raw);retained[rid]=raw;times.append(raw['generation_seconds'])
        if n<=3 or n%10==0:print(json.dumps(dict(model=a.model,shard=sid,returned=n,planned=len(requests),mean_seconds=sum(times)/len(times))),flush=True)
    checks=[]
    for w in shard['worlds']:
        aa=[retained[r['request_id']] for r in requests if r['world_cluster_id']==w and r['condition'].startswith('A_')]
        sequences=[r['input_token_ids'] for r in aa];upto=0
        for tt in zip(*sequences):
            if len(set(tt))!=1:break
            upto+=1
        common=sequences[0][:upto];text=pipe.processor.tokenizer.decode(common,skip_special_tokens=False,clean_up_tokenization_spaces=False)
        prefix=next(r['shared_observation_prefix'] for r in requests if r['world_cluster_id']==w)
        ok=prefix.rstrip() in text and len({r['visual_tensor_sha256'] for r in aa})==1
        checks.append(dict(world_cluster_id=w,mode='LOGICAL_SHARED_PREFIX',physical_cache_reused=False,
            actual_shared_token_count=upto,actual_shared_token_hash=digest(common),complete_observation_prefix_equal=ok))
    save(dest/'causal_prefix_checks.json',checks)
    index=[dict(request_id=rid,raw_ref=entry(dest/'records'/(rid+'.json'))) for rid in retained]
    save(dest/'response_index.json',index)
    result=dict(status='COMPLETE' if all(r['complete_observation_prefix_equal'] for r in checks) else 'PREFIX_CHECK_FAILED',
        model=a.model,shard=sid,worlds=len(shard['worlds']),planned=len(requests),returned=len(retained),
        invalid=sum(r['schema_status']=='INVALID' for r in retained.values()),gold_access_audit=dict(audit),
        semantic_retries=0,job_id=job,raw_index=entry(dest/'response_index.json'))
    save(dest/'EXECUTION_ACCEPTANCE.json',result);print(json.dumps(result),flush=True)
    if result['status']!='COMPLETE':raise SystemExit(2)


if __name__=='__main__':main()
