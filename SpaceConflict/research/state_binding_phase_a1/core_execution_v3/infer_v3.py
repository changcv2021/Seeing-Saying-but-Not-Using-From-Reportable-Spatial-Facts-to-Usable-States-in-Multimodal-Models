"""Frozen request execution, one attempt; input builder and scorer gold are separate."""
import time
from v3common import *
from pipeline_v3 import Pipeline,generated_suffix,install_gold_guard
from score_v3 import parse


def main():
    p=arguments(__doc__); p.add_argument('--model',required=True); p.add_argument('--stage',choices=['precore','core'],required=True)
    a=p.parse_args(); c,root=setup(a)
    if a.model not in c['models']: raise ValueError('UNAPPROVED_MODEL')
    lock=load(root/'manifest'/f'{a.stage}_lock.json')
    if a.stage=='core' and lock.get('status')!='CORE_FROZEN_VERIFIED_FOR_A1': raise ValueError('HUMAN_REVIEW_REQUIRED')
    source=root/'inputs'/a.stage/'requests.jsonl'
    if sha(source)!=lock['inputs_sha256'] or sha(a.config)!=lock['config_sha256']: raise ValueError('LOCK_CHANGED')
    check_entries(lock['code'])
    requests=list(rows(source))
    if len(requests)!=lock['requests_per_model'] or any(r['models']!=c['models'] for r in requests): raise ValueError('PANEL_CHANGED')
    if a.dry_run: print(json.dumps(dict(stage=a.stage,model=a.model,requests=len(requests),status='PLANNED_NOT_GENERATED'))); return
    compute()
    authorization=load(root/'resources'/f'{a.stage}_authorization.json')
    if not authorization.get('approved') or a.model not in authorization['models'] or authorization.get('run_id')!=c['run_id']:
        raise ValueError('THIS_RUN_GPU_BUDGET_NOT_APPROVED')
    if a.stage=='core':
        if sha(root/'review/researcher_records.csv')!=lock['review_sha256']: raise ValueError('REVIEW_CHANGED_AFTER_FREEZE')
    inventory=load(root/'current_state_inventory.json')
    for m in inventory['models']:
        if m['key']==a.model:
            check_entries([m['manifest'],m['index'],m['config']])
            if any(not Path(s['path']).is_file() or Path(s['path']).stat().st_size!=s['bytes'] for s in m['shard_sizes']):
                raise ValueError('MODEL_SHARD_SIZE_CHANGED')
    audit=install_gold_guard()
    import torch
    import transformers
    from transformers import AutoModelForMultimodalLM
    pipeline=Pipeline(c,a.model); mc=pipeline.mc
    if torch.cuda.device_count()!=mc['gpus']: raise ValueError('GPU_COUNT_MISMATCH')
    torch.manual_seed(c['seed']); torch.cuda.manual_seed_all(c['seed']); torch.set_float32_matmul_precision('high')
    kw=dict(local_files_only=True,dtype=torch.bfloat16,low_cpu_mem_usage=True,attn_implementation='sdpa')
    if mc['gpus']==1: kw['device_map']='cuda'
    else: kw.update(device_map='balanced',max_memory={i:'38GiB' for i in range(mc['gpus'])})
    start=time.monotonic(); model=AutoModelForMultimodalLM.from_pretrained(mc['model_path'],**kw); model.eval()
    loaded=time.monotonic()-start
    if any(str(v) in ['cpu','disk'] for v in getattr(model,'hf_device_map',{}).values()): raise ValueError('CPU_DISK_OFFLOAD_FORBIDDEN')
    eos=model.generation_config.eos_token_id or pipeline.processor.tokenizer.eos_token_id
    eos=[eos] if isinstance(eos,int) else list(eos)
    envpath=root/'environments'/a.stage/a.model/(os.environ['SLURM_JOB_ID']+'.json')
    save(envpath,dict(model=mc,torch=torch.__version__,transformers=transformers.__version__,cuda=torch.version.cuda,
        devices=[torch.cuda.get_device_name(i) for i in range(mc['gpus'])],device_map=getattr(model,'hf_device_map',{}),
        generation=c['generation'],load_seconds=loaded,processor_config=pipeline.processor.to_dict(),
        chat_template_sha256=digest(pipeline.processor.chat_template),media_budget=pipeline.campaign['media_budget'],
        config_sha256=sha(a.config),input_sha256=sha(source),visual_hash_version=c['visual_hash_version']))
    outdir=root/'raw'/a.stage/a.model; completed=[]
    for n,r in enumerate(requests,1):
        path=outdir/(r['request_id']+'.json')
        if path.exists():
            previous=load(path)
            if previous['request_sha256']!=digest(r) or previous['lock_sha256']!=sha(root/'manifest'/f'{a.stage}_lock.json'):
                raise ValueError('PRIOR_REQUEST_PROTOCOL_MISMATCH')
            if previous.get('infrastructure_error'): raise ValueError('PRIOR_INFRA_FAILURE_REQUIRES_EXPLICIT_NEW_ATTEMPT')
            completed.append(previous); continue
        started=time.monotonic()
        raw=dict(request_id=r['request_id'],parent_request_id=r['parent_request_id'],group_id=r['group_id'],
                 underlying_world_id=r['underlying_world_id'],level=r['level'],condition=r['condition'],
                 measurement_stage=r['stage'],model=a.model,model_id=mc['model'],model_revision=mc['revision'],
                 run_id=c['run_id'],normal_attempt=1,request_sha256=digest(r),
                 lock_sha256=sha(root/'manifest'/f'{a.stage}_lock.json'),environment_path=str(envpath),environment_sha256=sha(envpath),
                 raw_response='',output_tokens=None,truncated=False,infrastructure_error=None)
        try:
            batch,pres,_=pipeline.process(r)
            expected=root/'review/rendered'/a.model/(r['request_id']+'.json')
            if not expected.is_file(): raise ValueError('ACTUAL_INPUT_PREFLIGHT_MISSING')
            check=load(expected)
            if (pres['presentation_hash'],pres['rendered_prompt_sha256'])!=(check['presentation_hash'],check['rendered_prompt_sha256']):
                raise ValueError('ACTUAL_INPUT_DIFFERS_FROM_REVIEW')
            renderpath=root/'rendered'/a.stage/a.model/(r['request_id']+'.json'); save(renderpath,pres)
            raw.update(presentation_hash=pres['presentation_hash'],rendered_prompt_sha256=pres['rendered_prompt_sha256'],
                       rendered_path=str(renderpath),input_tokens=pres['input_tokens'],max_new_tokens=512,
                       execution_key=digest(dict(revision=mc['revision'],request=digest(r),visual=pres['presentation_hash'],
                                                 prompt=pres['rendered_prompt_sha256'],generation=c['generation'],seed=c['seed'])))
            if 'past_key_values' in batch or 'cache_params' in batch: raise ValueError('CROSS_REQUEST_CACHE')
            inputs=batch.to(model.device)
            for d in range(mc['gpus']): torch.cuda.reset_peak_memory_stats(d)
            torch.cuda.synchronize(); t=time.monotonic()
            with torch.inference_mode(): generated=model.generate(**inputs,do_sample=False,max_new_tokens=512,use_cache=True)
            torch.cuda.synchronize(); generation_seconds=time.monotonic()-t
            if not torch.equal(generated[0,:pres['input_tokens']],inputs['input_ids'][0]):
                raise ValueError('GENERATED_SEQUENCE_INPUT_PREFIX_MISMATCH')
            ids,discarded=generated_suffix(generated[0].tolist(),pres['input_tokens'],512)
            ended=bool(ids and ids[-1] in eos); truncated=discarded>0 or len(ids)==512 and not ended
            raw.update(raw_response=pipeline.processor.decode(ids,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip(),
                       output_token_ids=ids,output_tokens=len(ids),discarded_tokens=discarded,truncated=truncated,
                       finish_reason='length' if truncated else 'eos' if ended else 'stop',generation_seconds=generation_seconds,
                       peak_memory_bytes=[torch.cuda.max_memory_allocated(d) for d in range(mc['gpus'])])
            raw['parse_without_gold']=parse(raw,r['schema'])
            del inputs,batch,generated
        except Exception as exc:
            raw.update(infrastructure_error=type(exc).__name__+': '+str(exc),finish_reason='infrastructure_error')
        raw.update(timestamp_utc=now(),wall_seconds=time.monotonic()-started,gold_access_audit=dict(audit))
        save(path,raw); completed.append(raw)
        save(outdir/'progress.json',dict(status='RUNNING',completed=len(completed),expected=len(requests)),frozen=False)
        print(json.dumps(dict(index=n,total=len(requests),model=a.model,request_id=r['request_id'],error=raw['infrastructure_error'])),flush=True)
        if raw['infrastructure_error']: raise RuntimeError('INFRA_FAILURE_RETAINED_NO_AUTOMATIC_RETRY')
    save(outdir/'completion.json',dict(status='GENERATED',model=a.model,requests=len(completed),
         raw_index=[entry(outdir/(r['request_id']+'.json')) for r in completed],load_seconds=loaded,gold_access_audit=audit))
    save(outdir/'progress.json',dict(status='GENERATED',completed=len(completed),expected=len(requests)),frozen=False)


if __name__=='__main__': main()
