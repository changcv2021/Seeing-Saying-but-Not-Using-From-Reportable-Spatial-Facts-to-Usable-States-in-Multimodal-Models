"""One retained response per frozen request; smoke then own-model E9, no cross-model wait."""
import fcntl
import signal
import sys
import time
from common import *
from contracts import parse

stopping=False
def stop(signum,frame):
    global stopping
    stopping=True

def check_entries(items):
    for r in items:
        if sha(r['path'])!=r['sha256'].removeprefix('sha256:'): raise ValueError('FROZEN_FILE_CHANGED:'+r['path'])

def main():
    p=arguments(__doc__); p.add_argument('--model',required=True); p.add_argument('--stage',choices=['smoke_e9','smoke'],default='smoke_e9'); a=p.parse_args(); c,root=setup(a)
    if a.model not in c['models']: raise ValueError('UNAPPROVED_MODEL')
    auth=load(root/'scheduler/resource_authorization.json')
    if not auth.get('approved') or auth['run_id']!=c['run_id'] or a.model not in auth['models']: raise ValueError('AUTHORIZATION_MISSING')
    lock=load(root/'manifest/gpu_runtime_lock_v1.json'); check_entries(lock['code']+lock['inputs'])
    if a.dry_run: print(json.dumps(dict(status='DRY_RUN',model=a.model,smoke=12,E9=768 if a.stage=='smoke_e9' else 0))); return
    model_folder=root/'raw'/a.model
    model_folder.mkdir(parents=True,exist_ok=True)
    # Scope-local lock prevents duplicate writers. Independent models never share this lock.
    owner=(model_folder/'writer.lock').open('a')
    fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGUSR1,stop)
    project=Path(c['project']); sys.path.insert(0,str(project/'src'))
    sys.path.insert(0,str(project/'research/state_binding_phase_a1/core_execution_v3'))
    import pipeline_v3
    import importlib.util
    spec=importlib.util.spec_from_file_location('sws_allocated_gpu_health',project/'scripts/full_multimodel_split_v5/gpu_health.py')
    health=importlib.util.module_from_spec(spec); spec.loader.exec_module(health)
    health.check(model_folder)
    model_inventory=load(Path(c['b0'])/'manifest/model_inventory.json')
    mc0=next(m for m in model_inventory if m['key']==a.model)
    check_entries([mc0[k] for k in ('manifest','index','config')])
    if any(not Path(s['path']).is_file() or Path(s['path']).stat().st_size!=s['bytes'] for s in mc0['shard_sizes']): raise ValueError('MODEL_SHARD_SIZE_CHANGED')
    audit=pipeline_v3.install_gold_guard()
    import torch
    import transformers
    from transformers import AutoModelForMultimodalLM
    torch.manual_seed(c['seed']); torch.cuda.manual_seed_all(c['seed']); torch.set_float32_matmul_precision('high')
    runtime=dict(c,visual_hash_version='PURE_MEDIA_TENSORS_V3_SHARED_RUNTIME')
    pipeline=pipeline_v3.Pipeline(runtime,a.model); mc=pipeline.mc
    if torch.cuda.device_count()!=mc['gpus']: raise ValueError('GPU_ALLOCATION_MODEL_MISMATCH')
    kw=dict(local_files_only=True,dtype=torch.bfloat16,low_cpu_mem_usage=True,attn_implementation='sdpa')
    if mc['gpus']==1: kw['device_map']='cuda'
    else: kw.update(device_map='balanced',max_memory={i:'38GiB' for i in range(mc['gpus'])})
    start=time.monotonic(); model=AutoModelForMultimodalLM.from_pretrained(mc['model_path'],**kw); model.eval(); load_seconds=time.monotonic()-start
    if any(str(v) in ('cpu','disk') for v in getattr(model,'hf_device_map',{}).values()): raise ValueError('CPU_DISK_OFFLOAD_NOT_ALLOWED')
    eos=model.generation_config.eos_token_id or pipeline.processor.tokenizer.eos_token_id; eos=[eos] if isinstance(eos,int) else list(eos)
    job=os.environ['SLURM_JOB_ID']
    env=dict(run_id=c['run_id'],model=mc,job_id=job,torch=torch.__version__,transformers=transformers.__version__,cuda=torch.version.cuda,
             model_config_sha256=sha(mc0['config']['path']),model_revision=mc['revision'],device_map=getattr(model,'hf_device_map',{}),
             allocated_gpu_uuids=health.allocated_uuids(),load_seconds=load_seconds,source_lock_sha256=sha(root/'manifest/gpu_runtime_lock_v1.json'),
             authorization=auth['authorization_id'],generation=c['generation'],processor_configuration=pipeline.processor.to_dict(),
             chat_template_sha256=digest(pipeline.processor.chat_template),media_budget=pipeline.campaign['media_budget'])
    save(root/'reproducibility'/a.model/f'environment_{job}.json',env)
    smoke=list(rows(root/'public_inputs/smoke/requests.jsonl'))
    preflight={r['request_id']:r for r in rows(root/'review/smoke'/f'{a.model}_processor.jsonl')}
    smoke_results=[]; generated_total=0
    for stage,requests in [('smoke',smoke)]+([('E9',list(rows(root/'public_inputs/E9/requests.jsonl')))] if a.stage=='smoke_e9' else []):
        current=[]
        if stage=='E9':
            smoke_gate=load(root/'reports'/f'GPU_SMOKE_{a.model}.json')
            if smoke_gate['status']!='PASS': raise ValueError('OWN_MODEL_INFRASTRUCTURE_SMOKE_NOT_PASSED')
        for n,r in enumerate(requests,1):
            if stopping: raise SystemExit('SIGNAL_CHECKPOINT_STOP_NO_NEW_REQUEST')
            rid=r['request_id']; path=model_folder/'records'/(rid+'.json')
            if path.exists():
                raw=load(path)
                if raw['request_hash']!=r['model_independent_request_hash'] or raw['runtime_lock_sha256']!=sha(root/'manifest/gpu_runtime_lock_v1.json'): raise ValueError('RETAINED_RESPONSE_PROTOCOL_MISMATCH')
                current.append(raw); continue
            attempts=list((model_folder/'attempts').glob(rid+'.*.json')) if (model_folder/'attempts').exists() else []
            if len(attempts)>2: raise ValueError('INFRASTRUCTURE_ATTEMPTS_EXHAUSTED')
            raw=dict(request_id=rid,model_id=a.model,model_repo=mc['model'],model_revision=mc['revision'],run_id=c['run_id'],experiment=r['experiment'],
                     stage_first_executed=stage,logical_bundle_id=r['logical_bundle_id'],world_cluster_id=r['world_cluster_id'],split=r['split'],
                     sample_family=r['sample_family'],schema=r['schema'],review_status=r['review_status'],requested_tokens=r['requested_tokens'],
                     request_hash=r['model_independent_request_hash'],runtime_lock_sha256=sha(root/'manifest/gpu_runtime_lock_v1.json'),
                     physical_attempt=len(attempts)+1,first_retained_response=True,slurm_job_id=job,raw_response='',infrastructure_error=None,
                     information_role=r.get('information_role'),target_state=r.get('target_state'),queried_fact_id=r.get('queried_fact_id'))
            try:
                batch,pres,_=pipeline.process(r)
                if rid in preflight:
                    want=preflight[rid]
                    if (pres['presentation_hash'],pres['rendered_prompt_sha256'],batch['input_ids'][0].tolist())!=(want['presentation_hash'],want['rendered_prompt_sha256'],want['input_token_ids']): raise ValueError('CPU_GPU_PROCESSOR_BRIDGE_MISMATCH')
                raw.update(prompt=pres['rendered_prompt'],prompt_hash=pres['rendered_prompt_sha256'],media_refs=r['payload']['media'],
                           visual_tensor_sha256=pres['presentation_hash'],visual_tensors=pres['visual'],text_auxiliary=pres['text_auxiliary'],
                           input_token_ids=batch['input_ids'][0].tolist(),attention_mask=batch['attention_mask'][0].tolist(),
                           input_tokens=pres['input_tokens'],processor_revision=mc['revision'])
                inputs=batch.to(model.device)
                for d in range(mc['gpus']): torch.cuda.reset_peak_memory_stats(d); torch.cuda.synchronize(d)
                t=time.monotonic()
                with torch.inference_mode(): out=model.generate(**inputs,do_sample=False,max_new_tokens=r['requested_tokens'],use_cache=True)
                for d in range(mc['gpus']): torch.cuda.synchronize(d)
                elapsed=time.monotonic()-t
                if not torch.equal(out[0,:pres['input_tokens']],inputs['input_ids'][0]): raise ValueError('OUTPUT_PREFIX_CHANGED')
                ids,discarded=pipeline_v3.generated_suffix(out[0].tolist(),pres['input_tokens'],r['requested_tokens'])
                ended=bool(ids and ids[-1] in eos); truncated=discarded>0 or len(ids)==r['requested_tokens'] and not ended
                raw.update(raw_response=pipeline.processor.decode(ids,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip(),
                           output_token_ids=ids,output_tokens=len(ids),discarded_tokens=discarded,truncated=truncated,
                           finish_reason='length' if truncated else 'eos' if ended else 'stop',generation_seconds=elapsed,
                           peak_memory_bytes=[torch.cuda.max_memory_allocated(d) for d in range(mc['gpus'])])
                raw['parsed']=parse(raw['raw_response'],r['schema']); raw['schema_status']=raw['parsed']['status']
                raw['actual_key_order']=raw['parsed']['actual_key_order']; generated_total+=1
                del batch,inputs,out
            except Exception as exc:
                raw.update(infrastructure_error=type(exc).__name__+': '+str(exc),finish_reason='infrastructure_error',first_retained_response=False)
                save(model_folder/'attempts'/f'{rid}.{job}.json',dict(raw,timestamp=now(),gold_access_audit=dict(audit)))
                raise
            raw.update(timestamp=now(),gold_access_audit=dict(audit)); save(path,raw); current.append(raw)
            if n%25==0 or stage=='smoke':
                progress=dict(stage=stage,model=a.model,retained=len(current),expected=len(requests),generated_this_job=generated_total,job_id=job)
                save(model_folder/'progress'/f'{stage}_{job}_{n:04}.json',progress); print(json.dumps(progress),flush=True)
        save(model_folder/f'{stage}_response_index.json',[dict(request_id=x['request_id'],raw_path=str(model_folder/'records'/(x['request_id']+'.json')),raw_sha256=sha(model_folder/'records'/(x['request_id']+'.json'))) for x in current])
        if stage=='smoke':
            # Semantic accuracy/null/invalid are not retries or hardware gates. Preserve and score them.
            gate=dict(status='PASS',model=a.model,requests=len(current),CPU_GPU_processor_bridge='PASS',
                      schema_status_counts={v:sum(x['schema_status']==v for x in current) for v in ['VALID','INVALID']},
                      semantics_used_as_gate=False,invalid_or_null_retry=False,private_gold_open_attempts=audit['private_gold_open_attempts'],
                      load_seconds=load_seconds,generation_seconds=[x['generation_seconds'] for x in current],
                      media_peak_memory_bytes=[x['peak_memory_bytes'] for x in current if x['media_refs']],job_id=job)
            gatepath=root/'reports'/f'GPU_SMOKE_{a.model}.json'
            if not gatepath.exists(): save(gatepath,gate)
        reportpath=root/'reports'/f'{stage}_execution_{a.model}.json'
        if not reportpath.exists():
            save(reportpath,dict(status='GENERATED_NOT_YET_SCORED',model=a.model,requests=len(current),
                requested=len(requests),worlds=len({r['world_cluster_id'] for r in requests}),job_id=job,gold_access_audit=dict(audit),
                index=entry(model_folder/f'{stage}_response_index.json'),generation_count_this_job=generated_total))
    print(json.dumps(dict(status='SMOKE_E9_GENERATED_NOT_SCORED',model=a.model,generated_this_job=generated_total)),flush=True)

if __name__=='__main__': main()
