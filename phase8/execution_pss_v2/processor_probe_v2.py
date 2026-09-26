"""Measure actual processed train inputs and target tokens, without loading model weights."""
from collections import Counter,defaultdict
import statistics,time
from common import *
from model_io_verified import encode

def main():
    a=cli(__doc__).parse_args();root=a.run_root;out=root/'processor_probe_v2'
    if a.dry_run:print(out);return
    compute()
    if (out/'SUMMARY.json').exists() and a.resume:return
    from transformers import AutoProcessor
    processor=AutoProcessor.from_pretrained(MODEL,local_files_only=True,use_fast=True)
    strata={};token_totals={};panel=[]
    for task in ('answer','cot','state','trajectory'):
        path=(root/'trajectory_aux_v1/train/state.jsonl' if task=='trajectory' else root/'supervision_v3/train'/(task+'.jsonl'))
        if task=='state':path=root/'grounded_state_v4/train/state.jsonl'
        if task=='cot':path=root/'partial_cot_approved_v1/train/cot.jsonl'
        data=list(rows(path));by=defaultdict(list);nt=[]
        for row in data:
            k=row['level'] if task!='trajectory' else row['stage'];by[k].append(row)
            nt.append(len(processor.tokenizer.encode(row['target'],add_special_tokens=False))+int(row['end_turn']))
        token_totals[task]=dict(records=len(data),sum_target_tokens=sum(nt),min_target_tokens=min(nt,default=0),max_target_tokens=max(nt,default=0),
            mean_target_tokens=statistics.mean(nt) if nt else None,level_counts=dict(Counter(r['level'] for r in data)),input_sha256=sha(path))
        for k,group in sorted(by.items()):
            chosen=sorted(group,key=lambda r:digest([a.seed,task,r.get('aux_id',r['sample_id'])]))[:4]
            for row in chosen:panel.append(dict(task=task,stratum=k,row=row,selection='PREDEFINED_HASH_SAMPLE'))
        if data:panel.append(dict(task=task,stratum='STRESS_MAX_MEDIA',row=max(data,key=lambda r:(len(r['request'].get('media',[])),digest(r.get('aux_id',r['sample_id'])))),selection='MAX_MEDIA_NOT_MODEL_ERROR'))
    write(out/'FROZEN_PANEL.json',dict(seed=a.seed,ids=[dict(task=p['task'],stratum=p['stratum'],id=p['row'].get('aux_id',p['row']['sample_id']),selection=p['selection']) for p in panel]))
    measured=[]
    for index,p in enumerate(panel):
        row=p['row'];begin=time.monotonic()
        batch,receipt=encode(processor,row['request'],row['target'],task_prompt=row.get('task_prompt'),end_turn=row['end_turn'])
        record=dict(index=index,task=p['task'],stratum=p['stratum'],sample_id=row['sample_id'],aux_id=row.get('aux_id'),
            seconds=time.monotonic()-begin,**receipt)
        write(out/f'input_{index:03d}.json',record);measured.append(record);del batch
        print(json.dumps({k:record[k] for k in ('index','task','stratum','prompt_tokens','target_tokens','seconds')}),flush=True)
    for key in sorted({(r['task'],r['stratum']) for r in measured}):
        group=[r for r in measured if (r['task'],r['stratum'])==key]
        strata['/'.join(key)]=dict(n=len(group),mean_prompt_tokens=statistics.mean(r['prompt_tokens'] for r in group),
            max_prompt_tokens=max(r['prompt_tokens'] for r in group),mean_target_tokens=statistics.mean(r['target_tokens'] for r in group))
    result=dict(status='MEASURED_TRAIN_PROCESSOR_NO_MODEL_WEIGHTS',all_target_token_counts=token_totals,processed_panel=len(measured),strata=strata,
        input_statistics_scope='Hash-stratified sample plus stress inputs, NOT exact all-dataset input token totals',
        training_budget_frozen=False,test_opened=False,job_id=os.environ['SLURM_JOB_ID'],code_sha256=sha(__file__))
    write(out/'SUMMARY.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()

