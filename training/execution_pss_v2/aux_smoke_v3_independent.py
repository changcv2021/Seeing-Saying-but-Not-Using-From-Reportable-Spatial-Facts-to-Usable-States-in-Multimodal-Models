"""Test CoT/state teacher-forced loss and raw dev state responses, not formal training."""
from collections import defaultdict
import sys,time
from common import *
from model_io_verified import load_engine,encode,loss_for,HP
from state_schema import parse_state

def main():
    a=cli(__doc__).parse_args();root=a.run_root;out=root/'auxiliary_smoke_v3_independent'
    if a.dry_run:print(out);return
    compute()
    if (out/'ACCEPTANCE.json').exists() and a.resume:return
    if not read(root/'SPLIT_AUDIT.json')['status'].startswith('PASS'):raise ValueError('SPLIT_NOT_ACCEPTED')
    if read(root/'prepared_data_v2/MANIFEST.json')['status']!='PASS_PREPARED_SUPERVISION':raise ValueError('SUPERVISION_NOT_ACCEPTED')
    if read(root/'environment/ENVIRONMENT.json')['status']!='PASS_CPU_IMPORT_ONLY':raise ValueError('ENVIRONMENT_NOT_ACCEPTED')
    if read(root/'processor_probe_v2/SUMMARY.json')['status']!='MEASURED_TRAIN_PROCESSOR_NO_MODEL_WEIGHTS':raise ValueError('PROCESSOR_NOT_MEASURED')
    sys.path.insert(0,str(REPO/'scripts/full_multimodel_split_v5'))
    from gpu_health import check
    out.mkdir(parents=True,exist_ok=True);check(out)
    chosen=[]
    for task in ('cot','state','trajectory'):
        path=root/'trajectory_aux_v1/train/state.jsonl' if task=='trajectory' else root/'supervision_v3/train'/(task+'.jsonl')
        if task=='state':path=root/'grounded_state_v4/train/state.jsonl'
        groups=defaultdict(list)
        for row in rows(path):groups[row['stage'] if task=='trajectory' else row['level']].append(row)
        for key,group in sorted(groups.items()):
            chosen.append(dict(task=task,stratum=key,row=min(group,key=lambda r:digest([a.seed,'aux_smoke',r.get('aux_id',r['sample_id'])]))))
        if task=='cot':chosen.append(dict(task=task,stratum='MAX_TARGET',row=max([r for group in groups.values() for r in group],key=lambda r:r['target_tokens'])))
    write(out/'FROZEN_PANEL.json',dict(seed=a.seed,selection='HASH_PER_LEVEL_OR_STAGE_PLUS_MAX_TARGET_NOT_MODEL_PERFORMANCE',
        ids=[dict(task=p['task'],stratum=p['stratum'],id=p['row'].get('aux_id',p['row']['sample_id'])) for p in chosen]))
    import torch
    model,processor,engine=load_engine(root,a.seed)
    write(out/'ENGINE.json',engine)
    optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=HP['learning_rate'],weight_decay=HP['weight_decay'])
    model.train();receipts=[]
    for index,p in enumerate(chosen):
        row=p['row'];start=time.monotonic();torch.cuda.reset_peak_memory_stats()
        if p['task']!='cot' and parse_state(row['target'])!=row['state']:raise ValueError('GOLD_STATE_ROUNDTRIP')
        batch,receipt=encode(processor,row['request'],row['target'],task_prompt=row['task_prompt'],end_turn=True)
        optimizer.zero_grad(set_to_none=True);loss=loss_for(model,batch,receipt)
        if not torch.isfinite(loss):raise ValueError('NONFINITE_LOSS')
        loss.backward();norm=torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],HP['max_grad_norm'])
        if not torch.isfinite(norm) or float(norm)==0:raise ValueError('INVALID_GRADIENT')
        optimizer.step();torch.cuda.synchronize()
        result=dict(index=index,task=p['task'],stratum=p['stratum'],sample_id=row['sample_id'],aux_id=row.get('aux_id'),
            loss=float(loss.detach()),gradient_norm=float(norm),seconds=time.monotonic()-start,
            peak_allocated_bytes=torch.cuda.max_memory_allocated(),**receipt)
        write(out/f'step_{index:03d}.json',result);receipts.append(result)
        print(json.dumps({k:result[k] for k in ('index','task','stratum','loss','seconds','peak_allocated_bytes')}),flush=True)
        del loss,batch
    model.save_pretrained(out/'engineering_adapter',safe_serialization=True);del optimizer
    model.eval();model.gradient_checkpointing_disable();dev=list(rows(root/'trajectory_aux_v1/dev/state.jsonl'));predictions=[]
    for stage in ('S0','S1','S2'):
        row=min((r for r in dev if r['stage']==stage),key=lambda r:digest([a.seed,r['aux_id']]))
        batch,receipt=encode(processor,row['request'],task_prompt=row['task_prompt'])
        with torch.inference_mode():output=model.generate(**batch.to(model.device),max_new_tokens=512,do_sample=False,use_cache=True)
        ids=output[0,receipt['prompt_tokens']:receipt['prompt_tokens']+512].tolist()
        raw=processor.decode(ids,skip_special_tokens=True,clean_up_tokenization_spaces=False)
        try:parsed=parse_state(raw);error=None
        except (ValueError,TypeError,KeyError) as exc:parsed=None;error=str(exc)
        pred=dict(sample_id=row['sample_id'],stage=stage,raw_response=raw,token_ids=ids,parsed=parsed,parse_error=error,
            exact_match_descriptive_only=parsed==row['state'],gold=row['state'])
        write(out/(stage+'_dev_raw.json'),pred);predictions.append(pred);del batch,output
    result=dict(status='PASS_AUXILIARY_TRAINING_ENGINEERING',updates=len(receipts),
        peak_allocated_bytes=max(r['peak_allocated_bytes'] for r in receipts),step_seconds=[r['seconds'] for r in receipts],
        state_gold_roundtrip=True,dev_state_outputs=len(predictions),dev_state_parsable=sum(p['parsed'] is not None for p in predictions),
        dev_state_exact_match=sum(p['exact_match_descriptive_only'] for p in predictions),
        target_scope='ONLY_AVAILABLE_PROOF_GROUNDED_SUBSET; NOT_FULL_COT_COVERAGE',
        formal_training_started=False,formal_test_started=False,raw_invalid_outputs_preserved=True,independent_of_base_smoke=True,
        shared_formal_training_admission_still_requires_both_smokes=True,
        job_id=os.environ['SLURM_JOB_ID'],code_sha256=sha(__file__))
    write(out/'ACCEPTANCE.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()


