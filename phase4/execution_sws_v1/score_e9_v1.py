"""Deterministic E9 field scoring; partial snapshots retain failures, nulls and every control."""
from collections import Counter,defaultdict
from common import *
from contracts import parse
from e0_snapshot import interval

def main():
    p=arguments(__doc__); p.add_argument('--model',required=True); a=p.parse_args(); c,root=setup(a)
    if a.model not in c['models']: raise ValueError('MODEL_OUTSIDE_STUDY')
    if a.dry_run: print('Deterministic E9 scoring of all frozen requests; no judge or inference'); return
    requests=list(rows(root/'public_inputs/E9/requests.jsonl')); gold={r['request_id']:r for r in rows(root/'private_gold/E9.jsonl')}
    records=[]; originals=[]; attempts=[]
    for r in requests:
        rid=r['request_id']; path=root/'raw'/a.model/'records'/(rid+'.json'); g=gold[rid]; field=r['schema']['kind']
        if field=='value': key='value'
        elif field=='verdict': key='verdict'
        else: raise ValueError('UNPLANNED_E9_INTERFACE')
        record=dict(request_id=rid,model_id=a.model,world_cluster_id=r['world_cluster_id'],experiment='E9',split='symbolic_control',source_type=r['sample_family'],
            spatial_symbolic=r['spatial_symbolic'],target_missing=r['target_missing'],presentation=r['presentation'],condition=r['condition'],interface=field,
            gold=g[key],predicted=None,value_present=False,correct=False,execution_status='NOT_RUN',schema_status='NOT_RUN',truncated=None)
        if path.exists():
            raw=load(path)
            if raw['request_hash']!=r['model_independent_request_hash']: raise ValueError('REQUEST_HASH_CHANGED_AT_SCORE')
            parsed=parse(raw['raw_response'],r['schema']); got=parsed['component_values']
            record.update(predicted=got.get(key),value_present=key in got,correct=key in got and type(got[key]) is type(g[key]) and got[key]==g[key],
                execution_status='RETURNED',schema_status=parsed['status'],truncated=raw['truncated'],raw_path=str(path),raw_sha256=sha(path),
                model_revision=raw['model_revision'],first_retained_response=raw['first_retained_response'],physical_attempt=raw['physical_attempt'])
            originals.append(record)
        else:
            for path in sorted((root/'raw'/a.model/'attempts').glob(rid+'.*.json')):
                attempts.append(entry(path)); record['execution_status']='INFRASTRUCTURE_ATTEMPT_NO_RETAINED_RESPONSE'
        records.append(record)
    groups=defaultdict(list)
    for r in originals:
        key=(str(r['spatial_symbolic']),str(r['target_missing']),r['presentation'],r['condition'],r['interface']); groups[key].append(r)
    stats=[]
    for key,rs in sorted(groups.items()):
        byworld=defaultdict(list)
        for r in rs: byworld[r['world_cluster_id']].append(int(r['correct']))
        vals=[(w,sum(v),len(v)) for w,v in byworld.items()]; num=sum(v[1] for v in vals); den=sum(v[2] for v in vals)
        lo,hi=interval(vals,c['seed'],5000)
        stats.append(dict(hypothesis_id='E9_DESCRIPTIVE_CONTROL',experiment='E9',model_id=a.model,source_type='SYNTHETIC_SYMBOLIC',split='symbolic_control',
            stratum='|'.join(key),metric='FIELD_ACCURACY',numerator=num,denominator=den,worlds=len(vals),estimate=num/den if den else None,
            ci95_low=lo,ci95_high=hi,p_adjustment='NOT_CONFIRMATORY',interpretation_limit='SYMBOLIC_AND_NONSPATIAL_CONTROLS_NOT_REAL_SPATIAL_WORLD_EVIDENCE'))
    output=root/'scores/E9'/a.model
    csvsave(output/'all_request_scores.csv',records); csvsave(output/'primary_statistics.csv',stats)
    byid={r['request_id']:r for r in records}; matched=[]
    for pair in rows(root/'matched/E9_structure.jsonl'):
        f=byid[pair['fact_request_id']]; v=byid[pair['verdict_request_id']]
        matched.append(dict(pair,model_id=a.model,fact_execution=f['execution_status'],verdict_execution=v['execution_status'],
            fact_correct=f['correct'] if f['execution_status']=='RETURNED' else None,
            verdict_correct=v['correct'] if v['execution_status']=='RETURNED' else None,
            fact_available_null=f['value_present'] and f['predicted'] is None,
            fact_report=f['predicted'],verdict_report=v['predicted'],same_run=False,
            interpretation='INDEPENDENT_CALLS_MATCHED_BY_FROZEN_WORLD_CONDITION_NOT_PROOF_OF_INTERNAL_KNOWLEDGE'))
    save(output/'matched.jsonl',matched,'jsonl')
    report=dict(status='COMPLETE' if len(originals)==len(requests) else 'PARTIAL',model=a.model,planned=len(requests),returned=len(originals),
        unrun=len(requests)-len(originals),worlds_planned=len({r['world_cluster_id'] for r in requests}),worlds_returned=len({r['world_cluster_id'] for r in originals}),
        correct=sum(r['correct'] for r in originals),accuracy_returned=sum(r['correct'] for r in originals)/len(originals) if originals else None,
        null=sum(r['value_present'] and r['predicted'] is None for r in originals),invalid=sum(r['schema_status']=='INVALID' for r in originals),
        infrastructure_attempts=attempts,request_lock=entry(root/'manifest/E9_request_lock.json'),raw_index=[{k:r[k] for k in ('request_id','raw_path','raw_sha256')} for r in originals],
        counts_are_actual_not_submitted=True,real_world_count=0,bootstrap_repetitions=5000,job_id=os.environ['SLURM_JOB_ID'])
    save(output/'acceptance.json',report); print(json.dumps({k:v for k,v in report.items() if k not in ('raw_index','infrastructure_attempts')},ensure_ascii=False),flush=True)

if __name__=='__main__': main()
