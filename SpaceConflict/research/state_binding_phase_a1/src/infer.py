"""A1 isolated inference, adapting the Phase A loader/processor/media/token path.

This process opens public request manifests only, never private gold or old responses.
"""
import importlib.util
import time
from common import *

def tensor_hash(tensor):
    import torch
    return hashlib.sha256(tensor.detach().contiguous().cpu().view(torch.uint8).numpy().tobytes()).hexdigest()

def main():
    p=arguments(__doc__); p.add_argument('--model',required=True); p.add_argument('--stage',choices=['setup_v1','core'],required=True)
    a=p.parse_args(); cfg,root=setup(a)
    if a.model not in cfg['models']: raise ValueError('UNAUTHORIZED_MODEL')
    lock=load(root/('manifest/setup_v1_lock.json' if a.stage=='setup_v1' else 'protocol_lock_a1.json'))
    if a.stage=='core' and lock.get('status')!='CORE_FROZEN_VERIFIED_FOR_A1': raise ValueError('REVIEW_OR_CALIBRATION_NOT_PASSED')
    manifest=root/'inputs'/a.stage/'requests.jsonl'
    if sha(manifest)!=lock['inputs_sha256']: raise ValueError('REQUEST_FREEZE_CHANGED')
    if sha(a.config)!=lock['config_sha256']: raise ValueError('CONFIG_CHANGED')
    for src in lock['code']:
        if sha(src['path'])!=src['sha256']: raise ValueError('FROZEN_CODE_CHANGED:'+src['path'])
    req=list(rows(manifest))
    if not all(r['models']==cfg['models'] for r in req): raise ValueError('MODEL_PANELS_DIFFER')
    if a.stage=='setup_v1' and any(r['level']!='SETUP_ONLY' or r['payload']['media'] for r in req): raise ValueError('REAL_INPUT_IN_SETUP')
    if a.dry_run: print(json.dumps(dict(status='PLANNED',model=a.model,requests=len(req),stage=a.stage))); return
    require_compute()
    campaign=load(Path(cfg['campaign'])/'config.json')
    mc=next(m for m in campaign['models'] if m['key']==a.model)
    mm=load(mc['manifest_path'])
    if (mm['model_id'],mm['revision'])!=(mc['model'],mc['revision']): raise ValueError('MODEL_REVISION_MISMATCH')
    legacy=Path(cfg['campaign'])/'code'; sys.path.insert(0,str(legacy))
    from protocol import messages_for
    import torch
    import transformers
    from transformers import AutoModelForMultimodalLM, AutoProcessor
    if torch.cuda.device_count()!=mc['gpus']: raise ValueError('GPU_COUNT_MISMATCH')
    helper=legacy/'vision_process_frozen.py'
    if sha(helper)!=campaign['vision_helper_sha256']: raise ValueError('VISION_HELPER_CHANGED')
    spec=importlib.util.spec_from_file_location('a1_vision',helper); vision=importlib.util.module_from_spec(spec); spec.loader.exec_module(vision)
    processor=AutoProcessor.from_pretrained(mc['model_path'],local_files_only=True,use_fast=True)
    torch.manual_seed(cfg['seed']); torch.cuda.manual_seed_all(cfg['seed']); torch.set_float32_matmul_precision('high')
    kw=dict(local_files_only=True,dtype=torch.bfloat16,low_cpu_mem_usage=True,attn_implementation='sdpa')
    if mc['gpus']==1: kw['device_map']='cuda'
    else: kw.update(device_map='balanced',max_memory={i:'38GiB' for i in range(mc['gpus'])})
    begin=time.monotonic(); model=AutoModelForMultimodalLM.from_pretrained(mc['model_path'],**kw); model.eval(); load_seconds=time.monotonic()-begin
    if any(str(v) in ('cpu','disk') for v in getattr(model,'hf_device_map',{}).values()): raise ValueError('NO_CPU_DISK_OFFLOAD')
    eos=model.generation_config.eos_token_id or processor.tokenizer.eos_token_id; eos=[eos] if isinstance(eos,int) else list(eos)
    directory=root/'raw'/a.stage/a.model
    envpath=directory/'environments'/('job_'+os.environ['SLURM_JOB_ID']+'.json')
    save(envpath,dict(model=mc,load_seconds=load_seconds,torch=torch.__version__,transformers=transformers.__version__,
        cuda=torch.version.cuda,devices=[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
        device_map=getattr(model,'hf_device_map',{}),processor_config=processor.to_dict(),chat_template_sha256=digest(processor.chat_template),
        media_budget=campaign['media_budget'],vision_helper_sha256=sha(helper),legacy_protocol_sha256=sha(legacy/'protocol.py'),
        code_sha256=sha(__file__),config_sha256=sha(a.config),inputs_sha256=sha(manifest),
        generation=dict(enable_thinking=False,do_sample=False,max_new_tokens=cfg['max_new_tokens'],dtype='bfloat16',backend='sdpa',quantization=None)),frozen=True)
    completed=[]
    for i,r in enumerate(req,1):
        start=time.monotonic(); output=directory/(r['request_id']+'.json')
        result=dict(request_id=r['request_id'],run_id=cfg['run_id'],model=a.model,model_id=mc['model'],model_revision=mc['revision'],
            stage=a.stage,condition=r['condition'],group_id=r['group_id'],cluster_id=r['cluster_id'],level=r['level'],
            attempt_id=1,seed=cfg['seed'],max_new_tokens=cfg['max_new_tokens'],environment_path=str(envpath),environment_sha256=sha(envpath))
        try:
            messages=messages_for(dict(level='L1',claim_text='',media=r['payload']['media']),campaign['media_budget'])
            messages[0]['content']=r['payload']['system']; messages[1]['content'][-1]=dict(type='text',text=r['payload']['text'])
            rendered=processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
            if '<think>' in rendered and '</think>' not in rendered: raise ValueError('THINKING_MODE_OPEN')
            images,videos,vkwargs=vision.process_vision_info(messages,image_patch_size=16,return_video_kwargs=True,return_video_metadata=True)
            kwargs=dict(text=[rendered],images=images,return_tensors='pt',do_resize=False)
            if videos:
                tensors,metadata=zip(*videos); kwargs.update(videos=list(tensors),video_metadata=list(metadata),**vkwargs)
            inputs_cpu=processor(**kwargs)
            visual={k:dict(shape=list(v.shape),dtype=str(v.dtype),sha256=tensor_hash(v)) for k,v in inputs_cpu.items() if torch.is_tensor(v) and k not in ['input_ids','attention_mask']}
            ph=digest(visual); th=hashlib.sha256(rendered.encode()).hexdigest()
            key=digest(dict(revision=mc['revision'],request=r,presentation_hash=ph,prompt_hash=th,seed=cfg['seed'],cap=cfg['max_new_tokens']))
            result.update(execution_key=key,presentation_hash=ph,rendered_prompt_sha256=th)
            if output.exists():
                previous=load(output)
                if previous['execution_key']!=key: raise ValueError('ACTUAL_INPUT_CACHE_KEY_MISMATCH')
                if previous.get('infrastructure_error'): raise ValueError('PRIOR_FAILURE_REQUIRES_EXPLICIT_NEW_ATTEMPT_NO_SILENT_RETRY')
                completed.append(previous); continue
            review=root/'review/actual_presentations'/ph
            if not (review/'manifest.json').exists():
                review.mkdir(parents=True,exist_ok=True); imagefiles=[]
                for j,img in enumerate(images or []):
                    f=review/f'image_{j:03d}.png'; img.save(f); imagefiles.append(str(f.relative_to(root)))
                if videos: raise ValueError('A1_PANEL_EXPECTS_STILL_IMAGES_ONLY')
                save(review/'manifest.json',dict(visual=visual,images=imagefiles,media=r['payload']['media'],processor_resize=False,
                    source='EXACT_VISION_HELPER_OUTPUT_WITH_PROCESSOR_TENSOR_HASHES'),frozen=True)
            save(root/'rendered'/a.stage/a.model/(r['request_id']+'.json'),dict(messages=messages,rendered_prompt=rendered,
                rendered_prompt_sha256=th,visual=visual,presentation_hash=ph),frozen=True)
            prompt_tokens=int(inputs_cpu['input_ids'].shape[-1]); inputs=inputs_cpu.to(model.device)
            if 'past_key_values' in inputs or 'cache_params' in inputs: raise ValueError('CROSS_REQUEST_CACHE_FORBIDDEN')
            for device in range(torch.cuda.device_count()): torch.cuda.reset_peak_memory_stats(device)
            torch.cuda.synchronize(); t=time.monotonic()
            with torch.inference_mode(): generated=model.generate(**inputs,do_sample=False,max_new_tokens=cfg['max_new_tokens'],use_cache=True)
            torch.cuda.synchronize(); seconds=time.monotonic()-t
            count=int(generated.shape[-1]-prompt_tokens); tokens=generated[0,prompt_tokens:prompt_tokens+cfg['max_new_tokens']]; ids=tokens.tolist()
            ended=bool(ids and ids[-1] in eos); truncated=count>cfg['max_new_tokens'] or (len(ids)==cfg['max_new_tokens'] and not ended)
            result.update(raw_response=processor.decode(tokens,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip(),
                output_token_ids=ids,input_tokens=prompt_tokens,output_tokens=len(ids),finish_reason='length' if truncated else 'eos' if ended else 'stop',
                truncated=truncated,discarded_tokens=max(0,count-len(ids)),generation_seconds=seconds,
                peak_memory_bytes=[torch.cuda.max_memory_allocated(j) for j in range(torch.cuda.device_count())],infrastructure_error=None)
            del inputs,inputs_cpu,generated,tokens
        except Exception as exc:
            result.update(raw_response='',infrastructure_error=f'{type(exc).__name__}: {exc}',output_tokens=None,finish_reason='infrastructure_error')
        result.update(wall_seconds=time.monotonic()-start,timestamp_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
        save(output,result,frozen=True); completed.append(result)
        save(directory/'progress.json',dict(status='RUNNING',completed=len(completed),expected=len(req)))
        print(json.dumps(dict(index=i,total=len(req),request_id=r['request_id'],error=result.get('infrastructure_error'),seconds=result['wall_seconds'])),flush=True)
        if result.get('infrastructure_error'): raise RuntimeError('INFRASTRUCTURE_ERROR_STOP_NO_SILENT_SKIP')
    save(directory/'completion.json',dict(status='COMPLETE',requests=len(completed),expected=len(req),load_seconds=load_seconds,
        inference_seconds=sum(r['wall_seconds'] for r in completed),gpus=mc['gpus'],raw_index=[entry(directory/(r['request_id']+'.json')) for r in completed]),frozen=True)
    save(directory/'progress.json',dict(status='COMPLETE',completed=len(completed),expected=len(req)))

if __name__=='__main__': main()
