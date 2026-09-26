"""Bounded block-output readouts on actual expanded processor token positions."""
import fcntl
import sys
import time
from common_auto_v2 import *
from real_processor_v1 import verify
from m1_compile_v1 import BATCH


def semantic_positions(tokenizer,ids):
    text=tokenizer.decode(ids,skip_special_tokens=False,clean_up_tokenization_spaces=False)
    encoded=tokenizer(text,add_special_tokens=False,return_offsets_mapping=True)
    if encoded['input_ids']!=ids:raise ValueError('EXPANDED_TOKEN_ROUNDTRIP_NOT_EXACT_NO_POSITION_GUESS')
    offsets=encoded['offset_mapping'];positions=[]
    def add(name,point,marker):
        hits=[i for i,(start,end) in enumerate(offsets) if start<=point<end]
        if len(hits)!=1:raise ValueError('AMBIGUOUS_SEMANTIC_TOKEN:'+name)
        pos=hits[0];positions.append(dict(name=name,token_index=pos,char_point=point,marker=marker,
            token_id=ids[pos],token_text=tokenizer.decode([ids[pos]],skip_special_tokens=False),
            prefix_token_sha256=digest(ids[:pos+1])))
    def endline(name,marker):
        start=text.find(marker)
        if start<0:raise ValueError('SEMANTIC_MARKER_MISSING:'+name)
        end=text.find('\n',start+len(marker))
        if end<0:raise ValueError('SEMANTIC_LINE_UNTERMINATED:'+name)
        add(name,end-1,marker)
    endline('observation_end','IMAGE ORDER: ');endline('target_end','TARGET: ')
    for marker in ('CANDIDATE:','IRRELEVANT REGISTER:'):
        if marker in text:
            add('role_wrapper_end',text.index(marker)+len(marker)-1,marker)
            endline('candidate_end',marker);break
    endline('query_end','\nQUERY: ')
    positions.append(dict(name='answer_start',token_index=len(ids)-1,char_point=None,marker='FINAL_GENERATION_PROMPT_TOKEN',
        token_id=ids[-1],token_text=tokenizer.decode([ids[-1]],skip_special_tokens=False),prefix_token_sha256=digest(ids)))
    if len(positions)>6:raise ValueError('POSITION_CAP')
    return positions


def main():
    a=arguments(__doc__).parse_args();c,root=setup(a);out=root/'whitebox'/BATCH;lockpath=out/'manifest/M1_LOCK.json';lock=load(lockpath)
    verify(lock['code']+lock['public_inputs']+[lock['m0'],lock['source_processor']])
    if load(lock['m0']['path'])['status']!='PASS':raise ValueError('M0_REQUIRED')
    if not load(root/'scheduler/resource_authorization.json')['approved']:raise ValueError('RESOURCE_AUTHORITY_REQUIRED')
    directory=out/'measurements';directory.mkdir(parents=True,exist_ok=True)
    owner=(directory/'writer.lock').open('a');fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
    project=Path(c['project']);sys.path.insert(0,str(project/'src'));sys.path.insert(0,str(project/'research/state_binding_phase_a1/core_execution_v3'))
    import pipeline_v3,importlib.util
    spec=importlib.util.spec_from_file_location('m1_health',project/'scripts/full_multimodel_split_v5/gpu_health.py')
    health=importlib.util.module_from_spec(spec);spec.loader.exec_module(health);health.check(directory)
    inventory=load(Path(c['b0'])/'manifest/model_inventory.json');mc0=next(m for m in inventory if m['key']=='qwen35_9b')
    verify([mc0[k] for k in ('manifest','index','config')])
    if any(Path(r['path']).stat().st_size!=r['bytes'] for r in mc0['shard_sizes']):raise ValueError('MODEL_CHANGED')
    pre=load(lock['source_processor']['path']);verify([pre['records']])
    expected={r['request_id']:r for r in rows(pre['records']['path'])}
    audit=pipeline_v3.install_gold_guard()
    import torch,transformers
    from transformers import AutoModelForMultimodalLM
    if torch.cuda.device_count()!=1:raise ValueError('M1_9B_ONE_GPU')
    torch.manual_seed(c['seed']);torch.cuda.manual_seed_all(c['seed']);torch.set_float32_matmul_precision('high')
    pipe=pipeline_v3.Pipeline(dict(c,visual_hash_version='PURE_MEDIA_TENSORS_V3_SHARED_RUNTIME'),'qwen35_9b')
    started=time.monotonic();model=AutoModelForMultimodalLM.from_pretrained(pipe.mc['model_path'],local_files_only=True,dtype=torch.bfloat16,
        device_map='cuda',attn_implementation='sdpa',low_cpu_mem_usage=True);model.eval();layers=model.model.language_model.layers
    job=os.environ['SLURM_JOB_ID'];lockhash=sha(lockpath)
    save(directory/f'environment_{job}.json',dict(model=pipe.mc,torch=torch.__version__,transformers=transformers.__version__,
        load_seconds=time.monotonic()-started,gpu_uuids=health.allocated_uuids(),
        modules=[dict(layer=i,name=f'model.language_model.layers.{i}',block_type=m.block_type) for i,m in enumerate(layers)]))
    reqs=list(rows(out/'public_inputs/requests.jsonl'));results=[];previous=None
    for n,r in enumerate(reqs,1):
        path=directory/'records'/(r['request_id']+'.json')
        if path.exists():
            old=load(path)
            if old['runtime_lock_sha256']!=lockhash:raise ValueError('RETAINED_LOCK_CHANGED')
            results.append(old);continue
        if previous!=r['world_cluster_id']:pipe.image_cache.clear();previous=r['world_cluster_id']
        batch,pres,_=pipe.process(r);ids=batch['input_ids'][0].tolist();want=expected[r['request_id']]
        if (pres['presentation_hash'],pres['rendered_prompt_sha256'],ids)!=(want['presentation_hash'],want['rendered_prompt_sha256'],want['input_token_ids']):raise ValueError('ACTUAL_PROCESSOR_BRIDGE_FAILED')
        record=dict(request_id=r['request_id'],world_cluster_id=r['world_cluster_id'],model_id='qwen35_9b',
            request_hash=r['model_independent_request_hash'],runtime_lock_sha256=lockhash,
            rendered_prompt=pres['rendered_prompt'],prompt_hash=pres['rendered_prompt_sha256'],
            visual_tensor_sha256=pres['presentation_hash'],input_token_ids=ids,job_id=job,
            measurement='PREFILL_BLOCK_OUTPUT_SELECTED_POSITIONS_ONLY',actual_generations=0,causal_interventions=0)
        try:positions=semantic_positions(pipe.processor.tokenizer,ids)
        except ValueError as exc:
            record.update(status='POSITION_NOT_IDENTIFIABLE',error=str(exc));save(path,record);results.append(record);continue
        inputs=batch.to(model.device);indices=[p['token_index'] for p in positions];captured={}
        def hook(i):
            def observe(module,args,output):
                if not torch.is_tensor(output) or output.ndim!=3:raise ValueError('HOOK_OUTPUT_CONTRACT_CHANGED')
                captured[i]=output[0,indices,:].detach().clone().cpu().contiguous()
                return None
            return observe
        t=time.monotonic()
        with torch.inference_mode():
            torch.cuda.reset_peak_memory_stats();model.model.rope_deltas=None
            off=model(**inputs,use_cache=False,logits_to_keep=1).logits[0,-1].float().cpu()
            handles=[m.register_forward_hook(hook(i)) for i,m in enumerate(layers)]
            try:
                model.model.rope_deltas=None
                on=model(**inputs,use_cache=False,logits_to_keep=1).logits[0,-1].float().cpu()
            finally:
                for h in handles:h.remove()
        delta=float((off-on).abs().max());exact=int(off.argmax())==int(on.argmax())
        if set(captured)!=set(range(len(layers))):raise ValueError('MISSING_BLOCK_READOUT')
        if delta>lock['noop_last_logit_abs_tolerance'] or not exact:
            record.update(status='HOOK_NOT_EQUIVALENT',max_abs_logit_difference=delta,argmax_equal=exact)
            save(path,record);results.append(record);break
        tensors=directory/'hidden'/(r['request_id']+'.pt');tensors.parent.mkdir(parents=True,exist_ok=True)
        temporary=tensors.with_name(tensors.name+'.'+job+'.tmp')
        torch.save(dict(hidden=torch.stack([captured[i] for i in range(len(layers))]),positions=positions),temporary)
        if tensors.exists():
            prior=torch.load(tensors,map_location='cpu',weights_only=True)
            if prior['positions']!=positions or not torch.equal(prior['hidden'],torch.stack([captured[i] for i in range(len(layers))])):raise ValueError('EXISTING_HIDDEN_PAYLOAD_DIFFERS')
        else:os.link(temporary,tensors)
        temporary.unlink()
        record.update(status='MEASUREMENT_RECORDED',positions=positions,hidden=entry(tensors),
            max_abs_logit_difference=delta,argmax_equal=exact,hook_noop_pass=True,
            first_token_argmax=int(off.argmax()),seconds=time.monotonic()-t,peak_memory_bytes=torch.cuda.max_memory_allocated(),
            gold_access_audit=dict(audit));save(path,record);results.append(record)
        del batch,inputs,captured,off,on
        if n<=3 or n%10==0:print(json.dumps(dict(stage='M1_READOUT',retained=n,planned=len(reqs),status=record['status'])),flush=True)
    save(directory/'response_index.json',[entry(directory/'records'/(r['request_id']+'.json')) for r in results])
    report=dict(status='COLLECTION_COMPLETE' if len(results)==len(reqs) and all(r['status']=='MEASUREMENT_RECORDED' for r in results) else 'COLLECTION_PARTIAL_OR_NOT_IDENTIFIABLE',
        planned=len(reqs),records=len(results),measured=sum(r['status']=='MEASUREMENT_RECORDED' for r in results),
        world_count=len({r['world_cluster_id'] for r in results}),readability_conclusion='NOT_ESTABLISHED_BY_COLLECTION',
        causal_conclusion='NOT_ESTABLISHED',gold_access_audit=dict(audit),job_id=job)
    save(directory/'M1_ACCEPTANCE.json',report);print(json.dumps(report),flush=True)


if __name__=='__main__':main()
