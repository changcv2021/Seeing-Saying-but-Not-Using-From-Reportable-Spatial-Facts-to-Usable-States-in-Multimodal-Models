"""Phase A isolated inference. This module never opens private gold or state truths."""
import importlib.util
import time
from base import *
from request_identity import execution_identity

def tensor_hash(tensor):
    t=tensor.detach().contiguous().cpu()
    # Byte view supports BF16 without NumPy's BF16 dtype support.
    return hashlib.sha256(t.view(__import__('torch').uint8).numpy().tobytes()).hexdigest()

def main():
    p=args(__doc__); p.add_argument('--phase',choices=['measure','smoke','run'],required=True); p.add_argument('--model',required=True)
    a=p.parse_args(); cfg,root,project=setup(a)
    stage='setup' if a.phase=='measure' else cfg.get('setup_input_stage','setup') if a.phase=='smoke' else 'discovery'
    output_stage='measurement' if a.phase=='measure' else stage
    if a.model not in cfg['models']: raise ValueError('UNAUTHORIZED_MODEL')
    if stage=='discovery':
        resource=load(root/'manifest/resource_plan.json')
        if resource['status']!='PASS' or not resource['budget_authorized']: raise ValueError('UNRESOLVED_BATCH_BUDGET')
        freeze=load(root/'manifest/discovery_execution_freeze.json')
        if freeze['status']!='PASS': raise ValueError('DISCOVERY_PREFLIGHT_NOT_PASS')
        for dep in freeze['dependencies']:
            if not dep['available'] or sha(dep['path'])!=dep['sha256']: raise ValueError('FROZEN_INFERENCE_DEPENDENCY_CHANGED:'+dep['path'])
    file=root/'inputs'/stage/'requests.jsonl'; plan=load(root/'manifest'/stage/'request_plan.json')
    if sha(file)!=plan['input_hash']: raise ValueError('FROZEN_REQUEST_HASH_CHANGED')
    req=[r for r in rows(file) if a.model in r['models']]
    if stage.startswith('setup'):
        smoke=load(root/'manifest'/stage/'smoke_requests.json')
        if smoke['requests_hash']!=sha(file): raise ValueError('SMOKE_INPUT_HASH_CHANGED')
        byid={r['request_id']:r for r in req}
        chosen=smoke['measurement_request_ids'] if a.phase=='measure' else smoke['request_ids']
        req=[byid[rid] for rid in chosen if rid in byid]
    if a.limit: raise ValueError('USE_PREDECLARED_MANIFEST_NOT_POSTHOC_REQUEST_LIMIT')
    if not req: raise ValueError('NO_REQUESTS')
    if a.dry_run: print(json.dumps(dict(status='PLANNED',stage=stage,model=a.model,requests=len(req)))); return
    auth=root/'manifest'/('minimal_measurement_authorization.json' if a.phase=='measure' else 'gpu_authorization.json')
    if not auth.exists() or not load(auth).get('smoke_authorized'): raise ValueError('GPU_AUTHORIZATION_NOT_RECORDED')
    if a.phase=='measure' and (len(req)>10 or load(auth).get('scope')!='MINIMAL_SETUP_MEASUREMENT_ONLY'): raise ValueError('MINIMAL_MEASUREMENT_SCOPE_EXCEEDED')
    model_cfg=next(m for m in load(Path(cfg['campaign'])/'config.json')['models'] if m['key']==a.model)
    legacy_code=Path(cfg['campaign'])/'code'; sys.path.insert(0,str(legacy_code))
    from protocol import messages_for
    import torch
    import transformers
    from transformers import AutoModelForMultimodalLM, AutoProcessor
    if torch.cuda.device_count()!=model_cfg['gpus']: raise ValueError('GPU_COUNT_MISMATCH')
    manifest=load(model_cfg['manifest_path'])
    if (manifest['model_id'],manifest['revision'])!=(model_cfg['model'],model_cfg['revision']): raise ValueError('MODEL_MANIFEST_MISMATCH')
    prior=load(Path(cfg['campaign'])/'config.json'); budget=prior['media_budget']
    helper=legacy_code/'vision_process_frozen.py'
    if sha(helper)!=prior['vision_helper_sha256']: raise ValueError('VISION_HELPER_HASH_CHANGED')
    spec=importlib.util.spec_from_file_location('phase_a_vision',helper); vision=importlib.util.module_from_spec(spec); spec.loader.exec_module(vision)
    torch.manual_seed(cfg['seed']); torch.cuda.manual_seed_all(cfg['seed']); torch.set_float32_matmul_precision('high')
    processor=AutoProcessor.from_pretrained(model_cfg['model_path'],local_files_only=True,use_fast=True)
    kw=dict(local_files_only=True,dtype=torch.bfloat16,low_cpu_mem_usage=True,attn_implementation='sdpa')
    if model_cfg['gpus']==1: kw['device_map']='cuda'
    else: kw.update(device_map='balanced',max_memory={i:'38GiB' for i in range(model_cfg['gpus'])})
    started=time.monotonic(); model=AutoModelForMultimodalLM.from_pretrained(model_cfg['model_path'],**kw); model.eval()
    load_seconds=time.monotonic()-started
    if any(str(v) in ('cpu','disk') for v in getattr(model,'hf_device_map',{}).values()): raise ValueError('UNAUTHORIZED_OFFLOAD')
    if stage=='discovery' and model.generation_config.cache_implementation not in [None,'dynamic']: raise ValueError('UNVERIFIED_CACHE_IMPLEMENTATION')
    eos=model.generation_config.eos_token_id or processor.tokenizer.eos_token_id; eos=[eos] if isinstance(eos,int) else list(eos)
    directory=root/'raw'/output_stage/a.model; directory.mkdir(parents=True,exist_ok=True)
    software=dict(torch=torch.__version__,transformers=transformers.__version__,cuda=torch.version.cuda,dtype='bfloat16',quantization=None,backend='transformers_sdpa')
    environment=dict(model=model_cfg,software=software,load_seconds=load_seconds,device_map=getattr(model,'hf_device_map',{}),
        request_manifest_sha256=sha(file),processor_config=processor.to_dict() if hasattr(processor,'to_dict') else None,
        chat_template_sha256=digest(processor.chat_template),vision_helper_sha256=sha(helper),code_sha256=sha(__file__),
        effective_mode=dict(enable_thinking=False,do_sample=False,max_new_tokens=cfg['max_new_tokens'],use_cache=True),
        allocated_gpu_names=[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
        execution_identity_version='actual_input_identity_v1' if stage=='discovery' else 'legacy_request_digest',
        cache_implementation=model.generation_config.cache_implementation,
        request_identity_module_sha256=sha(CODE/'src/request_identity.py'))
    environment_path=directory/'environments'/('job_'+os.environ.get('SLURM_JOB_ID',time.strftime('%Y%m%dT%H%M%S',time.gmtime()))+'.json')
    frozen_write(environment_path,environment)
    if not (directory/'environment.json').exists(): frozen_write(directory/'environment.json',environment)
    completed=[]; reviews=set()
    for index,r in enumerate(req,1):
        outfile=directory/(r['request_id']+'.json')
        expected=digest([model_cfg['revision'],r,cfg['max_new_tokens'],False,cfg['seed']])
        if outfile.exists() and stage!='discovery':
            previous=load(outfile)
            if previous['execution_key']!=expected: raise ValueError('CACHE_KEY_MISMATCH')
            # Infrastructure failures also remain preserved; no automatic outcome-based retry.
            if previous.get('infrastructure_error'): raise ValueError('PRIOR_INFRASTRUCTURE_FAILURE_REQUIRES_EXPLICIT_NEW_VERSION')
            completed.append(previous); continue
        row=dict(request_id=r['request_id'],run_id=a.run_id,execution_key=expected,model_id=model_cfg['model'],model_revision=model_cfg['revision'],
                 condition=r['condition'],phase=output_stage,group_id=r['group_id'],cluster_id=r['cluster_id'],attempt_id=1,seed=cfg['seed'],max_new_tokens=cfg['max_new_tokens'],environment_path=str(environment_path),environment_sha256=sha(environment_path))
        start=time.monotonic()
        try:
            if r['condition']=='D_ORIG': messages=messages_for(r['original_input'],budget)
            else:
                # Reuse the existing evidence serialization, replace only the new task interface.
                messages=messages_for(dict(level='L1',claim_text='',media=r['payload']['media']),budget)
                messages[0]['content']=r['payload']['system']
                messages[1]['content'][-1]=dict(type='text',text=r['payload']['text'])
            rendered=processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
            if not rendered.endswith('<think>\n\n</think>\n\n') and '<think>' in rendered and '</think>' not in rendered: raise ValueError('THINKING_MODE_STILL_OPEN')
            images,videos,vkwargs=vision.process_vision_info(messages,image_patch_size=16,return_video_kwargs=True,return_video_metadata=True)
            kwargs=dict(text=[rendered],images=images,return_tensors='pt',do_resize=False)
            if videos:
                tensors,metadata=zip(*videos); kwargs.update(videos=list(tensors),video_metadata=list(metadata),**vkwargs)
            inputs_cpu=processor(**kwargs)
            visual={k:dict(shape=list(v.shape),dtype=str(v.dtype),sha256=tensor_hash(v)) for k,v in inputs_cpu.items() if torch.is_tensor(v) and k not in ['input_ids','attention_mask']}
            presentation_hash=digest(visual)
            prompt_hash=hashlib.sha256(rendered.encode()).hexdigest()
            if stage=='discovery':
                # The actual media and rendered prompt are part of the execution key,
                # including on resume. Stored outputs are never reused by target alone.
                expected=execution_identity(model_cfg['revision'],r,cfg,presentation_hash,prompt_hash)
                row.update(execution_key=expected,execution_identity_version='actual_input_identity_v1')
                if outfile.exists():
                    previous=load(outfile)
                    if previous['execution_key']!=expected: raise ValueError('ACTUAL_INPUT_CACHE_KEY_MISMATCH')
                    if previous.get('infrastructure_error'): raise ValueError('PRIOR_INFRASTRUCTURE_FAILURE_REQUIRES_EXPLICIT_NEW_VERSION')
                    completed.append(previous); del inputs_cpu; continue
            # Store the actual helper-resized media and processor grids for independent review.
            review=root/'review'/'actual_presentations'/presentation_hash
            if presentation_hash not in reviews and not (review/'manifest.json').exists():
                review.mkdir(parents=True,exist_ok=True); image_files=[]
                for ii,img in enumerate(images or []):
                    image_file=review/f'image_{ii:03d}.png'; img.save(image_file); image_files.append(str(image_file.relative_to(root)))
                if videos:
                    from PIL import Image
                    for vi,(tensor,meta) in enumerate(videos):
                        for fi,frame in enumerate(tensor):
                            array=frame.permute(1,2,0).cpu().numpy().clip(0,255).astype('uint8')
                            image_file=review/f'video_{vi:03d}_frame_{fi:03d}.png'; Image.fromarray(array).save(image_file); image_files.append(str(image_file.relative_to(root)))
                write(review/'manifest.json',dict(visual=visual,media=r['payload']['media'],images=image_files,
                    processor_resize=False,source='EXACT_VISION_HELPER_OUTPUT; processor pixel tensor hashes included'))
            reviews.add(presentation_hash)
            frozen_write(root/'rendered'/output_stage/a.model/(r['request_id']+'.json'),dict(messages=messages,rendered_prompt=rendered,rendered_prompt_sha256=prompt_hash,visual=visual))
            input_ids=inputs_cpu['input_ids']; prompt_tokens=int(input_ids.shape[-1])
            visual_tokens=sum(int((input_ids==token).sum()) for token in [getattr(model.config,'image_token_id',-1),getattr(model.config,'video_token_id',-2)])
            inputs=inputs_cpu.to(model.device)
            if 'past_key_values' in inputs or 'cache_params' in inputs: raise ValueError('CROSS_REQUEST_CACHE_INPUT_FORBIDDEN')
            for device in range(torch.cuda.device_count()): torch.cuda.reset_peak_memory_stats(device)
            torch.cuda.synchronize(); genstart=time.monotonic()
            with torch.inference_mode(): generated=model.generate(**inputs,do_sample=False,max_new_tokens=cfg['max_new_tokens'],use_cache=True)
            torch.cuda.synchronize(); generation_seconds=time.monotonic()-genstart
            original_count=int(generated.shape[-1]-prompt_tokens); tokens=generated[0,prompt_tokens:prompt_tokens+cfg['max_new_tokens']]
            ids=tokens.tolist(); raw=processor.decode(tokens,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip()
            ended=bool(ids and ids[-1] in eos); truncated=original_count>cfg['max_new_tokens'] or (len(ids)==cfg['max_new_tokens'] and not ended)
            row.update(raw_response=raw,output_token_ids=ids,input_tokens=prompt_tokens,visual_tokens=visual_tokens,output_tokens=len(ids),
                finish_reason='length' if truncated else 'eos' if ended else 'stop',truncated=truncated,discarded_tokens=max(0,original_count-len(ids)),
                presentation_hash=presentation_hash,rendered_prompt_sha256=hashlib.sha256(rendered.encode()).hexdigest(),
                generation_seconds=generation_seconds,peak_memory_bytes=[torch.cuda.max_memory_allocated(i) for i in range(torch.cuda.device_count())],infrastructure_error=None)
            del inputs,inputs_cpu,generated,tokens
        except Exception as exc:
            row.update(raw_response='',infrastructure_error=f'{type(exc).__name__}: {exc}',finish_reason='infrastructure_error',output_tokens=None)
            torch.cuda.empty_cache()
        row['wall_seconds']=time.monotonic()-start; row['timestamp_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        frozen_write(outfile,row); completed.append(row)
        write(directory/'progress.json',dict(status='RUNNING',completed=len(completed),expected=len(req),errors=sum(bool(x.get('infrastructure_error')) for x in completed)))
        print(json.dumps(dict(index=index,total=len(req),request_id=r['request_id'],condition=r['condition'],error=row.get('infrastructure_error'),seconds=row['wall_seconds'])),flush=True)
        if row.get('infrastructure_error'):
            write(directory/'interruption.json',dict(status='FAIL',failed_request=r['request_id'],reason=row['infrastructure_error']))
            raise RuntimeError('INFRASTRUCTURE_FAILURE_STOPPED_NO_SILENT_SKIP')
    write(directory/'completion.json',dict(status='COMPLETE',completed=len(completed),expected=len(req),infrastructure_errors=sum(bool(x.get('infrastructure_error')) for x in completed),
        manifest_sha256=sha(file),raw_index=[dict(request_id=x['request_id'],path=str(directory/(x['request_id']+'.json')),sha256=sha(directory/(x['request_id']+'.json'))) for x in completed],
        total_wall_seconds=sum(x['wall_seconds'] for x in completed),load_seconds=load_seconds,gpus=model_cfg['gpus'],max_new_tokens=cfg['max_new_tokens']))
    write(directory/'progress.json',dict(status='COMPLETE',completed=len(completed),expected=len(req)))

if __name__=='__main__': main()
