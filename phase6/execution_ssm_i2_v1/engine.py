"""Block-output intervention; full prefix replay at EVERY generated token, no cache."""
import copy,time,contextlib,importlib.util
from common_i2 import *
from representations import token_anchors
class Engine:
    def __init__(self,c,key,dest):
        sys.path.insert(0,str(Path(c['project'])/'src'))
        sys.path.insert(0,str(Path(c['project'])/'research/state_binding_phase_a1/core_execution_v3'))
        import pipeline_v3,torch,transformers
        self.guard=pipeline_v3.install_gold_guard();self.torch=torch
        spec=importlib.util.spec_from_file_location('i2_health',Path(c['project'])/'scripts/full_multimodel_split_v5/gpu_health.py')
        health=importlib.util.module_from_spec(spec);spec.loader.exec_module(health);health.check(dest)
        torch.manual_seed(20260911);torch.cuda.manual_seed_all(20260911);torch.set_float32_matmul_precision('high')
        self.pipe=pipeline_v3.Pipeline(dict(c,visual_hash_version='PURE_MEDIA_TENSORS_V3_SHARED_RUNTIME'),key);mc=self.pipe.mc
        assert torch.cuda.device_count()==mc['gpus']
        kw=dict(local_files_only=True,dtype=torch.bfloat16,low_cpu_mem_usage=True,attn_implementation='sdpa')
        if mc['gpus']==1:kw['device_map']='cuda'
        else:kw.update(device_map='balanced',max_memory={i:'38GiB' for i in range(mc['gpus'])})
        self.model=transformers.AutoModelForMultimodalLM.from_pretrained(mc['model_path'],**kw).eval()
        assert not any(str(v) in ('cpu','disk') for v in getattr(self.model,'hf_device_map',{}).values())
        self.layers=self.model.model.language_model.layers
        self.depths=sorted({round(i*(len(self.layers)-1)/7) for i in range(8)})
        eos=self.model.generation_config.eos_token_id
        self.eos=set(eos if isinstance(eos,list) else [eos]);self.forward_count=0
        self.generations=0;self.patched_generations=0;self.tokenizer=self.pipe.processor.tokenizer
        self.config=dict(model=mc,transformers=transformers.__version__,torch=torch.__version__,dtype='bfloat16',backend='sdpa',quantization=False,
            layers=[dict(index=i,type=getattr(self.layers[i],'block_type',None)) for i in self.depths],cache_policy='FULL_REPLAY_NONE_EVERY_FORWARD')
    def process(self,r):
        batch,pres,_=self.pipe.process(r);pos,mapping=token_anchors(self.pipe,batch,pres,r['payload']['text'])
        assert all(v is not None for v in pos.values())
        text=pres['rendered_prompt'];actual=batch['input_ids'][0].tolist()
        # Exact actual-token mapping has already been checked by token_anchors.
        visible=self.tokenizer.decode(actual[:pos['P_CHECKPOINT']+1],skip_special_tokens=False)
        assert 'ACTION_2:' not in visible
        record=dict(**pres,input_token_ids=actual,anchors=pos,token_alignment=mapping,checkpoint_visible_text=visible,
            actual_position_policy='NATIVE_MODEL_COMPUTE_3D_POSITION_IDS; TEXT_MODEL_NATIVE_ARANGE_WHEN_NONE')
        return dict(batch.to(self.model.device)),record
    def extended(self,inputs,tokens):
        torch=self.torch
        if not tokens:return dict(inputs)
        new=torch.tensor([tokens],device=inputs['input_ids'].device,dtype=inputs['input_ids'].dtype)
        result=dict(inputs,input_ids=torch.cat([inputs['input_ids'],new],1),attention_mask=torch.cat([inputs['attention_mask'],torch.ones_like(new)],1))
        for name in ['mm_token_type_ids','token_type_ids']:
            if name in inputs:result[name]=torch.cat([inputs[name],torch.zeros_like(new)],1)
        assert 'position_ids' not in inputs,'UNPLANNED_EXPLICIT_PROCESSOR_POSITION_IDS'
        return result
    @contextlib.contextmanager
    def hook(self,patch=None,capture=None,readonly=False):
        handles=[]
        if patch is not None:
            li,pos,vec=patch
            def change(mod,args,out):
                value=out[0] if isinstance(out,tuple) else out
                if readonly:return None
                result=value.clone();result[0,pos]=vec.to(value.device,dtype=value.dtype)
                return (result,*out[1:]) if isinstance(out,tuple) else result
            handles.append(self.layers[li].register_forward_hook(change))
        if capture is not None:
            positions,store=capture
            for li in self.depths:
                def take(mod,args,out,li=li):
                    value=out[0] if isinstance(out,tuple) else out
                    store[li]={an:value[0,p].detach().cpu().clone() for an,p in positions.items()}
                handles.append(self.layers[li].register_forward_hook(take))
        try:yield
        finally:
            for h in handles:h.remove()
    def forward(self,inputs,patch=None,keep=1,capture=None,readonly=False):
        self.model.model.rope_deltas=None
        with self.hook(patch,capture,readonly),self.torch.inference_mode():
            out=self.model(**inputs,past_key_values=None,use_cache=False,logits_to_keep=keep)
        self.forward_count+=1
        if getattr(out,'past_key_values',None) is not None:raise ValueError('CACHE_RETURNED_ON_FULL_REPLAY')
        result=out.logits[0].detach().float();del out
        return result
    def capture(self,inputs,positions):
        store={};self.forward(inputs,capture=(positions,store));return store
    def generate(self,inputs,patch=None,cap=512,readonly=False):
        start=time.monotonic();tokens=[];mins=[];self.generations+=1
        if patch is not None and not readonly:self.patched_generations+=1
        before=self.forward_count
        for _ in range(cap):
            logits=self.forward(self.extended(inputs,tokens),patch,readonly=readonly)[-1]
            top=self.torch.topk(logits,2).values;mins.append(float(top[0]-top[1]));token=int(logits.argmax());tokens.append(token)
            if token in self.eos:break
        return dict(raw_response=self.tokenizer.decode(tokens,skip_special_tokens=True,clean_up_tokenization_spaces=False),output_token_ids=tokens,
            output_tokens=len(tokens),truncated=len(tokens)==cap and tokens[-1] not in self.eos,finish_reason='eos' if tokens[-1] in self.eos else 'length',
            generation_seconds=time.monotonic()-start,forwards=self.forward_count-before,min_top2_logit_margin=min(mins),max_new_tokens=cap)
    def reference(self,inputs,cache=True,patch=None,cap=512):
        # Existing Transformers generate path and same greedy output contract.
        self.model.model.rope_deltas=None
        gc=copy.deepcopy(self.model.generation_config)
        gc.do_sample=False;gc.max_new_tokens=cap;gc.use_cache=cache;gc.temperature=None;gc.top_p=None;gc.top_k=None
        calls=[0]
        def count(mod,args):calls[0]+=1
        handle=self.model.register_forward_pre_hook(count)
        try:
            with self.hook(patch),self.torch.inference_mode():out=self.model.generate(**inputs,generation_config=gc)
        finally:handle.remove()
        self.forward_count+=calls[0];self.generations+=1
        if patch is not None:self.patched_generations+=1
        tokens=out[0,inputs['input_ids'].shape[1]:].tolist()
        return dict(output_token_ids=tokens,raw_response=self.tokenizer.decode(tokens,skip_special_tokens=True,clean_up_tokenization_spaces=False),forwards=calls[0])
    def score(self,inputs,answers,patch=None,sequential=False):
        result=[]
        for answer in answers:
            ids=self.tokenizer.encode(answer,add_special_tokens=False);n=len(ids)
            if sequential:
                lps=[]
                for j,tid in enumerate(ids):
                    logits=self.forward(self.extended(inputs,ids[:j]),patch)[-1]
                    lps.append(float(self.torch.log_softmax(logits,-1)[tid]))
            else:
                logits=self.forward(self.extended(inputs,ids),patch,keep=n+1)[:n]
                target=self.torch.tensor(ids,device=logits.device)
                lps=self.torch.log_softmax(logits,-1).gather(-1,target[:,None]).squeeze(-1).cpu().tolist()
            result.append(dict(answer=answer,token_ids=ids,token_logprobs=lps,logprob=sum(lps),includes_json_closing_brace=True))
        return result

