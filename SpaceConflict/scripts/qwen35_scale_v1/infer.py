"""Qwen3.5 vision inference, same frozen inputs and decoding across sizes."""
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from common import load, unique, parse, sha, write
from protocol import messages_for, select_rows, check_resume

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--scope', choices=['smoke','full'], required=True)
    p.add_argument('--num-shards', type=int, default=1)
    p.add_argument('--shard-index', type=int, default=0)
    p.add_argument('--seed', type=int, default=20260904)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--limit', type=int)
    a = p.parse_args(); root = a.run_root
    cfg = json.loads((root/'config.json').read_text()); model_cfg = cfg['candidate']
    if cfg['run_id'] != a.run_id or cfg['seed'] != a.seed:
        raise ValueError('RUN_OR_SEED_MISMATCH')
    request_path = root/('smoke.jsonl' if a.scope=='smoke' else 'requests.jsonl')
    rows = load(request_path); unique(rows)
    expected = cfg['input_hashes'][request_path.name]
    if sha(request_path) != expected: raise ValueError('REQUEST_HASH_MISMATCH')
    selected = select_rows(rows,a.num_shards,a.shard_index,a.limit)
    if not selected: raise ValueError('EMPTY_SHARD')
    if a.dry_run:
        print(json.dumps(dict(status='PLANNED',count=len(selected),model=model_cfg['model_id']))); return
    import torch
    import transformers
    from transformers import AutoModelForMultimodalLM, AutoProcessor
    from qwen_vl_utils import process_vision_info
    manifest=json.loads(Path(model_cfg['manifest_path']).read_text())
    if (manifest['model_id'],manifest['revision']) != (model_cfg['model_id'],model_cfg['revision']):
        raise ValueError('MODEL_MANIFEST_MISMATCH')
    if torch.cuda.device_count() != model_cfg['gpus']: raise ValueError('ALLOCATED_GPU_COUNT_MISMATCH')
    torch.manual_seed(a.seed); torch.cuda.manual_seed_all(a.seed)
    torch.set_float32_matmul_precision('high')
    processor = AutoProcessor.from_pretrained(model_cfg['model_path'],local_files_only=True,use_fast=True)
    options=dict(local_files_only=True,dtype=torch.bfloat16,attn_implementation='sdpa',low_cpu_mem_usage=True)
    if model_cfg['gpus']==1: options['device_map']='cuda'
    else: options.update(device_map='balanced',max_memory={i:'38GiB' for i in range(model_cfg['gpus'])})
    model = AutoModelForMultimodalLM.from_pretrained(model_cfg['model_path'],**options)
    if any(str(d) in ('cpu','disk') for d in getattr(model,'hf_device_map',{}).values()):
        raise ValueError('CPU_OR_DISK_OFFLOAD_FORBIDDEN')
    model.eval()
    output=root/a.scope/f'predictions_{a.shard_index:03d}.jsonl'
    output.parent.mkdir(parents=True,exist_ok=True)
    existing=load(output) if output.exists() else []
    if existing and not a.resume: raise FileExistsError(output)
    identity=dict(run_id=a.run_id,model_id=model_cfg['model_id'],model_revision=model_cfg['revision'],
                  seed=a.seed,requested_samples_sha256=expected,config_sha256=sha(root/'config.json'),
                  inference_code_sha256=sha(__file__),num_shards=a.num_shards,shard_index=a.shard_index)
    check_resume(existing,selected,identity)
    failures=sum(bool(r.get('error')) for r in existing)
    with output.open('a') as stream:
        for index,sample in enumerate(selected[len(existing):],len(existing)+1):
            started=time.monotonic()
            record=dict(identity,schema_version='spaceconflict_qwen35_prediction_v1',sample_id=sample['sample_id'],
                        pair_id=sample.get('pair_id'),component=sample['component'],decode=cfg['decode'],vision=cfg['vision'])
            try:
                messages=messages_for(sample,cfg)
                rendered=processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
                images,video_pairs,kwargs=process_vision_info(messages,return_video_kwargs=True,
                    return_video_metadata=True,image_patch_size=cfg['vision']['image_patch_size'])
                videos,metadata=(list(x) for x in zip(*video_pairs)) if video_pairs else (None,None)
                if metadata and any(m.get('fps') is None for m in metadata):
                    raise ValueError('NATIVE_VIDEO_FPS_MISSING')
                inputs=processor(text=[rendered],images=images,videos=videos,video_metadata=metadata,
                                 do_resize=False,return_tensors='pt',padding=True,**kwargs).to(model.device)
                with torch.inference_mode():
                    generated=model.generate(**inputs,do_sample=False,max_new_tokens=cfg['decode']['max_new_tokens'],use_cache=True)
                prompt_tokens=int(inputs['input_ids'].shape[-1]); suffix=generated[:,prompt_tokens:]
                raw=processor.batch_decode(suffix,skip_special_tokens=True,clean_up_tokenization_spaces=False)[0].strip()
                record.update(raw_response=raw,prediction=parse(raw),prompt_tokens=prompt_tokens,
                              generated_tokens=int(suffix.shape[-1]),output_cap_hit=int(suffix.shape[-1])>=cfg['decode']['max_new_tokens'],error=None)
            except Exception as exc:
                failures+=1
                record.update(raw_response='',prediction=parse(''),error=f'{type(exc).__name__}: {exc}')
                torch.cuda.empty_cache()
            record.update(inference_seconds=round(time.monotonic()-started,4),completed_at_utc=datetime.now(timezone.utc).isoformat())
            stream.write(json.dumps(record,ensure_ascii=False,sort_keys=True)+'\n'); stream.flush(); os.fsync(stream.fileno())
            print(json.dumps(dict(index=index,total=len(selected),sample_id=sample['sample_id'],error=record['error'],seconds=record['inference_seconds'])),flush=True)
    write(output.with_suffix('.manifest.json'),dict(status='PASS' if not failures else 'FAIL',count=len(selected),
        failure_count=failures,success_count=len(selected)-failures,output_sha256=sha(output),**identity,
        software=dict(torch=torch.__version__,transformers=transformers.__version__),code_commit='NO_GIT_REPOSITORY_AVAILABLE'))
    if failures: raise RuntimeError(f'INFERENCE_RUNTIME_ERRORS:{failures}')

if __name__=='__main__': main()
