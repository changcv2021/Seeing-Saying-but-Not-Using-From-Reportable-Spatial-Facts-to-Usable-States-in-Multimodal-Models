"""E7 full-state retention, paired world estimates, no selection or retries."""
from collections import defaultdict
from common_auto_v2 import *
from contracts import parse
from e0_snapshot import interval
from e7_design_v1 import BATCH


def main():
    p=arguments(__doc__);p.add_argument('--model',required=True);a=p.parse_args();c,root=setup(a)
    if a.model not in c['models']:raise ValueError('UNAUTHORIZED_MODEL')
    out=root/'batches'/BATCH;dest=out/'scores'/a.model/('snapshot_'+os.environ['SLURM_JOB_ID'])
    gold={r['request_id']:r for r in rows(out/'private_gold/request_gold.jsonl')};records={};index=[]
    for sh in load(out/'manifest/shards.json'):
        for r in rows(sh['request_file']['path']):
            rid=r['request_id'];path=out/'raw'/a.model/f'shard_{sh["shard"]:03}'/'records'/(rid+'.json');g=gold[rid]
            item=dict(request_id=rid,world_cluster_id=r['world_cluster_id'],condition=r['condition'],family=r['sample_family'],
                execution_status='NOT_RUN',schema_status='NOT_RUN',expected=g['expected'],correct=None,protected_correct=None,
                raw_ref=None,parent_request_ids=r['parent_request_ids'])
            if path.exists():
                raw=load(path)
                if raw['request_hash']!=r['model_independent_request_hash']:raise ValueError('RAW_REQUEST_CHANGED')
                parsed=parse(raw['raw_response'],r['schema']);got=parsed['component_values'].get('facts',{});want=g['expected']['facts']
                correct=all(k in got and type(got[k]) is type(v) and got[k]==v for k,v in want.items())
                protected='qP' if 'qP' in want else 'q2'
                item.update(execution_status='RETURNED',schema_status=parsed['status'],correct=correct,
                    protected_correct=protected in got and got[protected]==want[protected],components=got,
                    raw_ref=entry(path),parent_ancestry=raw['parent_ancestry'],truncated=raw['truncated'])
                index.append(dict(request_id=rid,model=a.model,raw_ref=entry(path)))
            records[rid]=item
    groups=defaultdict(list)
    for r in records.values():groups[(r['family'],r['condition'])].append(r)
    stats=[]
    for (family,cond),rr in sorted(groups.items()):
        values=[(r['world_cluster_id'],int(r['correct']),1) for r in rr if r['execution_status']=='RETURNED']
        lo,hi=interval(values,c['seed'],5000)
        stats.append(dict(family=family,condition=cond,metric='JOINT_FACT_ACCURACY',planned=len(rr),returned=len(values),worlds=len(values),
            estimate=sum(r[1] for r in values)/len(values) if values else None,ci95_low=lo,ci95_high=hi))
    matched=[];effects=defaultdict(list)
    for m in rows(out/'private_gold/matched_structure.jsonl'):
        refs={cond:records[rid] for cond,rid in m['ids'].items()}
        event=dict(world_cluster_id=m['world_cluster_id'],family=m['sample_family'],responses=refs,contrasts={})
        for name,left,right in [('NEUTRAL_PARENT_MINUS_EXPOSED_PARENT','B_NEUTRAL_PARENT','B_EXPOSED_PARENT'),
                                ('OWN_FEEDBACK_MINUS_READONLY','C_OWN_FEEDBACK','C_READONLY_SEQUENCE'),
                                ('READONLY_MINUS_ONESHOT','C_READONLY_SEQUENCE','C_ONESHOT_RECOMPUTE')]:
            if left in refs and right in refs:
                ok=all(refs[x]['execution_status']=='RETURNED' for x in (left,right))
                delta=int(refs[left]['correct'])-int(refs[right]['correct']) if ok else None
                event['contrasts'][name]=dict(status='COMPLETE' if ok else 'PARTIAL',delta=delta)
                if ok:effects[(m['sample_family'],name)].append((m['world_cluster_id'],delta,1))
        if refs['A_NEUTRAL']['execution_status']=='RETURNED':event['neutral_stage1_correct']=refs['A_NEUTRAL']['correct']
        matched.append(event)
    for (family,name),values in effects.items():
        lo,hi=interval(values,c['seed'],5000)
        stats.append(dict(family=family,condition=name,metric='PAIRED_JOINT_ACCURACY_DIFFERENCE',worlds=len(values),
            estimate=sum(v[1] for v in values)/len(values),ci95_low=lo,ci95_high=hi))
    csvsave(dest/'per_request_diagnostics.csv',records.values());csvsave(dest/'grouped_statistics.csv',stats)
    save(dest/'matched_results.jsonl',matched,'jsonl');save(dest/'raw_response_index.jsonl',index,'jsonl')
    report=dict(status='COMPLETE' if len(index)==len(records) else 'PARTIAL',model=a.model,planned=len(records),returned=len(index),
        worlds=20,split='discovery',scientific_grade='AUTO_ONLY_PROVISIONAL',confirmation=False,
        source_level='L1_PLUS_CONTROLLED_BRANCH_NOT_NATIVE_L4',all_null_invalid_and_not_run_retained=True,
        measured='EXTERNALIZED_STATE_AND_LOGICAL_PREFIX_BEHAVIOR_NOT_PROOF_OF_INTERNAL_STATE',
        job_id=os.environ['SLURM_JOB_ID'],raw_index=entry(dest/'raw_response_index.jsonl'))
    save(dest/'SCORE_ACCEPTANCE.json',report);print(json.dumps(report),flush=True)


if __name__=='__main__':main()
