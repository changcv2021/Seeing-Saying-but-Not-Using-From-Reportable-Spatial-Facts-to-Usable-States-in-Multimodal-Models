"""CPU-only actual processor presentation review; no model weights or generation."""
import html
import importlib.util
import time
from collections import defaultdict
from common import *
from infer import tensor_hash

VISUAL_FIELDS = {'pixel_values','pixel_values_videos','image_grid_thw','video_grid_thw','second_per_grid_ts'}
TEXT_FIELDS = {'input_ids','attention_mask','mm_token_type_ids','token_type_ids','position_ids'}

def main():
    a=arguments(__doc__).parse_args(); cfg,root=setup(a)
    if a.dry_run: print('PLANNED: actual media/processor review rendering, no inference'); return
    require_compute()
    if load(root/'reports/setup_calibration_acceptance.json')['status']!='PASS': raise ValueError('SETUP_FIRST')
    req=list(rows(root/'review/draft_requests.jsonl')); panel=list(rows(root/'review/candidate_panel.jsonl'))
    campaign=load(Path(cfg['campaign'])/'config.json'); legacy=Path(cfg['campaign'])/'code'
    sys.path.insert(0,str(legacy)); from protocol import messages_for
    import torch
    from transformers import AutoProcessor
    torch.set_num_threads(int(os.environ.get('SLURM_CPUS_PER_TASK','1')))
    helper=legacy/'vision_process_frozen.py'
    if sha(helper)!=campaign['vision_helper_sha256']: raise ValueError('VISION_HELPER_CHANGED')
    spec=importlib.util.spec_from_file_location('a1_review_vision',helper); vision=importlib.util.module_from_spec(spec); spec.loader.exec_module(vision)
    index=[]; byworld=defaultdict(dict); presentation_details={}; start=time.monotonic()
    for key in cfg['models']:
        mc=next(m for m in campaign['models'] if m['key']==key)
        processor=AutoProcessor.from_pretrained(mc['model_path'],local_files_only=True,use_fast=True)
        cache={}
        for r in req:
            msgs=messages_for(dict(level='L1',claim_text='',media=r['payload']['media']),campaign['media_budget'])
            msgs[0]['content']=r['payload']['system']; msgs[1]['content'][-1]=dict(type='text',text=r['payload']['text'])
            rendered=processor.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True,enable_thinking=False)
            th=hashlib.sha256(rendered.encode()).hexdigest(); bundle=digest(r['payload']['media'])
            if bundle not in cache:
                for media in r['payload']['media']:
                    if media['kind']!='image': raise ValueError('A1_REVIEW_STILL_IMAGE_SCOPE')
                    if sha(media['path'])!=media['sha256'].removeprefix('sha256:'): raise ValueError('SOURCE_MEDIA_HASH_MISMATCH')
                imgs,vids,vkwargs=vision.process_vision_info(msgs,image_patch_size=16,return_video_kwargs=True,return_video_metadata=True)
                if vids: raise ValueError('UNPLANNED_VIDEO_IN_A1')
                batch=processor(text=[rendered],images=imgs,return_tensors='pt',do_resize=False)
                visual={k:dict(shape=list(v.shape),dtype=str(v.dtype),sha256=tensor_hash(v)) for k,v in batch.items() if torch.is_tensor(v) and k in VISUAL_FIELDS}
                unexpected=[k for k,v in batch.items() if torch.is_tensor(v) and k not in VISUAL_FIELDS | TEXT_FIELDS]
                if unexpected: raise ValueError('UNCLASSIFIED_PROCESSOR_FIELDS:'+repr(unexpected))
                auxiliary={k:dict(shape=list(v.shape),dtype=str(v.dtype),sha256=tensor_hash(v)) for k,v in batch.items() if torch.is_tensor(v) and k in TEXT_FIELDS and k not in ['input_ids','attention_mask']}
                ph=digest(visual); d=root/'review/actual_presentations'/ph; d.mkdir(parents=True,exist_ok=True)
                files=[]
                for j,img in enumerate(imgs or []):
                    out=d/f'image_{j:03d}.png'
                    if not out.exists(): img.save(out)
                    files.append(entry(out))
                details=dict(visual=visual,representative_auxiliary_text_tensors=auxiliary,
                    visual_hash_version='PURE_MEDIA_TENSORS_V2_EXCLUDING_TEXT_AUXILIARIES',
                    media=r['payload']['media'],image_files=files,processor_do_resize=False,
                    note='EXACT_HELPER_MEDIA; actual processor pixel/grid tensors hashed. Validated once per identical media bundle per model; inference must check every request.',
                    representative_request_id=r['request_id'],model=key)
                # Per-model metadata is separate: shared visual hash does not imply model ID equality.
                save(d/('processor_'+key+'.json'),details,frozen=True)
                cache[bundle]=(ph,visual,files); presentation_details[(key,ph)]=details
                del batch
            ph,visual,files=cache[bundle]
            rp=root/'review/rendered_drafts'/key/(r['request_id']+'.json')
            save(rp,dict(request_id=r['request_id'],messages=msgs,rendered_prompt=rendered,rendered_prompt_sha256=th,
                presentation_hash=ph,visual=visual,processor_scope='PER_IDENTICAL_MEDIA_BUNDLE; NOT_MODEL_GENERATION'),frozen=True)
            index.append(dict(model=key,request_id=r['request_id'],group_id=r['group_id'],condition=r['condition'],
                presentation_hash=ph,rendered_prompt_sha256=th,rendered_path=str(rp),images=files))
            if files: byworld[r['group_id']][key]=dict(presentation_hash=ph,images=files)
        print(json.dumps(dict(model=key,draft_prompts=len(req),unique_media_bundles=len(cache),generation_requests=0)),flush=True)
    failures=[]
    for r in req:
        rr=[x for x in index if x['request_id']==r['request_id']]
        if len({x['presentation_hash'] for x in rr})!=1: failures.append(dict(request_id=r['request_id'],reason='CROSS_MODEL_PRESENTATION_DIFF'))
        # Model-specific chat templates may differ; retain differences instead of falsely declaring prompts identical.
    save(root/'review/rendered_drafts_index.jsonl',index,'jsonl',frozen=True)
    with (root/'derived_input_review.csv').open(newline='') as f: review=list(csv.DictReader(f))
    for row in review:
        row['actual_processor_check']='PASS' if not failures else 'FAIL'
        row['media_order']='PASS_EXACT_ROLE_AND_SHA256_ORDER'; row['human_review_completed']=False
    csvsave(root/'derived_input_review.csv',review)
    outdir=root/'review/review_package'; outdir.mkdir(parents=True,exist_ok=True)
    pages=['<!doctype html><meta charset="utf-8"><title>Phase A.1 派生输入复核</title><style>body{font:16px sans-serif;margin:32px;max-width:1500px}pre{white-space:pre-wrap;background:#eee;padding:12px}img{max-width:100%;border:1px solid #aaa}section{border-top:3px solid #555;margin-top:40px}figure{display:inline-block;max-width:46%;vertical-align:top}h1{color:#234}</style>',
        '<h1>Phase A.1 实际输入复核包</h1><p>尚未标记人工审核通过。这里展示实际 vision helper 图像（processor do_resize=False），不是上游未处理的原图。先看输入；gold 单独折叠，绝不发送给普通视觉推理。</p>',
        '<p>每个 world 需确认 PRE 可判定性、介入是否完整、target 唯一性、参考系、类别/范围、状态定义、来源真值、媒体顺序和每条派生问题。不能因为原数据已审核或仅因为文件存在就自动确认。</p>']
    for p in panel:
        gid=p['group_id']; pages.append('<section><h2>'+html.escape(p['world_id'])+' / '+p['level']+'</h2><p>'+html.escape(gid+' | '+p['stratum']+' | '+p['review_status'])+'</p>')
        pages.append('<pre>'+html.escape(p['context']+'\n'+p['intervention']+'\n'+p['query'])+'</pre>')
        seen=set()
        for key,detail in byworld[gid].items():
            if detail['presentation_hash'] in seen: continue
            seen.add(detail['presentation_hash']); pages.append('<p>实际呈现 SHA256: '+detail['presentation_hash']+'；模型 '+key+'</p>')
            for j,image in enumerate(detail['images']):
                src=os.path.relpath(image['path'],outdir)
                role=p['media'][j]['role']
                pages.append('<figure><figcaption>'+html.escape(f'Image {j+1}: {role}')+'</figcaption><a href="'+html.escape(src,quote=True)+'"><img src="'+html.escape(src,quote=True)+'"></a></figure>')
        pages.append('<details><summary>复核用来源真值／操作（不是普通模型输入）</summary><pre>'+html.escape(json.dumps(dict(values=p['values'],action=p['action_expected'],source_proof_sha256=p['source_proof_sha256']),ensure_ascii=False,indent=2))+'</pre></details>')
        for r in [r for r in req if r['group_id']==gid]:
            pages.append('<details><summary>'+html.escape(r['condition']+' '+r['request_id'])+'</summary><pre>'+html.escape(r['payload']['system']+'\n'+r['payload']['text'])+'</pre></details>')
        pages.append('</section>')
    save(outdir/'index.html','\n'.join(pages),'text',frozen=True)
    save(root/'review/processor_acceptance.json',dict(status='PASS' if not failures else 'FAIL',worlds=len(panel),models=cfg['models'],
        rendered_draft_prompts=len(index),failures=failures,wall_seconds=time.monotonic()-start,
        all_source_media_hashes_checked=True,source_media_order_preserved=True,actual_processor_tensors_hashed=True,
        visual_hash_version='PURE_MEDIA_TENSORS_V2_EXCLUDING_TEXT_AUXILIARIES',
        human_review_completed=False,verified_worlds=0,core_model_generation_requests=0),frozen=True)
    save(root/'LIVE_STATUS.json',dict(status='SETUP_PASSED_REVIEW_PACKAGE_READY_CORE_BLOCKED_ON_REVIEW',
        mechanism_started=False,verified_worlds=0,review_worlds=len(panel),review_package=str(outdir/'index.html')))

if __name__=='__main__': main()
