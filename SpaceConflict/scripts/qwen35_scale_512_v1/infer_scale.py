"""Deterministic, direct-mode Qwen3.5 inference without private gold access."""
import argparse
import importlib.util
import json
import os
import time
from pathlib import Path
from common import load, unique, sha, write, parse
from protocol import messages_for, selected_rows, PROMPT_VERSION
from output_policy import TOKEN_LIMIT, POLICY_VERSION, generation_metadata, parse_prediction

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--scope', choices=['smoke', 'full'], default='full')
    p.add_argument('--num-shards', type=int, default=1)
    p.add_argument('--shard-index', type=int, default=0)
    p.add_argument('--seed', type=int, default=20260904)
    p.add_argument('--limit', type=int)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--resume', action='store_true')
    a = p.parse_args()
    root = a.run_root
    cfg = json.loads((root/'config.json').read_text())
    if cfg.get('prompt_version') != PROMPT_VERSION:
        raise ValueError('PROMPT_VERSION_MISMATCH')
    if cfg['decode']['max_new_tokens'] != TOKEN_LIMIT or cfg['scoring_policy'] != POLICY_VERSION:
        raise ValueError('OUTPUT_POLICY_MISMATCH')
    if cfg['run_id'] != a.run_id or cfg['seed'] != a.seed:
        raise ValueError('CONFIG_ID_SEED_MISMATCH')
    req = root/('smoke.jsonl' if a.scope == 'smoke' else 'requests.jsonl')
    request_sha, config_sha = sha(req), sha(root/'config.json')
    if request_sha != cfg['input_hashes'][req.name]:
        raise ValueError('FROZEN_REQUEST_HASH_CHANGED')
    rows = load(req); unique(rows)
    selected = selected_rows(rows, a.num_shards, a.shard_index, a.limit)
    if not selected: raise ValueError('EMPTY_SELECTION')
    if a.dry_run:
        print(json.dumps(dict(status='PLANNED', model=cfg['model'], selected=len(selected)))); return
    output = root/a.scope/f'predictions_{a.shard_index:03d}.jsonl'
    existing = load(output) if output.exists() else []
    if existing and not a.resume: raise FileExistsError(output)
    if [r['sample_id'] for r in existing] != [r['sample_id'] for r in selected[:len(existing)]]:
        raise ValueError('RESUME_NOT_PREFIX')
    for r in existing:
        if (r['model_id'], r['model_revision'], r['requested_samples_sha256'], r['config_sha256']) != (cfg['model'], cfg['revision'], request_sha, config_sha):
            raise ValueError('RESUME_PROVENANCE_MISMATCH')
    manifest = json.loads(Path(cfg['manifest_path']).read_text())
    if (manifest['model_id'], manifest['revision']) != (cfg['model'], cfg['revision']):
        raise ValueError('MODEL_REVISION_MISMATCH')
    import torch
    import transformers
    from transformers import AutoModelForMultimodalLM, AutoProcessor
    if torch.cuda.device_count() != cfg['gpus']: raise ValueError('WRONG_GPU_COUNT')
    helper = Path(__file__).parent/'vision_process_frozen.py'
    if sha(helper) != cfg['vision_helper_sha256']: raise ValueError('VISION_HELPER_CHANGED')
    spec = importlib.util.spec_from_file_location('sc_frozen_vision', helper)
    vision = importlib.util.module_from_spec(spec); spec.loader.exec_module(vision)
    torch.manual_seed(a.seed); torch.cuda.manual_seed_all(a.seed)
    torch.set_float32_matmul_precision('high')
    processor = AutoProcessor.from_pretrained(cfg['model_path'], local_files_only=True, use_fast=True)
    kw = dict(local_files_only=True, dtype=torch.bfloat16, low_cpu_mem_usage=True, attn_implementation='sdpa')
    if cfg['gpus'] == 1: kw['device_map'] = 'cuda'
    else: kw.update(device_map='balanced', max_memory={i:'38GiB' for i in range(cfg['gpus'])})
    model = AutoModelForMultimodalLM.from_pretrained(cfg['model_path'], **kw)
    if any(str(v) in ('cpu','disk') for v in getattr(model,'hf_device_map',{}).values()):
        raise ValueError('OFFLOAD_OUTSIDE_ALLOCATED_GPUS')
    model.eval()
    eos_ids=model.generation_config.eos_token_id
    if eos_ids is None: eos_ids=processor.tokenizer.eos_token_id
    eos_ids=[eos_ids] if isinstance(eos_ids,int) else list(eos_ids or [])
    if not eos_ids: raise ValueError('NO_EOS_IDS_FOR_LENGTH_AUDIT')
    software = dict(torch=torch.__version__, transformers=transformers.__version__, cuda=torch.version.cuda)
    write(root/f'environment_{a.scope}_{a.shard_index:03d}.json', dict(software=software, config=cfg,
          device_map=getattr(model,'hf_device_map',{}), model_revision=cfg['revision'],
          code_sha256=sha(__file__), protocol_sha256=sha(Path(__file__).parent/'protocol.py')))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('a') as stream:
        for index, sample in enumerate(selected[len(existing):], len(existing)+1):
            started=time.monotonic()
            row=dict(schema_version='spaceconflict_qwen35_prediction_v1', run_id=a.run_id,
                     sample_id=sample['sample_id'], pair_id=sample.get('pair_id'), component=sample['component'],
                     model_id=cfg['model'], model_revision=cfg['revision'], seed=a.seed, decode=cfg['decode'],
                     prompt_version=PROMPT_VERSION, protocol_sha256=sha(Path(__file__).parent/'protocol.py'),
                     requested_samples_sha256=request_sha, config_sha256=config_sha)
            try:
                messages=messages_for(sample, cfg['media_budget'])
                text=processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
                images, videos, video_kwargs=vision.process_vision_info(messages, image_patch_size=16,
                    return_video_kwargs=True, return_video_metadata=True)
                kwargs=dict(text=[text], images=images, return_tensors='pt', do_resize=False)
                if videos:
                    tensors, metadata=zip(*videos)
                    kwargs.update(videos=list(tensors), video_metadata=list(metadata), **video_kwargs)
                inputs=processor(**kwargs).to(model.device)
                with torch.inference_mode():
                    generated=model.generate(**inputs, do_sample=False, max_new_tokens=cfg['decode']['max_new_tokens'], use_cache=True)
                prompt_tokens=inputs['input_ids'].shape[-1]
                original_count=int(generated.shape[-1]-prompt_tokens)
                tokens=generated[:,prompt_tokens:prompt_tokens+TOKEN_LIMIT]
                raw=processor.batch_decode(tokens, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0].strip()
                row.update(raw_response=raw, error=None, prompt_tokens=int(prompt_tokens),
                    **generation_metadata(int(tokens.shape[-1]),int(tokens[0,-1].item()) if tokens.shape[-1] else None,eos_ids,original_count))
                row['prediction']=parse_prediction(row)
                del inputs, generated, tokens
            except Exception as exc:
                row.update(raw_response='', prediction=parse(''), error=f'{type(exc).__name__}: {exc}')
                torch.cuda.empty_cache()
            row['inference_seconds']=round(time.monotonic()-started,4)
            stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n'); stream.flush(); os.fsync(stream.fileno())
            print(json.dumps(dict(index=index,total=len(selected),sample_id=row['sample_id'],error=row['error'],seconds=row['inference_seconds'])),flush=True)
    completed=load(output)
    write(output.with_suffix('.manifest.json'), dict(status='COMPLETE', count=len(completed),
          success_count=sum(not r['error'] for r in completed), failure_count=sum(bool(r['error']) for r in completed),
          run_id=a.run_id, seed=a.seed, input_sha256=request_sha, output_sha256=sha(output), code_sha256=sha(__file__),
          source_revision=cfg['revision'], code_commit='NO_GIT_REPOSITORY_AVAILABLE', software=software))

if __name__ == '__main__': main()
