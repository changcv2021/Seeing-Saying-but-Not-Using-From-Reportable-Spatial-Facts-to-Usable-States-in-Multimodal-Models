"""Source-only smoke freeze and three independent CPU processor preflights."""
import sys
from common import *

def main():
    p=arguments(__doc__); p.add_argument('--model',choices=['qwen35_4b','qwen35_9b','qwen35_27b']); a=p.parse_args(); c,root=setup(a)
    if a.dry_run: print('Fixed E9 + unchanged reviewed B0-A processor smoke, no inference'); return
    if a.model is None:
        er=list(rows(root/'public_inputs/E9/requests.jsonl'))
        # Fixed condition coverage independent of any response: eight symbolic requests.
        symbolic=[]
        for spatial in (False,True):
            for missing in (False,True):
                for kind in ('value','verdict'):
                    candidates=[r for r in er if r['spatial_symbolic']==spatial and r['target_missing']==missing and r['schema']['kind']==kind and r['presentation']=='TABLE']
                    symbolic.append(min(candidates,key=lambda r:digest([c['seed'],'SMOKE',r['request_id']])))
        source=Path(c['b0'])/'inputs/core/requests.jsonl'
        legacy=[r for r in rows(source) if r.get('cohort')=='B0_A' and r.get('wording')=='W0' and r.get('target')=='PRE' and r.get('context')=='I1' and r.get('repeat')==0 and r.get('condition') in ('FACT_NEUTRAL','FACT_CLAIM')]
        worlds=sorted({r['underlying_world_id'] for r in legacy},key=lambda w:digest([c['seed'],'M0_LEGACY_WORLD',w]))[:2]
        selected=[]
        for w in worlds:
            for condition in ('FACT_NEUTRAL','FACT_CLAIM'):
                pool=[r for r in legacy if r['underlying_world_id']==w and r['condition']==condition]
                old=min(pool,key=lambda r:digest([c['seed'],'M0_PAIR',r['request_id']]))
                r=dict(request_id='sws_legacy_'+old['request_id'],world_cluster_id=w,experiment='M0_SMOKE',split='history',
                    logical_bundle_id='legacy:'+w,source_request_id=old['request_id'],source_run=c['b0'],sample_family='LEGACY_B0_A',
                    payload=old['payload'],schema=old['schema'],condition=old['condition'],requested_tokens=512,models=c['models'],
                    review_status='OLD_RESEARCHER_REVIEWED_TASK_UNCHANGED_NOT_NEW_SWS_REVIEW',
                    source_request_sha256=digest(old),source_payload_sha256=digest(old['payload']))
                r['model_independent_request_hash']=digest(r); selected.append(r)
        requests=symbolic+selected
        assert len(requests)==12
        save(root/'public_inputs/smoke/requests.jsonl',requests,'jsonl')
        save(root/'manifest/smoke_request_lock.json',dict(status='REQUESTS_FROZEN_NOT_GENERATED',source=entry(root/'public_inputs/smoke/requests.jsonl'),
            requests_per_model=12,models=c['models'],symbolic=8,unchanged_B0_A=4,legacy_worlds=worlds,
            legacy_source=entry(source),selection_uses_model_outcomes=False,
            accuracy_is_not_smoke_gate=True,new_main_worlds=0,gpu_authorization='UNRESOLVED',
            code=[entry(CODE/x) for x in ('common.py','prepare_smoke.py','contracts.py','config.json')]))
        print('SMOKE_REQUESTS_FROZEN: 12 per model, no new main-world inference'); return
    sys.path.insert(0,str(Path(c['project'])/'research/state_binding_phase_a1/core_execution_v3'))
    from pipeline_v3 import Pipeline
    import torch
    if torch.cuda.is_available(): raise ValueError('CPU_PREFLIGHT_EXPECTED')
    runtime=dict(c,visual_hash_version='PURE_MEDIA_TENSORS_V3_SHARED_RUNTIME')
    pipeline=Pipeline(runtime,a.model); records=[]
    for r in rows(root/'public_inputs/smoke/requests.jsonl'):
        batch,pres,images=pipeline.process(r)
        rec=dict(request_id=r['request_id'],request_hash=r['model_independent_request_hash'],**{k:v for k,v in pres.items() if k!='request_id'},
                 input_token_ids=batch['input_ids'][0].tolist(),attention_mask=batch['attention_mask'][0].tolist(),
                 model_key=a.model,model_revision=pipeline.mc['revision'],raw_generation_status='NOT_RUN')
        records.append(rec)
    save(root/'review/smoke'/f'{a.model}_processor.jsonl',records,'jsonl')
    save(root/'reports'/f'smoke_processor_{a.model}.json',dict(status='PASS',job_id=os.environ['SLURM_JOB_ID'],requests=len(records),
        record_file=entry(root/'review/smoke'/f'{a.model}_processor.jsonl'),model=pipeline.mc,
        real_media_review_created=False,only_previously_reviewed_unchanged_B0_tasks=True,new_gpu_calls=0))
    print(json.dumps(dict(status='CPU_PROCESSOR_PASS',model=a.model,requests=len(records))),flush=True)

if __name__=='__main__': main()
