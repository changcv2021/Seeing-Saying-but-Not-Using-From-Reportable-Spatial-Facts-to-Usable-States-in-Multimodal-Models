"""Native frozen visual protocol + language-only LoRA. Test input never includes gold."""
import copy,importlib.util,math,re,sys
from common import *

PROTOCOL_DIR=REPO/'scripts/full_multimodel_20260908_v1'
sys.path.insert(0,str(REPO/'src'))
def old_module(name):
    spec=importlib.util.spec_from_file_location('pss_frozen_'+name,PROTOCOL_DIR/(name+'.py'))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
protocol=old_module('protocol')
BUDGET=dict(min_pixels=100352,max_pixels=401408,video_frames=16,video_max_pixels=200704)
HP=dict(lora_rank=16,lora_alpha=32,lora_dropout=0.05,learning_rate=2e-5,weight_decay=0.01,
        optimizer='AdamW',precision='bfloat16',gradient_checkpointing=True,max_grad_norm=1.0)

def answer_target(label):
    if label not in ('SUPPORTED','CONTRADICTORY','UNKNOWN'):raise ValueError('BAD_LABEL')
    # Partial assistant target: don't train a fake confidence/reason or an early EOS.
    return '{"label":'+json.dumps(label)

def load_engine(root,seed,adapter=None):
    env=read(root/'environment/ENVIRONMENT.json');sys.path.insert(0,env['overlay'])
    import torch,peft
    from transformers import AutoProcessor,Qwen3_5ForConditionalGeneration
    torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
    processor=AutoProcessor.from_pretrained(MODEL,local_files_only=True,use_fast=True)
    model=Qwen3_5ForConditionalGeneration.from_pretrained(MODEL,local_files_only=True,
        dtype=torch.bfloat16,attn_implementation='sdpa',device_map='cuda')
    model.requires_grad_(False)
    pattern=re.compile(r'^model\.language_model\.layers\.\d+\.(?:self_attn\.(?:q|k|v|o)_proj|linear_attn\.(?:in_proj_qkv|in_proj_z|in_proj_b|in_proj_a|out_proj))$')
    targets=sorted(n for n,m in model.named_modules() if isinstance(m,torch.nn.Linear) and pattern.fullmatch(n))
    if not targets:raise ValueError('NO_LANGUAGE_LORA_TARGETS')
    if adapter:
        model=peft.PeftModel.from_pretrained(model,adapter,is_trainable=True)
    else:
        model=peft.get_peft_model(model,peft.LoraConfig(r=HP['lora_rank'],lora_alpha=HP['lora_alpha'],
            lora_dropout=HP['lora_dropout'],target_modules=targets,bias='none',task_type='CAUSAL_LM'))
    model.enable_input_require_grads()
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    model.config.use_cache=False
    trainable=[n for n,p in model.named_parameters() if p.requires_grad]
    if any('.lora_' not in n or '.language_model.layers.' not in n for n in trainable):raise ValueError('UNEXPECTED_TRAINABLE')
    return model,processor,dict(hyperparameters=HP,lora_targets=targets,trainable_names=trainable,
        trainable_parameters=sum(p.numel() for p in model.parameters() if p.requires_grad))

def encode(processor,sample,target=None,*,task_prompt=None,end_turn=False):
    import torch
    from PIL import Image
    messages=protocol.messages_for(sample,BUDGET)
    if task_prompt is not None:
        messages[0]['content']='Use only the supplied visual evidence and the stated hypothetical actions. Do not invent unavailable facts.'
        messages[1]['content'][-1]['text']=task_prompt
    opened=[];visual=[]
    try:
        medias=iter(sample.get('media',[]))
        for item in messages[1]['content']:
            if item['type']!='image':continue
            media=next(medias)
            if media.get('kind','image')!='image':raise ValueError('NONIMAGE_REQUIRES_SEPARATE_NATIVE_PATH')
            with Image.open(media['path']) as src:im=src.convert('RGB')
            cap=media.get('presentation_max_pixels',401408)
            if im.width*im.height>cap:
                s=math.sqrt(cap/(im.width*im.height));im=im.resize((max(1,int(im.width*s)),max(1,int(im.height*s))),Image.Resampling.BICUBIC)
            visual.append(dict(path=media['path'],role=media.get('role'),size=list(im.size),rgb_sha256=hashlib.sha256(im.tobytes()).hexdigest()))
            item['image']=im;opened.append(im)
        batch=processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,
            return_dict=True,return_tensors='pt',enable_thinking=False)
        n=int(batch['input_ids'].shape[-1]);target_ids=[]
        if target is not None:
            target_ids=processor.tokenizer.encode(target,add_special_tokens=False)
            if end_turn:target_ids.append(processor.tokenizer.convert_tokens_to_ids('<|im_end|>'))
            if not target_ids or len(target_ids)>512:raise ValueError('TARGET_TOKEN_BUDGET')
            t=torch.tensor([target_ids],dtype=batch['input_ids'].dtype)
            batch['input_ids']=torch.cat([batch['input_ids'],t],dim=-1)
            batch['attention_mask']=torch.ones_like(batch['input_ids'])
            for key in ('mm_token_type_ids','token_type_ids'):
                if key in batch:batch[key]=torch.cat([batch[key],torch.zeros_like(t)],dim=-1)
        return batch,dict(prompt_tokens=n,target_tokens=len(target_ids),target_ids=target_ids,visual_inputs=visual,
                          prompt_payload_sha256=digest({k:v for k,v in sample.items() if k!='media'}))
    finally:
        for im in opened:im.close()

def loss_for(model,batch,receipt):
    import torch
    n=receipt['prompt_tokens'];t=receipt['target_tokens']
    if not t:raise ValueError('EMPTY_SUPERVISION')
    indices=torch.arange(n-1,n+t-1,device=model.device)
    outputs=model(**batch.to(model.device),use_cache=False,logits_to_keep=indices)
    labels=batch['input_ids'][:,n:n+t].to(model.device)
    # Restrict LM-head materialization to supervised positions; no full-context 248k-vocab logits.
    return torch.nn.functional.cross_entropy(outputs.logits.float().reshape(-1,outputs.logits.shape[-1]),labels.reshape(-1))

