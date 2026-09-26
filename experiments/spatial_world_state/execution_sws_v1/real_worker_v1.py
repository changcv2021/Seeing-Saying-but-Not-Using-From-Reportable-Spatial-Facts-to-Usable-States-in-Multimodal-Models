"""One model/shard writer; retain every first answer including null/invalid/wrong."""
import fcntl
import signal
import sys
import time
from common_auto_v2 import *
from contracts import parse
from real_design_v1 import BATCH
from real_processor_v1 import verify

stopping=False


def stop(signum,frame):
    global stopping
    stopping=True


def main():
    p=arguments(__doc__); p.add_argument('--model',required=True); p.add_argument('--shard',type=int)
    a=p.parse_args(); c,root=setup(a)
    if a.model not in c['models']: raise ValueError('UNAUTHORIZED_MODEL')
    sid=a.shard if a.shard is not None else int(os.environ['SLURM_ARRAY_TASK_ID'])
    out=root/'batches'/BATCH; lock=load(out/'manifest/REQUEST_LOCK.json'); verify(lock['code']+lock['public_inputs'])
    auth=load(root/'scheduler/resource_authorization.json')
    if not auth['approved'] or a.model not in auth['models']: raise ValueError('NO_RESOURCE_AUTHORIZATION')
    shards=load(out/'manifest/shards.json'); shard=next(r for r in shards if r['shard']==sid)
    requests=list(rows(shard['request_file']['path']))
    pre=load(out/'review'/a.model/'PROCESSOR_ACCEPTANCE.json')
    if pre['status']!='PASS': raise ValueError('ACTUAL_PROCESSOR_FAILED')
    verify([pre['records'],pre['request_lock']])
    if a.dry_run: print(json.dumps(dict(model=a.model,shard=sid,requests=len(requests),human_gate=False))); return
    directory=out/'raw'/a.model/f'shard_{sid:03}'; directory.mkdir(parents=True,exist_ok=True)
    owner=(directory/'writer.lock').open('a'); fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGUSR1,stop)
    sys.path.insert(0,str(Path(c['project'])/'src'))
    sys.path.insert(0,str(Path(c['project'])/'research/state_binding_phase_a1/core_execution_v3'))
    import pipeline_v3, importlib.util
    spec=importlib.util.spec_from_file_location('sws_real_gpu_health',Path(c['project'])/'scripts/full_multimodel_split_v5/gpu_health.py')
    health=importlib.util.module_from_spec(spec); spec.loader.exec_module(health); health.check(directory)
    inventory=load(Path(c['b0'])/'manifest/model_inventory.json'); mc0=next(m for m in inventory if m['key']==a.model)
    verify([mc0[k] for k in ('manifest','index','config')])
    if any(not Path(r['path']).is_file() or Path(r['path']).stat().st_size!=r['bytes'] for r in mc0['shard_sizes']): raise ValueError('MODEL_SHARD_SIZE_CHANGED')
    audit=pipeline_v3.install_gold_guard()
    import torch, transformers
    from transformers import AutoModelForMultimodalLM
    torch.manual_seed(c['seed']); torch.cuda.manual_seed_all(c['seed']); torch.set_float32_matmul_precision('high')
    pipe=pipeline_v3.Pipeline(dict(c,visual_hash_version='PURE_MEDIA_TENSORS_V3_SHARED_RUNTIME'),a.model); mc=pipe.mc
    if torch.cuda.device_count()!=mc['gpus']: raise ValueError('MODEL_GPU_ALLOCATION_MISMATCH')
    kw=dict(local_files_only=True,dtype=torch.bfloat16,low_cpu_mem_usage=True,attn_implementation='sdpa')
    if mc['gpus']==1: kw['device_map']='cuda'
    else: kw.update(device_map='balanced',max_memory={i:'38GiB' for i in range(mc['gpus'])})
    started=time.monotonic(); model=AutoModelForMultimodalLM.from_pretrained(mc['model_path'],**kw); model.eval(); load_seconds=time.monotonic()-started
    if any(str(v) in ('cpu','disk') for v in getattr(model,'hf_device_map',{}).values()): raise ValueError('CPU_OFFLOAD_NOT_ALLOWED')
    eos=model.generation_config.eos_token_id or pipe.processor.tokenizer.eos_token_id
    eos=[eos] if isinstance(eos,int) else list(eos)
    job=os.environ['SLURM_JOB_ID']; task=os.environ.get('SLURM_ARRAY_TASK_ID'); lockhash=sha(out/'manifest/REQUEST_LOCK.json')
    save(directory/f'environment_{job}_{task}.json',dict(model=mc,model_revision=mc['revision'],job_id=job,array_task_id=task,
        torch=torch.__version__,transformers=transformers.__version__,cuda=torch.version.cuda,
        device_map=getattr(model,'hf_device_map',{}),allocated_gpu_uuids=health.allocated_uuids(),load_seconds=load_seconds,
        source_lock_sha256=lockhash,generation=c['generation'],processor_configuration=pipe.processor.to_dict(),
        chat_template_sha256=digest(pipe.processor.chat_template),media_budget=pipe.campaign['media_budget']))
    need={r['request_id'] for r in requests}; preflight={r['request_id']:r for r in rows(pre['records']['path']) if r['request_id'] in need}
    current=[]; times=[]; previous_world=None
    for n,r in enumerate(requests,1):
        if stopping: raise SystemExit('SIGNAL_CHECKPOINT_STOP')
        rid=r['request_id']; dest=directory/'records'/(rid+'.json')
        if dest.exists():
            raw=load(dest)
            if raw['request_hash']!=r['model_independent_request_hash'] or raw['runtime_lock_sha256']!=lockhash: raise ValueError('RETAINED_RESPONSE_LOCK_MISMATCH')
            current.append(raw); continue
        attempts=list((directory/'attempts').glob(rid+'.*.json')) if (directory/'attempts').exists() else []
        if len(attempts)>c['resources']['infrastructure_retry_max']: raise ValueError('INFRASTRUCTURE_RETRY_ENVELOPE_EXHAUSTED')
        raw=dict(request_id=rid,model_id=a.model,model_repo=mc['model'],model_revision=mc['revision'],run_id=c['run_id'],batch=BATCH,
                 shard=sid,experiment=r['experiment'],logical_bundle_id=r['logical_bundle_id'],world_cluster_id=r['world_cluster_id'],
                 split=r['split'],sample_family=r['sample_family'],schema=r['schema'],review_status=r['review_status'],
                 scientific_review_grade='AUTO_ONLY_PROVISIONAL',requested_tokens=r['requested_tokens'],request_hash=r['model_independent_request_hash'],
                 runtime_lock_sha256=lockhash,physical_attempt=len(attempts)+1,first_retained_response=True,
                 slurm_job_id=job,slurm_array_task_id=task,raw_response='',infrastructure_error=None,
                 information_role=r['information_role'],target_state=r['target_state'],queried_fact_id=r['queried_fact_id'])
        try:
            if previous_world!=r['world_cluster_id']: pipe.image_cache.clear(); previous_world=r['world_cluster_id']
            batch,pres,_=pipe.process(r); want=preflight[rid]
            if (pres['presentation_hash'],pres['rendered_prompt_sha256'],batch['input_ids'][0].tolist())!=(want['presentation_hash'],want['rendered_prompt_sha256'],want['input_token_ids']):
                raise ValueError('ACTUAL_CPU_GPU_PROCESSOR_MISMATCH')
            raw.update(prompt=pres['rendered_prompt'],prompt_hash=pres['rendered_prompt_sha256'],media_refs=r['payload']['media'],
                visual_tensor_sha256=pres['presentation_hash'],visual_tensors=pres['visual'],text_auxiliary=pres['text_auxiliary'],
                input_token_ids=batch['input_ids'][0].tolist(),attention_mask=batch['attention_mask'][0].tolist(),
                input_tokens=pres['input_tokens'],processor_revision=mc['revision'])
            inputs=batch.to(model.device)
            for d in range(mc['gpus']): torch.cuda.reset_peak_memory_stats(d); torch.cuda.synchronize(d)
            t=time.monotonic()
            with torch.inference_mode(): generated=model.generate(**inputs,do_sample=False,max_new_tokens=r['requested_tokens'],use_cache=True)
            for d in range(mc['gpus']): torch.cuda.synchronize(d)
            elapsed=time.monotonic()-t
            if not torch.equal(generated[0,:pres['input_tokens']],inputs['input_ids'][0]): raise ValueError('OUTPUT_PREFIX_CHANGED')
            ids,discarded=pipeline_v3.generated_suffix(generated[0].tolist(),pres['input_tokens'],r['requested_tokens'])
            ended=bool(ids and ids[-1] in eos); truncated=discarded>0 or len(ids)==r['requested_tokens'] and not ended
            raw.update(raw_response=pipe.processor.decode(ids,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip(),
                output_token_ids=ids,output_tokens=len(ids),discarded_tokens=discarded,truncated=truncated,
                finish_reason='length' if truncated else 'eos' if ended else 'stop',generation_seconds=elapsed,
                peak_memory_bytes=[torch.cuda.max_memory_allocated(d) for d in range(mc['gpus'])])
            raw['parsed']=parse(raw['raw_response'],r['schema']); raw['schema_status']=raw['parsed']['status']; raw['actual_key_order']=raw['parsed']['actual_key_order']
            del inputs,batch,generated
        except Exception as exc:
            raw.update(infrastructure_error=type(exc).__name__+': '+str(exc),finish_reason='infrastructure_error',first_retained_response=False)
            save(directory/'attempts'/f'{rid}.{job}_{task}.json',dict(raw,timestamp=now(),gold_access_audit=dict(audit)))
            raise
        raw.update(timestamp=now(),gold_access_audit=dict(audit)); save(dest,raw); current.append(raw); times.append(raw['generation_seconds'])
        if n<=3 or n%10==0:
            progress=dict(stage='REAL_INFERENCE',model=a.model,shard=sid,retained=len(current),expected=len(requests),
                generation_seconds_sum=sum(times),mean_seconds=sum(times)/len(times),job_id=job,
                peak_memory_bytes=raw['peak_memory_bytes'],semantic_success_not_a_gate=True)
            save(directory/'progress'/f'{job}_{task}_{n:05}.json',progress); print(json.dumps(progress),flush=True)
    idx=[dict(request_id=r['request_id'],raw_path=str(directory/'records'/(r['request_id']+'.json')),
              raw_sha256=sha(directory/'records'/(r['request_id']+'.json'))) for r in current]
    save(directory/'response_index.json',idx)
    save(directory/'EXECUTION_ACCEPTANCE.json',dict(status='COMPLETE',model=a.model,shard=sid,planned=len(requests),returned=len(current),
        worlds=len({r['world_cluster_id'] for r in requests}),job_id=job,array_task_id=task,private_gold_open_attempts=audit['private_gold_open_attempts'],
        request_lock_sha256=lockhash,raw_index=entry(directory/'response_index.json'),
        invalid=sum(r['schema_status']=='INVALID' for r in current),truncated=sum(r['truncated'] for r in current)))
    print(json.dumps(dict(status='REAL_SHARD_GENERATED',model=a.model,shard=sid,returned=len(current))),flush=True)


if __name__=='__main__': main()
