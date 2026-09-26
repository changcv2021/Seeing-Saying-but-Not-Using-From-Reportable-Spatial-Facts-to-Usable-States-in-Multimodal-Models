"""Read-only global source inventory. Never reads predictions for sample selection."""
from collections import Counter, defaultdict
from common import *
from world_identity_v2 import checked_overlay, repair_root

def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('CPU metadata/fact inventory; no media inference, no human signature, no sample lock'); return
    overlay, identity = checked_overlay(c, root)
    identity_root = repair_root(root)
    root = identity_root / 'inventory'
    p=Path(c['project']); pa=Path(c['phase_a']); baseline=Path(c['baseline']); inputs=[]
    prior=load(pa/'manifest/cluster_split.json'); inputs.append(entry(pa/'manifest/cluster_split.json'))
    historical_splits=defaultdict(set); datasets=defaultdict(set); media_keys=defaultdict(set)
    # Membership metadata only; do not open sealed/test graph bodies.
    for path in sorted((p/'splits').glob('*.jsonl')):
        inputs.append(entry(path))
        for r in rows(path):
            w=cluster(r['global_world_id']); historical_splits[w].add(r['split']); datasets[w].update(r.get('source_datasets',[]))
    # Count the current campaign's entire submitted universe as exposed, including pending rows.
    # Deliberately project only ID/world/split metadata; no claim, label, rationale or prediction is retained.
    exposed=set(); release_counts=Counter(); release_worlds=defaultdict(set)
    path=identity_root/'baseline_world_metadata.jsonl'; inputs.append(entry(path))
    for r in overlay.values():
        w=cluster(r['global_world_id']); exposed.add(w)
        # All submitted metadata, including UNKNOWN, informs split and exposure isolation.
        historical_splits[w].add(r['split']); datasets[w].add(r['dataset'])
        k=(r['level'],r['dataset'],r['split'],r.get('component',''))
        release_counts[k]+=1; release_worlds[k].add(w)
    for w,partition in prior['partition'].items():
        if partition in ('setup','discovery'): exposed.add(cluster(w))
    sealed={cluster(w) for w,s in prior['partition'].items() if s=='confirmation'}
    known_cross={cluster(w) for w in prior['excluded_known_cross_split_clusters']}
    # All index versions inform identity, not source-gold choice.
    indexes=sorted((p/'world_index').glob('*.jsonl'))
    for path in indexes:
        inputs.append(entry(path))
        for r in rows(path):
            w=cluster(r['global_world_id']); datasets[w].update(r.get('source_datasets',[]))
            for m in r.get('media',[]):
                if not isinstance(m,dict): continue
                rev=m.get('source_revision','')
                for key in ('sha256','archive_member','relative_path','media_id'):
                    if m.get(key): media_keys[w].add((key, '' if key=='sha256' else rev, m[key]))
    parent={w:w for w in historical_splits}
    def find(w):
        parent.setdefault(w,w)
        while parent[w]!=w: parent[w]=parent[parent[w]]; w=parent[w]
        return w
    def union(a,b):
        aa,bb=find(a),find(b)
        if aa!=bb: parent[max(aa,bb)]=min(aa,bb)
    key_owner={}; duplicate_edges=[]
    for w,keys in sorted(media_keys.items()):
        for key in sorted(keys):
            if key in key_owner and key_owner[key]!=w:
                union(w,key_owner[key]); duplicate_edges.append(dict(left=w,right=key_owner[key],evidence=key))
            else: key_owner[key]=w
    components=defaultdict(set)
    for w in list(parent): components[find(w)].add(w)
    eligibility={}; excluded=[]
    for component,ws in sorted(components.items()):
        ss=set().union(*(historical_splits[w] for w in ws)); reasons=[]
        if 'test' in ss: reasons.append('SOURCE_TEST_MEMBERSHIP')
        if ws&sealed: reasons.append('OLD_SEALED_CONFIRMATION')
        if len(ss)>1 or ws&known_cross: reasons.append('HISTORICAL_CROSS_SPLIT_CONFLICT')
        if not ss or not ss<= {'train','dev'}: reasons.append('NO_PERMITTED_SOURCE_PARTITION')
        record=dict(world_cluster_id=component,aliases=sorted(ws),source_splits=sorted(ss),previously_exposed=bool(ws&exposed),
                    candidate_status='BLOCKED' if reasons else 'SOURCE_MEMBERSHIP_ELIGIBLE_NOT_MEDIA_VERIFIED',reasons=reasons,
                    sampling_rank=digest([c['seed'],'GLOBAL_POOL',component]),
                    allowed_future_split='DISCOVERY_ONLY' if ws&exposed else 'UNASSIGNED_PENDING_COMPLETE_IDENTITY_AUDIT',
                    datasets=sorted(set().union(*(datasets[w] for w in ws))))
        for w in ws: eligibility[w]=record
        if reasons: excluded.append(record)
    save(root/'manifest/source_membership_audit.jsonl',[eligibility[min(ws)] for ws in components.values()],'jsonl')
    save(root/'manifest/exact_asset_cluster_edges.jsonl',duplicate_edges,'jsonl')
    # The manifests are lightweight metadata. Same graph path appears in multiple snapshots; read once.
    graphs={}
    for path in sorted((p/'world_graphs').glob('manifest.*.jsonl')):
        inputs.append(entry(path))
        for r in rows(path):
            w=cluster(r['global_world_id'])
            if r.get('validation_status')!='GRAPH_VALID' or eligibility.get(w,{}).get('candidate_status')!='SOURCE_MEMBERSHIP_ELIGIBLE_NOT_MEDIA_VERIFIED': continue
            graphs[r['graph_path']]=r
    facts_by_world=defaultdict(dict); rejects=[]; graph_refs=[]
    for i,(relative,r) in enumerate(sorted(graphs.items()),1):
        path=p/relative; ref=entry(path); graph_refs.append(ref)
        if ref['sha256']!=r['graph_sha256'].removeprefix('sha256:'): raise ValueError('SOURCE_GRAPH_HASH_CHANGED:'+relative)
        graph=load(path); w=find(cluster(r['global_world_id']))
        for f in graph.get('facts',[]):
            provenance=f.get('provenance',{}); ctx=f.get('context',{})
            if provenance.get('origin_type') not in ('NATIVE_DIRECT','QA_DIRECT','RULE_DERIVED','GEOMETRY_DERIVED'):
                rejects.append(dict(world=w,fact_id=f.get('fact_id'),reason='NON_GT_OR_UNDOCUMENTED_ORIGIN')); continue
            if f.get('observability') not in ('directly_observable','derived_from_observable'):
                rejects.append(dict(world=w,fact_id=f.get('fact_id'),reason='NOT_OBSERVABLE_SOURCE_FACT')); continue
            fid=f.get('canonical_fact_hash') or f.get('fact_id')
            if not fid: raise ValueError('FACT_ID_MISSING:'+relative)
            # Preserve complete native fact and provenance privately. No MLLM-derived gold.
            facts_by_world[w].setdefault(fid,dict(fact=f,source_graph=ref,source_global_world_id=r['global_world_id']))
        if i%500==0: print(json.dumps(dict(graphs_checked=i,total=len(graphs))),flush=True)
    facts=[]; catalog=[]; stratum_counts=Counter()
    for w,fs in sorted(facts_by_world.items()):
        ff=[v['fact'] for v in fs.values()]
        counts=[f for f in ff if f.get('predicate')=='COUNT' and type(f.get('value')) is int and f['value']>=0]
        relations=[f for f in ff if f.get('predicate') in ('LEFT_OF','RIGHT_OF','FRONT_OF','BEHIND','ABOVE','BELOW','INSIDE','CONTAINS','TOUCHING')]
        temporal=[f for f in ff if f.get('predicate') in ('BEFORE','AFTER')]
        frames={json.dumps(f.get('context',{}).get('reference_frame'),sort_keys=True) for f in ff if f.get('context',{}).get('reference_frame')}
        source_scopes=Counter(str(f.get('context',{}).get('scope')) for f in ff)
        strata=[]
        if counts: strata.append('COUNT')
        if relations: strata.append('NONCOUNT_RELATION')
        if len(frames)>1: strata.append('VIEW_FRAME_IDENTITY')
        if temporal: strata.append('TIME_BRANCH')
        for s in strata: stratum_counts[s]+=1
        catalog.append(dict(world_cluster_id=w,source_membership=eligibility[w],fact_count=len(ff),count_fact_count=len(counts),
            relation_fact_count=len(relations),temporal_fact_count=len(temporal),explicit_reference_frames=len(frames),
            candidate_strata=strata,scopes=dict(source_scopes),pre_counts=sorted({f['value'] for f in counts}),
            multiple_facts_available=len(ff)>=2,review_status='NOT_REVIEWED_FOR_SWS',
            warnings=['COUNTS_ARE_SOURCE_FACTS_NOT_ASSERTIONS_OF_PROCESSED_VISIBILITY','RELATION_DOMAINS_NOT_BINARY_WSA_MECHANISM_EVIDENCE','NEAR_DUPLICATE_AUDIT_PENDING','MULTIFACT_OR_MULTIFRAME_DOES_NOT_PROVE_MULTIVIEW_NECESSITY']))
        facts.extend(dict(world_cluster_id=w,**f) for f in fs.values())
    save(root/'private_gold/source_fact_catalog.jsonl',facts,'jsonl')
    save(root/'manifest/world_candidate_inventory.jsonl',catalog,'jsonl')
    csvsave(root/'tables/source_fact_rejects.csv',rejects)
    csvsave(root/'tables/E0_release_breadth.csv',[dict(level=k[0],dataset=k[1],source_split=k[2],component=k[3],claims=n,worlds=len(release_worlds[k])) for k,n in sorted(release_counts.items())])
    result=dict(status='INVENTORY_COMPLETE_NOT_A_QUALIFIED_FROZEN_PANEL',run_id=c['run_id'],job_id=os.environ['SLURM_JOB_ID'],
        created_at=now(),identity_acceptance=entry(identity_root/'identity_acceptance.json'),
        recovered_world_id_records=identity['recovered_records'],source_world_aliases=len(parent),metadata_asset_clusters=len(components),exact_asset_edges=len(duplicate_edges),
        permitted_membership_clusters=len(components)-len(excluded),source_graph_files_checked=len(graphs),
        source_fact_records=len(facts),candidate_worlds=len(catalog),candidate_stratum_world_counts=dict(stratum_counts),
        candidate_unexposed_worlds=sum(not r['source_membership']['previously_exposed'] for r in catalog),
        excluded_reason_counts=dict(Counter(x for r in excluded for x in r['reasons'])),
        real_worlds_verified_for_sws=0,final_sample_freeze='BLOCKED_IDENTITY_MEDIA_AND_DERIVED_QUERY_REVIEW',
        source_graphs_from_test_opened=0,source_graphs_from_old_confirmation_opened=0,model_prediction_files_read=0,
        release_label_or_claim_fields_used=0,original_data_writes=0,source_inventory_scope='ALL_EXISTING_SPLIT_INDEX_AND_VALID_GRAPH_MANIFESTS; UNADAPTED_RAW_SOURCES_NOT_EXHAUSTED')
    save(root/'manifest/source_inventory_inputs.json',inputs+graph_refs)
    save(root/'reports/source_inventory.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__': main()

