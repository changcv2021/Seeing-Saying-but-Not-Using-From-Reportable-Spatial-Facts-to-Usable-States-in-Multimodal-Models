"""Actual bounded block-output interventions; no mechanism or confirmation claims."""
import fcntl
import importlib.util
import sys
import time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from common_auto_v2 import *
from real_processor_v1 import verify
from m1_worker_v1 import semantic_positions
from prepare import NAME


def main():
    parser=arguments(__doc__);parser.add_argument('--mode',choices=['pilot','coarse'],required=True);parser.add_argument('--shard',type=int,required=True)
    a=parser.parse_args();c,root=setup(a)
    if a.dry_run:print('Gold-blind patched full-sequence likelihoods, exact token alignment, explicit no-op/self checks.');return
    out=root/'whitebox'/NAME;lp=out/'manifest/M2_PROTOCOL_LOCK.json';lock=load(lp)
    verify(lock['code']+lock['public_inputs']+[lock['m0'],lock['source_processor']])
    if load(lock['m0']['path'])['status']!='PASS':raise ValueError('M0_REQUIRED')
    if not load(root/'scheduler/resource_authorization.json')['approved']:raise ValueError('RESOURCE_AUTHORITY_REQUIRED')
    if a.mode=='pilot' and a.shard not in lock['pilot_shards']:raise ValueError('UNPLANNED_PILOT_WORLD')
    if a.mode=='coarse':
        for sid in lock['pilot_shards']:
            acc=load(out/f'pilot/shard_{sid:03}/ACCEPTANCE.json')
            if acc['status']!='TECHNICAL_PASS':raise ValueError('MEASURED_PILOT_REQUIRED')
    plan=next(r for r in rows(out/'public_inputs/operations.jsonl') if r['shard']==a.shard)
    requests={r['request_id']:r for r in rows(out/'public_inputs/requests.jsonl')}
    directory=out/a.mode/f'shard_{a.shard:03}';directory.mkdir(parents=True,exist_ok=True)
    owner=(directory/'writer.lock').open('a');fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (directory/'ACCEPTANCE.json').exists():print('EXISTING_ACCEPTANCE_RETAINED_NO_ANSWER_RETRY');return
    project=Path(c['project']);sys.path.insert(0,str(project/'src'));sys.path.insert(0,str(project/'research/state_binding_phase_a1/core_execution_v3'))
    import pipeline_v3
    spec=importlib.util.spec_from_file_location('m2_health',project/'scripts/full_multimodel_split_v5/gpu_health.py')
    health=importlib.util.module_from_spec(spec);spec.loader.exec_module(health);health.check(directory)
    inventory=load(Path(c['b0'])/'manifest/model_inventory.json');mc0=next(m for m in inventory if m['key']=='qwen35_9b')
    verify([mc0[k] for k in ('manifest','index','config')])
    if any(Path(r['path']).stat().st_size!=r['bytes'] for r in mc0['shard_sizes']):raise ValueError('MODEL_CHANGED')
    pre=load(lock['source_processor']['path']);verify([pre['records']]);expected={r['request_id']:r for r in rows(pre['records']['path'])}
    audit=pipeline_v3.install_gold_guard()
    import torch,transformers
    from transformers import AutoModelForMultimodalLM
    if torch.cuda.device_count()!=1:raise ValueError('M2_9B_ONE_GPU_REQUIRED')
    torch.manual_seed(c['seed']);torch.cuda.manual_seed_all(c['seed']);torch.set_float32_matmul_precision('high')
    pipe=pipeline_v3.Pipeline(dict(c,visual_hash_version='PURE_MEDIA_TENSORS_V3_SHARED_RUNTIME'),'qwen35_9b')
    start=time.monotonic()
    model=AutoModelForMultimodalLM.from_pretrained(pipe.mc['model_path'],local_files_only=True,dtype=torch.bfloat16,
        device_map='cuda',attn_implementation='sdpa',low_cpu_mem_usage=True);model.eval()
    layers=model.model.language_model.layers
    selected=sorted({0,len(layers)//2,len(layers)-1}) if a.mode=='pilot' else sorted({round(i*(len(layers)-1)/7) for i in range(8)})
    posnames=lock['pilot_positions'] if a.mode=='pilot' else lock['positions']
    save(directory/'environment.json',dict(model=pipe.mc,torch=torch.__version__,transformers=transformers.__version__,load_seconds=time.monotonic()-start,
        gpu_uuids=health.allocated_uuids(),selected_layers=selected,semantic_positions=posnames,job_id=os.environ['SLURM_JOB_ID'],lock_sha256=sha(lp)))
    processed={};cache={};records=[];failure=None;peak=0

    def process(rid):
        if rid not in processed:
            batch,pres,_=pipe.process(requests[rid]);ids=batch['input_ids'][0].tolist();want=expected[rid]
            if (pres['presentation_hash'],pres['rendered_prompt_sha256'],ids)!=(want['presentation_hash'],want['rendered_prompt_sha256'],want['input_token_ids']):
                raise ValueError('ACTUAL_PROCESSOR_BRIDGE_FAILED:'+rid)
            positions={p['name']:p for p in semantic_positions(pipe.processor.tokenizer,ids)}
            processed[rid]=(batch,pres,positions)
            save(directory/'inputs'/(rid+'.json'),dict(request_id=rid,prompt=pres['rendered_prompt'],prompt_sha256=pres['rendered_prompt_sha256'],
                presentation_hash=pres['presentation_hash'],positions=positions,input_token_ids=ids,media=requests[rid]['payload']['media']))
        return processed[rid]

    def full_inputs(rid,answer):
        batch,_,_=process(rid);inputs=batch.to(model.device)
        tokens=torch.tensor([pipe.processor.tokenizer.encode(answer,add_special_tokens=False)],device=model.device)
        full=dict(inputs);full['input_ids']=torch.cat([inputs['input_ids'],tokens],dim=1)
        full['attention_mask']=torch.cat([inputs['attention_mask'],torch.ones_like(tokens)],dim=1)
        if 'mm_token_type_ids' in inputs:full['mm_token_type_ids']=torch.cat([inputs['mm_token_type_ids'],torch.zeros_like(tokens)],dim=1)
        return full,tokens

    def forward(full,tokens):
        model.model.rope_deltas=None
        n=tokens.shape[-1];output=model(**full,use_cache=False,logits_to_keep=n+1)
        logits=output.logits[0,:n].float()
        lpv=torch.log_softmax(logits,dim=-1).gather(-1,tokens[0,:,None]).squeeze(-1)
        return dict(sequence_logprob=float(lpv.sum()),token_logprobs=lpv.tolist(),answer_token_ids=tokens[0].tolist())

    def baseline(rid,answer):
        key=(rid,answer)
        if key in cache:return cache[key]
        full,tokens=full_inputs(rid,answer);_,_,positions=process(rid);captures={}
        def observer(i):
            def h(module,args,output):
                if not torch.is_tensor(output) or output.ndim!=3:raise ValueError('HOOK_OUTPUT_CONTRACT_CHANGED')
                captures[i]={name:output[0,p['token_index'],:].detach().clone().cpu() for name,p in positions.items()}
                return None
            return h
        handles=[layers[i].register_forward_hook(observer(i)) for i in selected]
        try:value=forward(full,tokens)
        finally:
            for h in handles:h.remove()
        cache[key]=(value,captures)
        return cache[key]

    try:
        with torch.inference_mode():
            for operation in plan['operations']:
                donor,recipient=operation['donor'],operation['recipient']
                for answer in operation['evaluation_sequences']:
                    original,_=baseline(recipient,answer);_,captured=baseline(donor,answer)
                    _,_,rp=process(recipient);_,_,dp=process(donor)
                    full,tokens=full_inputs(recipient,answer)
                    for layer in selected:
                        for pname in posnames:
                            source_name=operation['donor_position_override'] or pname
                            if source_name not in dp or pname not in rp:raise ValueError('SEMANTIC_POSITION_NOT_IDENTIFIABLE')
                            # Empty interventions / self replacements are real numerical controls.
                            vector=captured[layer][source_name].to(model.device)
                            target_index=rp[pname]['token_index'];hits=[0]
                            def patch(module,args,output):
                                if not torch.is_tensor(output) or output.ndim!=3 or tuple(vector.shape)!=tuple(output[0,target_index].shape):
                                    raise ValueError('NO_PADDING_OR_TRUNCATION_ALLOWED')
                                changed=output.clone();changed[0,target_index,:]=vector;hits[0]+=1;return changed
                            # No-op clone is checked on every case, independent of model answers.
                            noop=layers[layer].register_forward_hook(lambda module,args,output:output.clone())
                            try:no=forward(full,tokens)
                            finally:noop.remove()
                            nd=abs(no['sequence_logprob']-original['sequence_logprob'])
                            if nd>lock['hook_noop_logprob_abs_tolerance']:raise ValueError('NOOP_NOT_EQUIVALENT:'+str(nd))
                            h=layers[layer].register_forward_hook(patch);t=time.monotonic();torch.cuda.reset_peak_memory_stats()
                            try:value=forward(full,tokens)
                            finally:h.remove()
                            elapsed=time.monotonic()-t;peak=max(peak,torch.cuda.max_memory_allocated())
                            if hits[0]!=1:raise ValueError('PATCH_COUNT_NOT_EXACTLY_ONE')
                            delta=value['sequence_logprob']-original['sequence_logprob']
                            selfpass=operation['name']!='SELF_REPLACEMENT' or abs(delta)<=lock['self_replacement_logprob_abs_tolerance']
                            rec=dict(operation_id=operation['operation_id'],condition=operation['name'],endpoint=operation['endpoint'],
                                world_cluster_id=plan['world_cluster_id'],family=plan['family'],split='discovery',mode=a.mode,
                                model_id='qwen35_9b',donor_request_id=donor,recipient_request_id=recipient,
                                layer=layer,block_type=layers[layer].block_type,donor_position=dp[source_name],recipient_position=rp[pname],
                                evaluation_sequence=answer,baseline=original,patched=value,raw_sequence_logprob_delta=delta,
                                noop_sequence_logprob_delta=nd,self_check_pass=selfpass,seconds=elapsed,peak_memory_bytes=peak,
                                status='MEASURED' if selfpass else 'SELF_NOT_EQUIVALENT',job_id=os.environ['SLURM_JOB_ID'],
                                runtime_lock_sha256=sha(lp),gold_access_audit=dict(audit),actual_open_ended_generations=0)
                            key=digest([operation['operation_id'],answer,layer,pname]);target=directory/'records'/(key+'.json')
                            save(target,rec);records.append(entry(target))
                            if not selfpass:raise ValueError('SELF_REPLACEMENT_NOT_EQUIVALENT:'+str(delta))
                print(json.dumps(dict(stage=a.mode,world=plan['world_cluster_id'],operation=operation['name'],measurements=len(records))),flush=True)
    except Exception as exc:
        failure=dict(type=type(exc).__name__,message=str(exc))
        save(directory/'FAILURE.json',failure)
    report=dict(status=('TECHNICAL_PASS' if a.mode=='pilot' else 'COARSE_MEASUREMENTS_COMPLETE') if failure is None else 'TECHNICAL_FAILURE_NO_AUTOMATIC_ANSWER_RETRY',
        world_cluster_id=plan['world_cluster_id'],worlds=1,mode=a.mode,measurements=len(records),failure=failure,
        elapsed_seconds=time.monotonic()-start,peak_memory_bytes=peak,processed_inputs=len(processed),
        job_id=os.environ['SLURM_JOB_ID'],gold_access_audit=dict(audit),actual_causal_interventions=len(records),
        validation_complete=False,mechanism_lock=False,C2_complete=False,raw_index=records)
    save(directory/'ACCEPTANCE.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='raw_index'}),flush=True)
    if failure:raise SystemExit(2)

if __name__=='__main__':main()
