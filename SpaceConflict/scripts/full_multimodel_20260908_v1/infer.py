"""Frozen common ordered-media inference. Never open gold or score files."""
import argparse, hashlib, json, math, os, sys, time
from pathlib import Path
from common import load, unique, sha, write
from output_policy import generation_metadata, parse_prediction
from protocol import messages_for

def final_text(clean,raw,mode):
    # Explicit boundaries only. Never search a reasoning paragraph for a label.
    if '</think>' in clean:return clean.rsplit('</think>',1)[1].strip(),'CLOSED_THINK'
    if '</think>' in raw:
        tail=raw.rsplit('</think>',1)[1]
        for token in ['<|im_end|>','<|endoftext|>','<|end_of_sentence|>']:tail=tail.removesuffix(token).strip()
        return tail.strip(),'CLOSED_THINK_RAW'
    if mode=='thinking' or '<think>' in raw:return '', 'NO_FINAL_UNCLOSED_THINK'
    if '<|channel>thought' in raw:
        if '<channel|>' not in raw:return '', 'NO_FINAL_UNCLOSED_THOUGHT_CHANNEL'
        tail=raw.rsplit('<channel|>',1)[1]
        for token in ['<eos>','<end_of_turn>']:tail=tail.removesuffix(token).strip()
        return tail.strip(),'CLOSED_THOUGHT_CHANNEL'
    return clean.strip(),'DIRECT'

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run-root',type=Path,required=True);p.add_argument('--run-id',required=True)
    p.add_argument('--scope',choices=['smoke','full'],default='smoke');p.add_argument('--num-shards',type=int,default=1)
    p.add_argument('--shard-index',type=int,default=0);p.add_argument('--seed',type=int,default=20260904)
    p.add_argument('--limit',type=int);p.add_argument('--dry-run',action='store_true');p.add_argument('--resume',action='store_true')
    a=p.parse_args();root=a.run_root;cfg=json.loads((root/'config.json').read_text())
    if a.run_id!=cfg['run_id'] or a.seed!=cfg['seed']:raise ValueError('CONFIG_ID_MISMATCH')
    if not 0<=a.shard_index<a.num_shards:raise ValueError('INVALID_SHARD')
    req=root/('smoke.jsonl' if a.scope=='smoke' else 'requests.jsonl')
    request_sha=sha(req);config_sha=sha(root/'config.json')
    if request_sha!=cfg['input_hashes'][req.name]:raise ValueError('REQUEST_CHANGED')
    selected=[r for i,r in enumerate(load(req)) if i%a.num_shards==a.shard_index];unique(selected)
    if a.limit is not None:selected=selected[:a.limit]
    if a.dry_run:print(json.dumps(dict(model=cfg['model_id'],n=len(selected))));return
    if not os.environ.get('SLURM_JOB_ID'):raise ValueError('SLURM_REQUIRED')
    # Enforce private gold separation even if a future helper accidentally tries to read it.
    forbidden={'private_gold.jsonl','rubric.json','full_scored.jsonl','smoke_scored.jsonl'}
    gold_attempts=[]
    def audit(event,values):
        if event=='open' and values and isinstance(values[0],(str,bytes,os.PathLike)):
            path=os.fsdecode(values[0])
            if Path(path).name in forbidden:
                gold_attempts.append(path);raise PermissionError('CANDIDATE_GOLD_ACCESS_FORBIDDEN')
    sys.addaudithook(audit)
    out=root/a.scope/f'predictions_{a.shard_index:03d}.jsonl';out.parent.mkdir(parents=True,exist_ok=True)
    prior=load(out) if out.exists() else []
    if prior and not a.resume:raise FileExistsError(out)
    if [r['sample_id'] for r in prior]!=[r['sample_id'] for r in selected[:len(prior)]]:raise ValueError('RESUME_NOT_PREFIX')
    for r in prior:
        if r['config_sha256']!=config_sha or r['requested_samples_sha256']!=request_sha:raise ValueError('RESUME_PROVENANCE_CHANGED')
    import torch, transformers
    from PIL import Image
    from transformers import AutoProcessor, AutoModelForMultimodalLM, AutoModelForImageTextToText
    if torch.cuda.device_count()!=cfg['gpus']:raise ValueError('GPU_COUNT_MISMATCH')
    torch.manual_seed(a.seed);torch.cuda.manual_seed_all(a.seed);torch.set_float32_matmul_precision('high')
    trust=bool(cfg.get('trust_remote_code',False))
    processor=AutoProcessor.from_pretrained(cfg['model_path'],local_files_only=True,use_fast=True,trust_remote_code=trust)
    if cfg['key'].startswith('internvl35_'):
        # Resource-only pre-generation calibration: max 2 tiles plus native
        # thumbnail; keep every source image/frame, avoid 16-frame context overflow.
        processor.image_processor.max_patches=2
    kw=dict(local_files_only=True,dtype=torch.bfloat16,low_cpu_mem_usage=True,attn_implementation='sdpa',trust_remote_code=trust)
    if cfg['gpus']==1:kw['device_map']='cuda'
    else:kw.update(device_map='balanced',max_memory={i:'38GiB' for i in range(cfg['gpus'])})
    loader=AutoModelForImageTextToText if cfg.get('auto_class')=='image_text_to_text' else AutoModelForMultimodalLM
    model=loader.from_pretrained(cfg['model_path'],**kw).eval()
    if any(str(v) in ['cpu','disk'] for v in getattr(model,'hf_device_map',{}).values()):raise ValueError('UNAUTHORIZED_OFFLOAD')
    eos=model.generation_config.eos_token_id or processor.tokenizer.eos_token_id;eos=[eos] if isinstance(eos,int) else list(eos)
    image_cfg=processor.image_processor.to_dict()
    software=dict(torch=torch.__version__,transformers=transformers.__version__,cuda=torch.version.cuda)
    write(root/f'environment_{a.scope}_{a.shard_index:03d}.json',dict(model_id=cfg['model_id'],revision=cfg['revision'],software=software,
        processor=image_cfg,chat_template_sha256=hashlib.sha256(str(processor.chat_template).encode()).hexdigest(),
        device_map=getattr(model,'hf_device_map',{}),config_sha256=config_sha,job_id=os.environ['SLURM_JOB_ID']))
    failures=0
    with out.open('a') as stream:
        for number,sample in enumerate(selected[len(prior):],len(prior)+1):
            start=time.monotonic();row=dict(sample_id=sample['sample_id'],pair_id=sample.get('pair_id'),component=sample['component'],
                run_id=a.run_id,model_id=cfg['model_id'],model_revision=cfg['revision'],config_sha256=config_sha,
                requested_samples_sha256=request_sha,seed=a.seed,decode=cfg['decode'],raw_response='',error=None,normal_attempt=1,
                protocol_sha256=sha(Path(__file__).with_name('protocol.py')),code_sha256=sha(__file__))
            inputs=generated=None;opened=[]
            try:
                messages=messages_for(sample,cfg['media_budget']);visual=[];media_index=0
                # Every architecture gets the same ordered source images, bounded before its own processor.
                for item in messages[1]['content']:
                    if item['type']!='image':continue
                    media=sample['media'][media_index];media_index+=1
                    with Image.open(media['path']) as source:im=source.convert('RGB')
                    cap=media.get('presentation_max_pixels',401408)
                    if im.width*im.height>cap:
                        scale=math.sqrt(cap/(im.width*im.height));im=im.resize((max(1,int(im.width*scale)),max(1,int(im.height*scale))),Image.Resampling.BICUBIC)
                    digest=hashlib.sha256(im.tobytes()).hexdigest();visual.append(dict(path=media['path'],size=list(im.size),rgb_sha256=digest,role=media.get('role')))
                    item['image']=im;opened.append(im)
                # The existing benchmark prompt/labels are unchanged; adapter supplies PIL images only.
                rendered=processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=cfg['enable_thinking'])
                inputs=processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,
                    return_dict=True,return_tensors='pt',enable_thinking=cfg['enable_thinking'])
                tensor_hashes={}
                for name,value in inputs.items():
                    if hasattr(value,'shape'):
                        array=value.detach().cpu().contiguous();tensor_hashes[name]=dict(shape=list(array.shape),dtype=str(array.dtype),
                            sha256=hashlib.sha256(array.view(torch.uint8).numpy().tobytes()).hexdigest())
                prompt_tokens=int(inputs['input_ids'].shape[-1])
                text_config=getattr(model.config,'text_config',model.config)
                context_limit=getattr(text_config,'max_position_embeddings',None)
                if context_limit and prompt_tokens+512>context_limit:raise ValueError('INPUT_PLUS_OUTPUT_EXCEEDS_MODEL_CONTEXT_NO_INPUT_DROPPED')
                inputs=inputs.to(model.device)
                with torch.inference_mode():generated=model.generate(**inputs,do_sample=False,max_new_tokens=512,use_cache=True)
                ids=generated[0,prompt_tokens:prompt_tokens+512].tolist()
                clean=processor.decode(ids,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip()
                raw=processor.decode(ids,skip_special_tokens=False,clean_up_tokenization_spaces=False).strip()
                final,status=final_text(clean,raw,cfg['mode'])
                row.update(raw_generated_special=raw,raw_generated_clean=clean,generated_token_ids=ids,raw_response=final,
                    rendered_prompt=rendered,prompt_version=cfg['prompt_version'],
                    channel_status=status,prompt_tokens=prompt_tokens,visual_inputs=visual,processor_tensors=tensor_hashes,
                    **generation_metadata(len(ids),ids[-1] if ids else None,eos,int(generated.shape[-1]-prompt_tokens)))
                row['prediction']=parse_prediction(row)
            except Exception as exc:
                row['error']=type(exc).__name__+': '+str(exc);failures+=1
            finally:
                for im in opened:im.close()
                del inputs,generated
            row.update(inference_seconds=round(time.monotonic()-start,4),gold_access_attempts=len(gold_attempts))
            stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n');stream.flush();os.fsync(stream.fileno())
            write(root/a.scope/f'progress_{a.shard_index:03d}.json',dict(completed=number,expected=len(selected),errors=failures))
            print(json.dumps(dict(model=cfg['key'],completed=number,total=len(selected),seconds=row['inference_seconds'],error=row['error'])),flush=True)
            if row['error']:raise RuntimeError('INFERENCE_ERROR_PRESERVED_STOP_NO_RETRY:'+row['error'])
    final=load(out)
    if len(final)!=len(selected):raise ValueError('INCOMPLETE')
    write(out.with_suffix('.manifest.json'),dict(status='COMPLETE',count=len(final),success_count=sum(not r['error'] for r in final),
        output_sha256=sha(out),input_sha256=request_sha,config_sha256=config_sha,source_revision=cfg['revision'],seed=a.seed,
        code_commit='NO_GIT_COMMIT_ASSERTED_FILE_HASH_PROVENANCE',code_sha256=sha(__file__),software=software))

if __name__=='__main__':main()
