"""Fixed technical inputs, measured resources, no mechanism selection or gold-based gate."""
import time
import importlib.util
from ssm_common import *
from contracts import parse
from interface_repair_v3.adapter import normalize
def main():
    p=cli(__doc__);p.add_argument('--model',required=True);a=p.parse_args();c,root=context(a)
    if a.dry_run:print('Fixed per-model technical preflight, no semantic retry.');return
    assert a.model in MODELS
    dest=root/'technical'/a.model;dest.mkdir(parents=True,exist_ok=True)
    if (dest/'BEHAVIOR_PREFLIGHT.json').exists():print('RETAINED_PREFLIGHT_EXISTS');return
    sys.path.insert(0,str(Path(c['project'])/'src'))
    sys.path.insert(0,str(Path(c['project'])/'research/state_binding_phase_a1/core_execution_v3'))
    import pipeline_v3
    audit=pipeline_v3.install_gold_guard()
    spec=importlib.util.spec_from_file_location('ssm_health',Path(c['project'])/'scripts/full_multimodel_split_v5/gpu_health.py')
    health=importlib.util.module_from_spec(spec);spec.loader.exec_module(health);health.check(dest)
    import torch,transformers
    from transformers import AutoModelForMultimodalLM
    torch.manual_seed(20260911);torch.cuda.manual_seed_all(20260911);torch.set_float32_matmul_precision('high')
    pipe=pipeline_v3.Pipeline(dict(c,visual_hash_version='PURE_MEDIA_TENSORS_V3_SHARED_RUNTIME'),a.model);mc=pipe.mc
    assert torch.cuda.device_count()==mc['gpus']
    kw=dict(local_files_only=True,dtype=torch.bfloat16,low_cpu_mem_usage=True,attn_implementation='sdpa')
    if mc['gpus']==1:kw['device_map']='cuda'
    else:kw.update(device_map='balanced',max_memory={i:'38GiB' for i in range(mc['gpus'])})
    t=time.monotonic();model=AutoModelForMultimodalLM.from_pretrained(mc['model_path'],**kw);model.eval();load_seconds=time.monotonic()-t
    assert not any(str(v) in ('cpu','disk') for v in getattr(model,'hf_device_map',{}).values())
    layers=[(n,m) for n,m in model.named_modules() if n.endswith('.layers') and 'language_model' in n]
    if not layers:raise ValueError('REAL_TEXT_DECODER_LAYERS_NOT_LOCATED')
    lname,ls=layers[0];mid=len(ls)//2
    save(dest/'ARCHITECTURE_MANIFEST.json',dict(model=mc,config=model.config.to_dict(),layer_container=lname,
        layers=[dict(index=i,class_name=type(m).__name__,module_path=f'{lname}.{i}',children=[(n,type(v).__name__) for n,v in m.named_children()]) for i,m in enumerate(ls)],
        torch=torch.__version__,transformers=transformers.__version__,cuda=torch.version.cuda,device_map=getattr(model,'hf_device_map',{}),
        allocated_gpu_uuids=health.allocated_uuids(),load_seconds=load_seconds,no_quantization=True))
    sample=min(rows(root/'batches/B1/public_inputs/requests.jsonl'),key=lambda r:digest([20260911,'TECH_MEDIA',r['world_cluster_id']]))
    texts=['EXACT TEST RECORD: target=3. Copy its value.', 'EXACT TEST RECORD: target=null. Copy its value; do not infer another value.',
        'EXACT TEST RECORD: target=12. Copy its value.',
        'The images are unrelated to this output-interface check. EXACT TEST RECORD: target=4. Copy its value.']
    result=[];fail=[];measured=[]
    def generate(inputs,use_cache=True):
        with torch.inference_mode():out=model.generate(**inputs,do_sample=False,max_new_tokens=512,use_cache=use_cache)
        return out[0,inputs['input_ids'].shape[1]:].tolist()
    def clone_hook(mod,inputs,output):
        return (output[0].clone(),*output[1:]) if isinstance(output,tuple) else output.clone()
    for i,text in enumerate(texts):
        r=dict(request_id=f'SSM_TECH_{i}',payload=dict(system=sample['payload']['system'],text=text+' Return exactly one JSON object with the single key "value". Use a JSON integer or literal null; no reasoning or markdown. Maximum 512 output tokens.',media=sample['payload']['media'] if i==3 else []))
        batch,pres,_=pipe.process(r);again,pres2,_=pipe.process(r)
        assert torch.equal(batch['input_ids'],again['input_ids']) and pres['presentation_hash']==pres2['presentation_hash'];del again
        inputs=batch.to(model.device)
        t=time.monotonic();base=generate(inputs);elapsed=time.monotonic()-t;measured.append(dict(input_tokens=pres['input_tokens'],seconds=elapsed,output_tokens=len(base),media_count=len(r['payload']['media'])))
        handle=ls[mid].register_forward_hook(lambda mod,inp,out:None)
        noop=generate(inputs);handle.remove()
        handle=ls[mid].register_forward_hook(clone_hook)
        self_patch=generate(inputs);handle.remove()
        uncached=generate(inputs,False)
        eq_noop=base==noop;eq_self=base==self_patch;eq_cache=base==uncached
        # A different request between two identical calls checks request-local cache ownership.
        if i:
            repeat=generate(previous_inputs)
            if repeat!=previous_base:fail.append(f'AB_CACHE_ISOLATION_{i}')
        previous_inputs=inputs;previous_base=base
        txt=pipe.processor.decode(base,skip_special_tokens=True,clean_up_tokenization_spaces=False).strip()
        parsed=normalize(txt,dict(kind='value',domain='count',nullable=True))
        row=dict(case=i,prompt=pres['rendered_prompt'],raw_response=txt,output_ids=base,noop_ids=noop,self_patch_ids=self_patch,uncached_ids=uncached,
            noop_equal=eq_noop,self_equal=eq_self,cached_uncached_equal=eq_cache,normalized=parsed,**measured[-1])
        result.append(row);print(json.dumps({k:v for k,v in row.items() if k not in ('prompt','normalized')}),flush=True)
        if not eq_noop or not eq_self:fail.append(f'HOOK_EQUIVALENCE_{i}')
        # Cache path discrepancies block whitebox claims, not the unchanged historical cached behavior engine.
    save(dest/'technical_responses.jsonl',result,'jsonl')
    schema_ok=all(r['normalized']['normalized']['status']=='VALID' for r in result)
    save(dest/'BEHAVIOR_PREFLIGHT.json',dict(behavior_execution_status='PASS' if not fail and schema_ok else 'FAILED',
        full_whitebox_T0_status='PENDING_EXTENDED_PREFIX_CAUSAL_AND_PAIR_SPECIFIC_ACCEPTANCE_NOT_AUTHORIZED_IN_B1_B2_LAUNCH',
        runner=entry(SWS_CODE/'real_worker_v1.py'),adapter=entry(HERE/'runtime.py'),request_lock_B1=entry(root/'batches/B1/manifest/REQUEST_LOCK.json'),
        request_lock_B2=entry(root/'batches/B2/manifest/REQUEST_LOCK.json'),model=mc,job=os.environ['SLURM_JOB_ID'],
        unchanged_legacy_generation_engine=True,cache_differences=sum(not r['cached_uncached_equal'] for r in result),failure_reasons=fail,
        schema_gate=schema_ok,semantic_accuracy_not_a_gate=True,no_semantic_retry=True,measurements=measured,
        load_seconds=load_seconds,peak_memory_bytes=[torch.cuda.max_memory_allocated(i) for i in range(mc['gpus'])],gold_guard=dict(audit)))
    if fail or not schema_ok:raise ValueError('TECHNICAL_PREFLIGHT_FAILED')
if __name__=='__main__':main()
