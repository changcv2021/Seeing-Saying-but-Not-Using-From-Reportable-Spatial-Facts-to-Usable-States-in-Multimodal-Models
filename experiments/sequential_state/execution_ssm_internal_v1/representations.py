"""Read-only fixed residual anchors with independent technical calibration, no causal edits."""
import time,copy,importlib.util
from internal_common import *

def token_anchors(pipe,batch,pres,body):
    text=pres['rendered_prompt'];tok=pipe.processor.tokenizer
    base=tok(text,add_special_tokens=False,return_offsets_mapping=True)
    actual=batch['input_ids'][0].tolist();mapping=[];j=0
    imageid=tok.convert_tokens_to_ids('<|image_pad|>')
    for tid in base['input_ids']:
        if j>=len(actual) or actual[j]!=tid:raise ValueError('EXPANDED_TOKEN_ALIGNMENT_FAILED')
        if tid==imageid:
            while j+1<len(actual) and actual[j+1]==imageid:j+=1
        mapping.append(j);j+=1
    if j!=len(actual):raise ValueError('EXPANDED_TOKEN_TAIL_MISMATCH')
    start=text.index(body)
    def boundary(marker,before=False):
        pos=body.find(marker)
        if pos<0:return None
        end=pos if before else body.find('\n',pos)
        if end<0:end=len(body)
        absolute=start+end
        inds=[i for i,(lo,hi) in enumerate(base['offset_mapping']) if hi<=absolute and hi>lo]
        return mapping[inds[-1]] if inds else None
    result={'P_PRE':boundary('ACTION_1:',True),'P_A1':boundary('ACTION_1:'),'P_CHECKPOINT':boundary('STATE_NOTE:'),
        'P_A2':boundary('ACTION_2:'),'P_QUERY':boundary('OUTPUT CONTRACT:',True)}
    aliases={}
    if result['P_CHECKPOINT'] is None and result['P_A1'] is not None:
        result['P_CHECKPOINT']=result['P_A1'];aliases['P_CHECKPOINT']='P_A1; NO_EXPLICIT_CHECKPOINT_SLOT_IN_SYMBOLIC_INPUT'
    return result,dict(base_token_ids=base['input_ids'],character_offsets=base['offset_mapping'],expanded_positions=mapping,aliases=aliases)

def main():
    p=cli(__doc__);p.add_argument('--model',required=True);a=p.parse_args();c,out=setup(a)
    if a.dry_run:print('416 fixed contexts, 8 residual layers, pre-answer anchors; no patch or outcome selection.');return
    assert a.model in MODELS;verify_lock(False)
    dest=out/'representations'/a.model;dest.mkdir(parents=True,exist_ok=True)
    if (dest/'EXTRACTION_ACCEPTANCE.json').exists():print('EXISTING_EXTRACTION_RETAINED');return
    sys.path.insert(0,str(Path(c['project'])/'src'));sys.path.insert(0,str(Path(c['project'])/'research/state_binding_phase_a1/core_execution_v3'))
    import pipeline_v3
    guard=pipeline_v3.install_gold_guard()
    spec=importlib.util.spec_from_file_location('ssm_r1_health',Path(c['project'])/'scripts/full_multimodel_split_v5/gpu_health.py')
    health=importlib.util.module_from_spec(spec);spec.loader.exec_module(health);health.check(dest)
    import torch,transformers
    from transformers import AutoModelForMultimodalLM
    torch.manual_seed(20260911);torch.cuda.manual_seed_all(20260911);torch.set_float32_matmul_precision('high')
    pipe=pipeline_v3.Pipeline(dict(c,visual_hash_version='PURE_MEDIA_TENSORS_V3_SHARED_RUNTIME'),a.model);mc=pipe.mc
    assert torch.cuda.device_count()==mc['gpus']
    kw=dict(local_files_only=True,dtype=torch.bfloat16,low_cpu_mem_usage=True,attn_implementation='sdpa')
    if mc['gpus']==1:kw['device_map']='cuda'
    else:kw.update(device_map='balanced',max_memory={i:'38GiB' for i in range(mc['gpus'])})
    started=time.monotonic();model=AutoModelForMultimodalLM.from_pretrained(mc['model_path'],**kw);model.eval();loadsec=time.monotonic()-started
    assert not any(str(v) in ('cpu','disk') for v in getattr(model,'hf_device_map',{}).values())
    layers=model.model.language_model.layers;indices=sorted({round(i*(len(layers)-1)/7) for i in range(8)})
    requests=list(rows(out/'public_inputs/r1_requests.jsonl'));assert len(requests)==416
    def clear():model.model.rope_deltas=None
    def forward(inputs,positions=None,clone=False):
        captured={};handles=[]
        def capture_positions(mod,args,kwargs):
            value=kwargs.get('position_ids')
            if value is not None:captured['_position_ids']=value.detach().cpu().clone()
        handles.append(model.model.language_model.register_forward_pre_hook(capture_positions,with_kwargs=True))
        for li in indices:
            def hook(mod,args,output,li=li):
                tensor=output[0] if isinstance(output,tuple) else output
                if positions:
                    captured[li]={k:tensor[0,i].detach().float().cpu().clone() for k,i in positions.items() if i is not None}
                if clone:return (tensor.clone(),*output[1:]) if isinstance(output,tuple) else tensor.clone()
                return None
            handles.append(layers[li].register_forward_hook(hook))
        try:
            clear()
            with torch.inference_mode():res=model(**inputs,use_cache=False,logits_to_keep=1)
            logits=res.logits[0,-1].detach().float().cpu();del res
        finally:
            for h in handles:h.remove()
        return logits,captured
    # Calibrate before any new mechanism-context forward; semantic outcomes do not select these inputs.
    media=min(requests,key=lambda r:digest([20260911,'R1_TECH_MEDIA',r['world_cluster_id']]))['payload']['media']
    tech=[];max_prefix_rel=0.;max_lp=0.;failed=[]
    techbody='SYMBOLIC REGISTER: S0=2.\nACTION_1: add exactly 2 units.\nSTATE_NOTE: '
    for i,(value,mm) in enumerate([(3,[]),(12,[]),(None,media[:1]),(4,media)]):
        common=techbody
        tail=f'The unrelated register value is {json.dumps(value)}.\nACTION_2: add exactly 1 unit.\nQUERY: Copy the explicitly specified unrelated register value.\nOUTPUT CONTRACT: Return JSON with one key value and an integer or null, within 512 tokens.'
        r=dict(request_id=f'R1_TECH_{i}',payload=dict(system=requests[0]['payload']['system'],text=common+tail,media=mm))
        batch,pres,_=pipe.process(r);pos,mapping=token_anchors(pipe,batch,pres,r['payload']['text']);inputs=batch.to(model.device)
        clear()
        with torch.inference_mode():res=model(**inputs,use_cache=False,logits_to_keep=1)
        plain=res.logits[0,-1].float().cpu();del res
        hooked,cap=forward(inputs,pos);selflog,_=forward(inputs,pos,True)
        if not torch.equal(plain,hooked) or not torch.equal(plain,selflog):failed.append(f'READONLY_SELF_PREFILL_{i}')
        before=forward(inputs,pos)[0]
        alternate=copy.deepcopy(r);alternate['payload']['text']=common+'The unrelated register value is 19.\nACTION_2: add exactly 1 unit.\nQUERY: Copy that register value.\nOUTPUT CONTRACT: Return JSON with key value.'
        b2,p2,_=pipe.process(alternate);apos,_=token_anchors(pipe,b2,p2,alternate['payload']['text']);alt=b2.to(model.device);_,acap=forward(alt,apos)
        prefix_index=pos['P_A1'];assert inputs['input_ids'][0,:prefix_index+1].tolist()==alt['input_ids'][0,:apos['P_A1']+1].tolist()
        diffs=[]
        for li in indices:
            v,z=cap[li]['P_A1'],acap[li]['P_A1'];rel=float((v-z).square().mean().sqrt()/(v.square().mean().sqrt()+1e-8));diffs.append(rel)
        max_prefix_rel=max(max_prefix_rel,*diffs)
        again,_=forward(inputs,pos)
        if not torch.equal(before,again):failed.append(f'AB_PREFILL_ISOLATION_{i}')
        # Full candidate strings with termination brace, independent technical values; never first-digit-only scores.
        cand=[]
        for answer in ['{"value":0}','{"value":12}','{"value":null}']:
            tokens=torch.tensor([pipe.processor.tokenizer.encode(answer,add_special_tokens=False)],device=model.device);n=tokens.shape[1];length=inputs['input_ids'].shape[1]
            full=dict(inputs,input_ids=torch.cat([inputs['input_ids'],tokens],1),attention_mask=torch.cat([inputs['attention_mask'],torch.ones_like(tokens)],1))
            if 'mm_token_type_ids' in inputs:full['mm_token_type_ids']=torch.cat([inputs['mm_token_type_ids'],torch.zeros_like(tokens)],1)
            clear()
            with torch.inference_mode():res=model(**full,use_cache=False,logits_to_keep=n+1)
            lp=torch.log_softmax(res.logits[0,:n].float(),-1).gather(-1,tokens[0,:,None].to(res.logits.device)).squeeze(-1).cpu();arg=res.logits[0,:n].argmax(-1).cpu().tolist();del res
            clear()
            with torch.inference_mode():res=model(**inputs,use_cache=True,logits_to_keep=1)
            cache=res.past_key_values;delta=model.model.rope_deltas.detach().clone();logits=res.logits[0,-1].float();del res
            inc=[];args=[]
            for j in range(n):
                inc.append(float(torch.log_softmax(logits,-1)[int(tokens[0,j])]));args.append(int(logits.argmax()))
                if j<n-1:
                    model.model.rope_deltas=delta.clone()
                    position=torch.tensor([[[length+j]]],device=model.device).expand(3,1,1)+delta.to(model.device).view(1,1,1)
                    with torch.inference_mode():res=model(input_ids=tokens[:,j:j+1],attention_mask=torch.ones((1,length+j+1),device=model.device,dtype=inputs['attention_mask'].dtype),position_ids=position,past_key_values=cache,use_cache=True,logits_to_keep=1)
                    logits=res.logits[0,-1].float();cache=res.past_key_values;del res
            diff=max(abs(float(x)-y) for x,y in zip(lp,inc));max_lp=max(max_lp,diff)
            cand.append(dict(answer=answer,full_lp=lp.tolist(),incremental_lp=inc,max_abs=diff,argmax_differences=sum(x!=y for x,y in zip(arg,args))))
            del cache,logits,full
        tech.append(dict(case=i,input_tokens=pres['input_tokens'],media_count=len(mm),prompt=pres['rendered_prompt'],anchors=pos,
            prefix_relative_rms=diffs,readonly_exact=torch.equal(plain,hooked),self_exact=torch.equal(plain,selflog),candidates=cand))
        del inputs,alt,batch,b2;pipe.image_cache.clear()
    if max_prefix_rel>.01:failed.append('PREFIX_CAUSAL_INVARIANCE_TECH_FAILED')
    save(dest/'T0_TECHNICAL_RECORDS.json',tech)
    save(dest/'TOLERANCE_LOCK.json',dict(calibrated_before_mechanism_forwards=True,source=entry(dest/'T0_TECHNICAL_RECORDS.json'),
        prefix_relative_rms_tolerance=max(1e-4,2*max_prefix_rel),candidate_token_lp_tolerance=max(.02,2*max_lp),
        cache_difference_above_calibration_safety_ceiling=max_lp>.5,failure_reasons=failed))
    gate=dict(status='PASS_READONLY_EXTRACTION' if not failed else 'FAILED_NO_R1_EXTRACTION',
        full_intervention_T0='PENDING_PAIR_SPECIFIC_CHANGED_ACTIVATION_RECOMPUTATION_AND_FREE_GENERATION_TESTS',
        no_intervention_test_faked=True,candidate_cache_max_lp_difference=max_lp,candidate_cache_argmax_differences=sum(x['argmax_differences'] for r in tech for x in r['candidates']),
        tolerance=entry(dest/'TOLERANCE_LOCK.json'),model=mc,job_id=os.environ['SLURM_JOB_ID'])
    save(dest/'T0_EXTRACTION_ACCEPTANCE.json',gate)
    if failed:raise ValueError('READ_ONLY_EXTRACTION_TECH_FAILED')
    # Pre-answer residual features only; no generation and no target labels opened.
    expected={};wanted={r['request_id'] for r in requests}
    for b in ('B1','B2'):
        ac=load(ROOT/'batches'/b/'review'/a.model/'PROCESSOR_ACCEPTANCE.json');check(ac['records'])
        assert ac['status']=='PASS'
        expected.update({r['request_id']:r for r in rows(ac['records']['path']) if r['request_id'] in wanted})
    items=[];features=[];previous=None
    for k,r in enumerate(requests):
        if previous!=r['world_cluster_id']:pipe.image_cache.clear();previous=r['world_cluster_id']
        batch,pres,_=pipe.process(r);pos,mapping=token_anchors(pipe,batch,pres,r['payload']['text']);inputs=batch.to(model.device)
        want=expected[r['request_id']]
        if (pres['presentation_hash'],pres['rendered_prompt_sha256'],inputs['input_ids'][0].tolist())!=(want['presentation_hash'],want['rendered_prompt_sha256'],want['input_token_ids']):raise ValueError('R1_ACTUAL_PROCESSOR_BRIDGE_CHANGED')
        t=time.monotonic();logits,cap=forward(inputs,pos);elapsed=time.monotonic()-t
        tensor=torch.stack([torch.stack([cap[li][an] for an in ['P_PRE','P_A1','P_CHECKPOINT','P_A2','P_QUERY']]) for li in indices]).to(torch.bfloat16)
        features.append(tensor)
        items.append(dict(request_id=r['request_id'],world_cluster_id=r['world_cluster_id'],split=r['split'],condition=r['r1_condition'],batch=r['batch'],
            input_tokens=pres['input_tokens'],input_token_ids=inputs['input_ids'][0].tolist(),rendered_prompt=pres['rendered_prompt'],text=r['payload']['text'],
            presentation_hash=pres['presentation_hash'],visual=pres['visual'],text_auxiliary=pres['text_auxiliary'],anchors=pos,token_alignment=mapping,
            actual_position_ids=cap['_position_ids'].tolist() if '_position_ids' in cap else None,rope_deltas=model.model.rope_deltas.tolist(),
            next_token_argmax=int(logits.argmax()),forward_seconds=elapsed))
        del inputs,batch,cap
        if (k+1)%40==0:print(json.dumps(dict(model=a.model,contexts=k+1,total=len(requests))),flush=True)
    target=dest/'anchor_residuals.pt'
    if target.exists():raise ValueError('REFUSE_OVERWRITE_ACTIVATIONS')
    torch.save(dict(features=torch.stack(features),request_ids=[r['request_id'] for r in items],layers=indices,anchors=['P_PRE','P_A1','P_CHECKPOINT','P_A2','P_QUERY']),target)
    save(dest/'activation_index.jsonl',items,'jsonl')
    save(dest/'EXTRACTION_ACCEPTANCE.json',dict(status='COMPLETE_READONLY_REPRESENTATIONS_NOT_MECHANISM_PROOF',model=mc,contexts=len(items),
        activations=entry(target),index=entry(dest/'activation_index.jsonl'),T0=entry(dest/'T0_EXTRACTION_ACCEPTANCE.json'),
        layers=[dict(index=i,module=f'model.language_model.layers.{i}',layer_type=getattr(layers[i],'block_type',None)) for i in indices],
        intervention_trials=0,new_behavior_answers=0,job_id=os.environ['SLURM_JOB_ID'],gold_access_audit=dict(guard),load_seconds=loadsec,
        actual_r1_forwards=len(items),technical_records=entry(dest/'T0_TECHNICAL_RECORDS.json'),peak_memory=[torch.cuda.max_memory_allocated(i) for i in range(mc['gpus'])]))
    print(json.dumps(dict(model=a.model,status='R1_EXTRACTED',contexts=len(items))),flush=True)
if __name__=='__main__':main()
