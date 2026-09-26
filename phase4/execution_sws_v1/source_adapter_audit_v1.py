"""Source-only adapter qualification; no predictions, no new gold, no proxy review."""
from collections import Counter, defaultdict
from common import *
from world_identity_v2 import repair_root

def main():
    a=arguments(__doc__).parse_args(); c,runroot=setup(a)
    if a.dry_run: print('Profile source-grounded fact/media schemas before compiling actual SWS review inputs'); return
    root=runroot/'preparation/source_adapters_v1'
    src=repair_root(runroot)/'inventory'
    acceptance=load(repair_root(runroot)/'REPAIR_ACCEPTANCE.json')
    if not acceptance['status'].startswith('PASS_'): raise ValueError('SOURCE_INVENTORY_NOT_ACCEPTED')
    paths=[src/'manifest/world_candidate_inventory.jsonl',src/'private_gold/source_fact_catalog.jsonl']
    inputs=[entry(p) for p in paths]
    expected={r['path']:r['sha256'] for r in acceptance['output_files']}
    for ref in inputs:
        if ref['sha256']!=expected[ref['path']]: raise ValueError('REPAIRED_INVENTORY_CHANGED')
    worlds={r['world_cluster_id']:r for r in rows(paths[0])}
    counts=Counter(); worldsets=defaultdict(set); examples={}; groups=defaultdict(Counter); warnings=Counter()
    for n,r in enumerate(rows(paths[1]),1):
        w=r['world_cluster_id']; f=r['fact']; prov=f['provenance']; ctx=f['context']; grounding=f.get('grounding') or {}
        key=(prov['source_dataset'],f['predicate'],ctx.get('scope'),ctx.get('state_id'))
        counts[key]+=1; worldsets[key].add(w)
        group=digest({k:ctx.get(k) for k in ('branch_id','reference_frame','scope','state_id','time_scope','media_id')})
        groups[w][group]+=1
        ek=(prov['source_dataset'],f['predicate'])
        rank=digest([c['seed'],'ADAPTER_SCHEMA_EXAMPLE',w,f['fact_id']])
        if ek not in examples or rank<examples[ek][0]: examples[ek]=(rank,r)
        if f['predicate']=='COUNT' and ctx.get('state_id')=='post_intervention': warnings['POST_COUNT_IS_NOT_PRE_COUNT']+=1
        if not grounding.get('source_media_locator'): warnings['NO_SOURCE_MEDIA_LOCATOR']+=1
    entries=[]
    for key,n in sorted(counts.items(),key=lambda x:str(x[0])):
        entries.append(dict(source_dataset=key[0],predicate=key[1],scope=key[2],state_id=key[3],facts=n,worlds=len(worldsets[key])))
    csvsave(root/'source_fact_schema_counts.csv',entries)
    representative=[]
    for _,r in sorted(examples.values(),key=lambda x:x[0]):
        p=Path(r['source_graph']['path'])
        if sha(p)!=r['source_graph']['sha256']: raise ValueError('GRAPH_CHANGED:'+str(p))
        graph=load(p)
        # Only permitted graph bodies, already selected without model outputs.
        representative.append(dict(**r,source_graph_keys=sorted(graph),source_graph_nonfacts={k:v for k,v in graph.items() if k not in ('facts','records')},
                                   source_membership=worlds[r['world_cluster_id']]['source_membership']))
    save(root/'representative_source_schemas.jsonl',representative,'jsonl')
    catalog=[]
    for w,r in sorted(worlds.items()):
        catalog.append(dict(world_cluster_id=w,sampling_rank=r['source_membership']['sampling_rank'],source_membership=r['source_membership'],
                            candidate_strata=r['candidate_strata'],same_context_fact_groups=dict(groups[w]),
                            max_same_context_fact_count=max(groups[w].values(),default=0),review_status='PENDING_ACTUAL_INPUT_COMPILATION',
                            source_counts=r['pre_counts'],source_counts_are_not_necessarily_PRE=True))
    save(root/'structural_candidates.jsonl',catalog,'jsonl')
    report=dict(status='SOURCE_SCHEMA_AUDITED_NOT_INPUT_VERIFIED',created_at=now(),job_id=os.environ['SLURM_JOB_ID'],
                run_id=c['run_id'],seed=c['seed'],config_snapshot=c,code_files=[entry(__file__),entry(CODE/'common.py')],
                inputs=inputs,source_fact_records=sum(counts.values()),candidate_worlds=len(worlds),representative_schema_records=len(representative),
                warnings=dict(warnings),model_prediction_files_read=0,model_calls=0,proxy_VERIFIED=0,
                outputs=[entry(root/x) for x in ('source_fact_schema_counts.csv','representative_source_schemas.jsonl','structural_candidates.jsonl')])
    save(root/'ADAPTER_AUDIT.json',report)
    print(json.dumps({k:report[k] for k in ('status','job_id','source_fact_records','candidate_worlds','representative_schema_records','warnings')}),flush=True)

if __name__=='__main__': main()
