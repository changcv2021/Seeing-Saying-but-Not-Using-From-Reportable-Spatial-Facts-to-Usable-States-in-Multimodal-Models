"""Afterany partial-safe deterministic scoring; no model-based judge or input repair."""
from collections import defaultdict, Counter
from common_auto_v2 import *
from contracts import parse
from e0_snapshot import interval
from real_design_v1 import BATCH


def equal(a,b): return type(a) is type(b) and a==b


def main():
    p=arguments(__doc__); p.add_argument('--model',required=True); a=p.parse_args(); c,root=setup(a)
    if a.model not in c['models']: raise ValueError('UNAUTHORIZED_MODEL')
    if a.dry_run: print('Score all first responses and retain NOT_RUN; no judge'); return
    out=root/'batches'/BATCH; job=os.environ['SLURM_JOB_ID']; dest=out/'scores'/a.model/('snapshot_'+job)
    reqs={r['request_id']:r for r in rows(out/'public_inputs/requests.jsonl')}
    gold={g['request_id']:g for g in rows(out/'private_gold/request_gold.jsonl')}
    byid={}; indexes=[]
    for sh in load(out/'manifest/shards.json'):
        for r in rows(sh['request_file']['path']):
            rid=r['request_id']; path=out/'raw'/a.model/f'shard_{sh["shard"]:03}'/'records'/(rid+'.json')
            record=dict(request_id=rid,world_cluster_id=r['world_cluster_id'],model_id=a.model,split='discovery',
                        sample_family=r['sample_family'],execution_status='NOT_RUN',schema_status='NOT_RUN',component_values={},
                        expected=gold[rid]['expected'],content_correct=None,strict_correct=None)
            if path.exists():
                raw=load(path)
                if raw['request_hash']!=r['model_independent_request_hash']: raise ValueError('RAW_REQUEST_HASH_MISMATCH')
                parsed=parse(raw['raw_response'],r['schema']); got=parsed['component_values']; expected=gold[rid]['expected']
                correct=all(k in got and equal(got[k],v) for k,v in expected.items())
                record.update(execution_status='RETURNED',schema_status=parsed['status'],component_values=got,
                    content_correct=correct,strict_correct=correct and parsed['status']=='VALID',
                    order_compliant=parsed.get('order_compliant',False),truncated=raw['truncated'],raw_path=str(path),raw_sha256=sha(path),
                    generation_seconds=raw['generation_seconds'],model_revision=raw['model_revision'])
                indexes.append({k:record[k] for k in ('request_id','model_id','raw_path','raw_sha256','model_revision')})
            else:
                attempts=list((path.parent.parent/'attempts').glob(rid+'.*.json'))
                record['infrastructure_attempts']=[entry(p) for p in attempts]
                if attempts: record['execution_status']='INFRASTRUCTURE_FAILURE_NO_RETAINED_RESPONSE'
            byid[rid]=record
    logical=[]
    for alias in rows(out/'private_gold/logical_aliases.jsonl'):
        scored=byid[alias['request_id']]
        logical.append(dict(scored,experiment=alias['experiment'],condition=alias['condition'],wording=alias['wording'],view_variant=alias['view_variant']))
    csvsave(dest/'all_physical_request_scores.csv',byid.values()); csvsave(dest/'all_logical_request_scores.csv',logical)
    stats=[]; groups=defaultdict(list)
    for r in logical: groups[(r['experiment'],r['sample_family'],r['condition'],r['wording'])].append(r)
    for key,rs in sorted(groups.items()):
        rr=[r for r in rs if r['execution_status']=='RETURNED']; worlds=defaultdict(list)
        for r in rr: worlds[r['world_cluster_id']].append(int(r['content_correct']))
        vals=[(w,sum(v),len(v)) for w,v in worlds.items()]; lo,hi=interval(vals,c['seed'],5000)
        stats.append(dict(model_id=a.model,experiment=key[0],sample_family=key[1],condition=key[2],wording=key[3],metric='CONTENT_ACCURACY',
            planned=len(rs),returned=len(rr),numerator=sum(r['content_correct'] for r in rr),denominator=len(rr),worlds=len(worlds),
            estimate=sum(r['content_correct'] for r in rr)/len(rr) if rr else None,ci95_low=lo,ci95_high=hi,
            split='discovery',review_grade='AUTO_ONLY_PROVISIONAL',confirmation_p_value='NOT_CONFIRMATORY'))
    matched=[]; effect_groups=defaultdict(list)
    for m in rows(out/'private_gold/matched_structure.jsonl'):
        event=dict(m,model_id=a.model,status='PARTIAL')
        refs={k:byid[v] for k,v in m.items() if isinstance(v,str) and v in byid}
        event['responses']={k:{q:r.get(q) for q in ('request_id','execution_status','component_values','schema_status','raw_path','raw_sha256')} for k,r in refs.items()}
        if refs and all(r['execution_status']=='RETURNED' for r in refs.values()):
            event['status']='COMPLETE'
            if m['experiment'] in ('E2','E2_PROTECTION'):
                values={k:r['component_values'].get('value') for k,r in refs.items()}
                present={k:'value' in r['component_values'] for k,r in refs.items()}
                neutral_correct=present['neutral'] and equal(values['neutral'],m['target_gold'])
                fc=present['false'] and equal(values['false'],m['target_gold']); sc=present['sham'] and equal(values['sham'],m['target_gold'])
                excess=int(neutral_correct and not fc)-int(neutral_correct and not sc)
                event.update(neutral_correct=neutral_correct,false_correct=fc,sham_correct=sc,correct_to_wrong_excess=excess,
                    false_to_candidate=neutral_correct and present['false'] and equal(values['false'],m['candidate_value']) and not equal(m['target_gold'],m['candidate_value']),
                    sham_to_candidate=neutral_correct and present['sham'] and equal(values['sham'],m['candidate_value']) and not equal(m['target_gold'],m['candidate_value']),
                    null_or_invalid={k:not present[k] or v is None for k,v in values.items()},
                    interpretation='PAIRED_BEHAVIOR_NOT_INTERNAL_STATE_PROOF')
                family=refs['neutral']['sample_family']; effect_groups[(m['experiment'],family,m['wording'])].append((m['world_cluster_id'],excess))
            elif m['experiment']=='E6':
                details={}
                for label in ('FACT_FIRST','VERDICT_FIRST'):
                    r=refs[label]; vals=r['component_values']; value=vals.get('value'); verdict=vals.get('verdict')
                    fact_correct='value' in vals and equal(value,m['target_gold'])
                    target_label='SUPPORTED' if equal(m['target_gold'],m['candidate_value']) else 'CONTRADICTORY'
                    self_label=None if value is None else 'SUPPORTED' if equal(value,m['candidate_value']) else 'CONTRADICTORY'
                    details[label]=dict(fact_correct=fact_correct,verdict_correct=verdict==target_label,
                        fact_correct_verdict_wrong=fact_correct and verdict!=target_label,
                        self_inconsistent=None if self_label is None or verdict is None else verdict!=self_label,
                        actual_order_compliant=r['order_compliant'])
                event['joint_diagnostics']=details
            elif m['experiment']=='E4':
                event['all_targets_correct']=all('value' in refs[s]['component_values'] and equal(refs[s]['component_values']['value'],v) for s,v in m['expected'].items())
        matched.append(event)
    for key,rs in sorted(effect_groups.items()):
        ww=defaultdict(list)
        for w,v in rs: ww[w].append(v)
        # Equal weight per world; within-world offsets stay together.
        vals=[(w,sum(v)/len(v),1) for w,v in ww.items()]; lo,hi=interval(vals,c['seed'],5000)
        stats.append(dict(model_id=a.model,experiment=key[0],sample_family=key[1],wording=key[2],condition='FALSE_MINUS_SAME_VALUE_SHAM',
            metric='WORLD_MACRO_CORRECT_TO_WRONG_EXCESS',estimate=sum(x[1] for x in vals)/len(vals),ci95_low=lo,ci95_high=hi,
            worlds=len(vals),matched_blocks=len(rs),split='discovery',review_grade='AUTO_ONLY_PROVISIONAL',confirmation_p_value='NOT_CONFIRMATORY'))
    csvsave(dest/'primary_statistics.csv',stats); save(dest/'matched_results.jsonl',matched,'jsonl'); save(dest/'raw_response_index.jsonl',indexes,'jsonl')
    returned=sum(r['execution_status']=='RETURNED' for r in byid.values())
    report=dict(status='COMPLETE' if returned==len(reqs) else 'PARTIAL',batch=BATCH,model_id=a.model,job_id=job,
        planned=len(reqs),returned=returned,not_returned=len(reqs)-returned,worlds_planned=len({r['world_cluster_id'] for r in reqs.values()}),
        invalid=sum(r['schema_status']=='INVALID' for r in byid.values()),
        human_review_required=False,scientific_review_grade='AUTO_ONLY_PROVISIONAL',
        full_study_complete=False,raw_index=entry(dest/'raw_response_index.jsonl'),
        primary_statistics=entry(dest/'primary_statistics.csv'),matched=entry(dest/'matched_results.jsonl'))
    save(dest/'SCORE_ACCEPTANCE.json',report); print(json.dumps(report),flush=True)


if __name__=='__main__': main()
