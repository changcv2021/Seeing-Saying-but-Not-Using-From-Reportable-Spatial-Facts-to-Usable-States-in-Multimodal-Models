"""Independent gold-blind normalization; keep logical reuse and all not-run states."""
from collections import defaultdict,Counter
from ssm_common import *
from interface_repair_v3.adapter import normalize
def main():
    p=cli(__doc__);p.add_argument('--batch',choices=['B1','B2'],required=True);p.add_argument('--model',required=True);p.add_argument('--stage',choices=['normalize','score'],required=True)
    a=p.parse_args();c,root=context(a);src=root/'batches'/a.batch;dest=src/'scores'/a.model/('snapshot_'+os.environ['SLURM_JOB_ID'])
    if a.dry_run:print('Normalize without gold, then deterministic typed scoring.');return
    lock=load(src/'manifest/REQUEST_LOCK.json')
    for ref in lock['code']+lock['public_inputs']:check(ref)
    requests={r['request_id']:r for r in rows(src/'public_inputs/requests.jsonl')};new_ids=set(requests);logical=list(rows(src/'public_inputs/logical_manifest.jsonl'))
    legacy=next((Path(r['legacy_source']) for r in logical if r['execution_source']=='EXACT_LEGACY_REUSE'),None)
    if a.stage=='normalize':
        sys.path.insert(0,str(Path(c['project'])/'research/state_binding_phase_a1/core_execution_v3'))
        from pipeline_v3 import install_gold_guard
        guard=install_gold_guard();result=[];locations={}
        for sh in load(src/'manifest/shards.json'):
            for r in rows(sh['request_file']['path']):locations[r['request_id']]=src/'raw'/a.model/f'shard_{sh["shard"]:03}/records'/(r['request_id']+'.json')
        if legacy:
            old={r['request_id']:r for r in rows(legacy/'public_inputs/requests.jsonl')}
            for r in logical:
                if r['execution_source']!='EXACT_LEGACY_REUSE':continue
                rid=r['request_id'];req=old[rid]
                assert req['payload']==r['legacy_payload'] and req['schema']==r['legacy_schema']
                requests[rid]=req;paths=list((legacy/'raw'/a.model).glob('shard_*/records/'+rid+'.json'))
                if len(paths)>1:raise ValueError('AMBIGUOUS_LEGACY_REUSE')
                locations[rid]=paths[0] if paths else None
        for rid,r in requests.items():
            path=locations.get(rid);rec=dict(request_id=rid,world_cluster_id=r['world_cluster_id'],status='NOT_RUN')
            if path and path.is_file():
                raw=load(path);assert raw['request_hash']==r['model_independent_request_hash']
                rec.update(status='RETURNED',normalization=normalize(raw['raw_response'],r['schema']),raw_response=raw['raw_response'],raw=entry(path),
                    output_tokens=raw['output_tokens'],truncated=raw['truncated'],generation_seconds=raw.get('generation_seconds'),
                    is_reused=rid not in new_ids)
            result.append(rec)
        save(dest/'canonical_views.jsonl',result,'jsonl');save(dest/'NORMALIZE_ACCEPTANCE.json',dict(rows=len(result),guard=guard));return
    gold={r['request_id']:r for r in rows(src/'private_gold/request_gold.jsonl')}
    if legacy:gold.update({r['request_id']:r for r in rows(legacy/'private_gold/request_gold.jsonl')})
    views={r['request_id']:r for r in rows(dest/'canonical_views.jsonl')};rr=[]
    for l in logical:
        rid=l['request_id'];rec=views.get(rid,{});state=rec.get('status','NOT_APPLICABLE' if l['execution_source']=='NOT_APPLICABLE' else 'NOT_RUN')
        parsed=rec.get('normalization',{}).get('normalized',{});expected=gold[rid]['expected'] if rid else None
        correct=parsed.get('status')=='VALID' and digest(parsed.get('component_values'))==digest(expected) if state=='RETURNED' else None
        rr.append(dict(**{k:v for k,v in l.items() if k not in ('legacy_payload','legacy_schema')},model=a.model,execution_status=state,content_correct=correct,expected=expected,
            prediction=parsed.get('component_values'),strict_status=rec.get('normalization',{}).get('strict',{}).get('status'),normalized_status=parsed.get('status'),
            raw_response=rec.get('raw_response'),raw=rec.get('raw'),output_tokens=rec.get('output_tokens'),truncated=rec.get('truncated')))
    csvsave(dest/'logical_scores.csv',rr)
    summaries=[];groups=defaultdict(list)
    for r in rr:groups[(r['condition'],r['split'])].append(r)
    for (cond,sp),rs in sorted(groups.items()):
        applicable=[r for r in rs if r['execution_status']!='NOT_APPLICABLE'];returned=[r for r in applicable if r['execution_status']=='RETURNED']
        summaries.append(dict(model=a.model,batch=a.batch,condition=cond,split=sp,planned=len(rs),applicable=len(applicable),returned=len(returned),
            worlds=len({r['world_cluster_id'] for r in applicable}),correct=sum(r['content_correct'] is True for r in returned),
            accuracy_all_applicable=sum(r['content_correct'] is True for r in returned)/len(applicable) if applicable else None,
            not_run=len(applicable)-len(returned),not_applicable=len(rs)-len(applicable),null=sum(r['prediction']=={'value':None} for r in returned),
            invalid=sum(r['normalized_status']!='VALID' for r in returned)))
    csvsave(dest/'condition_summary.csv',summaries)
    total=Counter(r['execution_status'] for r in rr)
    save(dest/'SCORE_ACCEPTANCE.json',dict(status='COMPLETE_WITH_EXPLICIT_NA' if not total['NOT_RUN'] else 'PARTIAL_NOT_RUN_RETAINED',
        model=a.model,batch=a.batch,logical_rows=len(rr),counts=dict(total),normalization=entry(dest/'canonical_views.jsonl'),scores=entry(dest/'logical_scores.csv'),
        no_internal_intervention=True,not_a_final_mechanism_report=True,raw_gold_unchanged=True))
    print(json.dumps(dict(model=a.model,batch=a.batch,counts=total)),flush=True)
if __name__=='__main__':main()
