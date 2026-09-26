"""One media/processor path for CPU review and GPU generation; no gold access."""
from v3common import *

VISUAL_FIELDS = {'pixel_values','pixel_values_videos','image_grid_thw','video_grid_thw','second_per_grid_ts'}
TEXT_FIELDS = {'input_ids','attention_mask','mm_token_type_ids','token_type_ids','position_ids'}


def tensor_hash(t):
    import torch
    return hashlib.sha256(t.detach().contiguous().cpu().view(torch.uint8).numpy().tobytes()).hexdigest()


def fingerprint(batch):
    import torch
    visual, auxiliary = {}, {}
    for k,v in batch.items():
        if k not in VISUAL_FIELDS | TEXT_FIELDS:
            raise ValueError('UNCLASSIFIED_PROCESSOR_FIELD:'+k)
        record = dict(dtype=str(v.dtype),shape=list(v.shape),sha256=tensor_hash(v)) if torch.is_tensor(v) else dict(value=v)
        if k in VISUAL_FIELDS: visual[k]=record
        elif k not in ['input_ids','attention_mask']: auxiliary[k]=record
    return dict(visual=visual,presentation_hash=digest(visual),text_auxiliary=auxiliary)


def generated_suffix(full, input_length, cap=512):
    # Sequence indexing is performed BEFORE decoding and parsing.
    total = len(full)-input_length
    if total<0: raise ValueError('GENERATION_SHORTER_THAN_INPUT')
    return full[input_length:input_length+cap], max(0,total-cap)


class Pipeline:
    def __init__(self,c,key):
        import torch
        from transformers import AutoProcessor
        self.c=c; self.key=key
        self.campaign=load(Path(c['campaign'])/'config.json')
        self.mc=next(m for m in self.campaign['models'] if m['key']==key)
        mm=load(self.mc['manifest_path'])
        if (mm['model_id'],mm['revision'])!=(self.mc['model'],self.mc['revision']):
            raise ValueError('MODEL_MANIFEST_REVISION_MISMATCH')
        legacy=Path(c['campaign'])/'code'
        helper=legacy/'vision_process_frozen.py'
        if sha(helper)!=self.campaign['vision_helper_sha256']: raise ValueError('VISION_HELPER_CHANGED')
        self.vision=import_file(helper,'a1c3_vision')
        self.protocol=import_file(legacy/'protocol.py','a1c3_legacy_protocol')
        self.processor=AutoProcessor.from_pretrained(self.mc['model_path'],local_files_only=True,use_fast=True)
        self.image_cache={}; self.checked_media=set()
        torch.set_num_threads(int(os.environ.get('SLURM_CPUS_PER_TASK','1')))

    def messages(self,r):
        if set(r['payload'])!={'system','text','media'}: raise ValueError('UNSANITIZED_PAYLOAD_FIELDS')
        msgs=self.protocol.messages_for(dict(level='L1',claim_text='',media=r['payload']['media']),self.campaign['media_budget'])
        msgs[0]['content']=r['payload']['system']
        msgs[1]['content'][-1]=dict(type='text',text=r['payload']['text'])
        rendered=self.processor.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True,enable_thinking=False)
        if '<think>' in rendered and '</think>' not in rendered: raise ValueError('THINKING_MODE_OPEN')
        return msgs,rendered

    def process(self,r):
        messages,rendered=self.messages(r)
        bundle=digest(r['payload']['media'])
        if bundle not in self.image_cache:
            for m in r['payload']['media']:
                if m['kind']!='image': raise ValueError('UNPLANNED_NON_IMAGE_MEDIA')
                if m['path'] not in self.checked_media:
                    if sha(m['path'])!=m['sha256'].removeprefix('sha256:'): raise ValueError('SOURCE_MEDIA_CHANGED')
                    self.checked_media.add(m['path'])
            images,videos,_=self.vision.process_vision_info(messages,image_patch_size=16,return_video_kwargs=True,return_video_metadata=True)
            if videos: raise ValueError('UNPLANNED_VIDEO')
            self.image_cache[bundle]=images
        images=self.image_cache[bundle]
        batch=self.processor(text=[rendered],images=images,return_tensors='pt',do_resize=False)
        fp=fingerprint(batch)
        manifest=dict(request_id=r['request_id'],messages=messages,rendered_prompt=rendered,
                      rendered_prompt_sha256=hashlib.sha256(rendered.encode()).hexdigest(),
                      visual_hash_version=self.c['visual_hash_version'],**fp,
                      input_tokens=int(batch['input_ids'].shape[-1]),processor_do_resize=False,
                      media=r['payload']['media'],image_sizes=[list(im.size) for im in images or []])
        return batch,manifest,images


def install_gold_guard():
    """Fail closed on Python file-open attempts to private gold; keep a read audit."""
    audit=dict(private_gold_open_attempts=0, file_opens=0)
    def hook(event,args):
        if event!='open' or not args or not isinstance(args[0],(str,bytes,os.PathLike)): return
        path=os.fsdecode(args[0]); audit['file_opens']+=1
        parts=Path(path).parts
        if any(p in ['gold','private_gold','PRIVATE_GOLD.jsonl'] or '.private.' in p for p in parts):
            audit['private_gold_open_attempts']+=1
            raise PermissionError('INFERENCE_PRIVATE_GOLD_READ_FORBIDDEN:'+path)
    sys.addaudithook(hook)
    return audit
