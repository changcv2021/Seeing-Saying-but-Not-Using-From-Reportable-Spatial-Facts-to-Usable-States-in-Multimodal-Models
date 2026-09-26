"""CPU-only processor smoke using fixed source images; no model weights or gold."""
import ast,json,os
from pathlib import Path
from campaign import CODE,ROOT,SOURCE,INDUSTRY,args,frozen

def main():
    a=args()
    if a.dry_run:print('CPU processor assembly, no generation.');return
    if not os.environ.get('SLURM_JOB_ID'):raise ValueError('SLURM_REQUIRED')
    for path in CODE.glob('*.py'):ast.parse(path.read_text(),filename=str(path))
    from PIL import Image
    from transformers import AutoProcessor
    from protocol import messages_for
    sample=None
    with (SOURCE/'requests.jsonl').open() as stream:
        for line in stream:
            r=json.loads(line)
            if r['split']!='test' and r['media'] and all(m.get('kind','image')=='image' for m in r['media']):sample=r;break
    if sample is None:raise ValueError('NO_DEV_IMAGE_FIXTURE')
    configs=[]
    for filename in ['qwen_family_eval_v1.json','diverse_family_eval_v1.json']:
        configs+=json.loads((INDUSTRY/'protocol'/filename).read_text())['models']
    env=json.loads((INDUSTRY/'reports/qwen25vl7b_full_eval_20260902/environment.json').read_text())
    configs.insert(0,dict(key='qwen25vl_7b',model_path=env['model_path']))
    checks=[]
    for cfg in configs:
        if cfg.get('enabled',True) is False:continue
        try:
            processor=AutoProcessor.from_pretrained(cfg['model_path'],local_files_only=True,use_fast=True,trust_remote_code=cfg.get('trust_remote_code',False))
            if cfg['key'].startswith('internvl35_'):processor.image_processor.max_patches=2
            messages=messages_for(sample,dict(min_pixels=100352,max_pixels=401408,video_max_pixels=200704,video_frames=16))
            opened=[]
            for item in messages[1]['content']:
                if item['type']=='image':
                    im=Image.open(item['image']).convert('RGB');im.thumbnail((560,560));item['image']=im;opened.append(im)
            inputs=processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=True,
                return_tensors='pt',enable_thinking=cfg.get('mode')=='thinking')
            check=dict(model=cfg['key'],status='PASS',shapes={k:list(v.shape) for k,v in inputs.items() if hasattr(v,'shape')})
            for im in opened:im.close()
            del processor,inputs
        except Exception as exc:check=dict(model=cfg['key'],status='FAIL',error=type(exc).__name__+': '+str(exc))
        checks.append(check);print(json.dumps(check),flush=True)
    frozen(ROOT/'processor_precheck_bounded_tiles.json',dict(status='PASS' if all(r['status']=='PASS' for r in checks) else 'FAIL',checks=checks,
        model_calls=0,sample_id=sample['sample_id'],split=sample['split'],scope='Actual processor image assembly; full smoke covers frozen video-frame requests.'))
    if any(r['status']!='PASS' for r in checks):raise SystemExit(1)

if __name__=='__main__':main()
