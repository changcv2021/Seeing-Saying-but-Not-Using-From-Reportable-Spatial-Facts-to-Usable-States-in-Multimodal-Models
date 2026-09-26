"""Read-only D01 interface audit or source-only branch eligibility preparation."""
from collections import Counter, defaultdict
from common_auto_v2 import *
from contracts import parse
from real_design_v1 import BATCH, qualified_fact, independent_facts


def interface(c, root, model):
    base=root/'batches'/BATCH
    dest=root/'diagnostics/interface_d01_v1'/model/('snapshot_'+os.environ['SLURM_JOB_ID'])
    reqs=list(rows(base/'public_inputs/requests.jsonl')); records=[]
    for sh in load(base/'manifest/shards.json'):
        for r in rows(sh['request_file']['path']):
            path=base/'raw'/model/f'shard_{sh["shard"]:03}'/'records'/(r['request_id']+'.json')
            row=dict(request_id=r['request_id'],world_cluster_id=r['world_cluster_id'],model=model,
                     experiment=r['experiment'],condition=r['condition'],family=r['sample_family'],schema=r['schema'],status='NOT_RUN')
            if path.exists():
                raw=load(path); p=parse(raw['raw_response'],r['schema'])
                if raw['request_hash']!=r['model_independent_request_hash']: raise ValueError('RAW_REQUEST_CHANGED')
                text=raw['raw_response'].strip()
                category='VALID'
                if p['status']!='VALID':
                    category=p['reason']
                    if text.startswith('```'): category='MARKDOWN_FENCE'
                    elif text.isdigit(): category='BARE_INTEGER'
                    elif text in ('YES','NO','SUPPORTED','CONTRADICTORY','UNKNOWN','null'): category='BARE_DOMAIN_LITERAL'
                    elif p['parsed'] is not None: category='OBJECT_SCHEMA_OR_DOMAIN'
                row.update(status='RETURNED',schema_status=p['status'],interface_category=category,
                    retained_components=p['component_values'],actual_key_order=p['actual_key_order'],
                    order_compliant=p.get('order_compliant',False),truncated=raw['truncated'],output_tokens=raw['output_tokens'],
                    raw_ref=entry(path),raw_response=text)
            records.append(row)
    csvsave(dest/'per_request_interface_audit.csv',records)
    groups=Counter((r['family'],r['schema']['kind'],r.get('interface_category','NOT_RUN')) for r in records)
    csvsave(dest/'interface_groups.csv',[dict(family=k[0],kind=k[1],category=k[2],requests=v) for k,v in sorted(groups.items())])
    report=dict(status='COMPLETE' if all(r['status']=='RETURNED' for r in records) else 'PARTIAL',model=model,
        planned=len(reqs),returned=sum(r['status']=='RETURNED' for r in records),worlds=len({r['world_cluster_id'] for r in records}),
        parser=entry(CODE/'contracts.py'),gold_read=False,old_scores_modified=False,semantic_retries=0,
        diagnostic_only_not_alternative_score=True,job_id=os.environ['SLURM_JOB_ID'],
        detail=entry(dest/'per_request_interface_audit.csv'),groups=entry(dest/'interface_groups.csv'))
    save(dest/'AUDIT_ACCEPTANCE.json',report); print(json.dumps(report),flush=True)


def eligibility(c, root):
    dest=root/'preparation/branch_eligibility_v1'
    inv=root/'repairs/world_identity_v2/inventory'
    worldfile=inv/'manifest/world_candidate_inventory.jsonl'
    factfile=inv/'private_gold/source_fact_catalog.jsonl'
    existing={r['world_cluster_id'] for r in rows(root/'batches'/BATCH/'private_gold/world_panel.jsonl')}
    worlds={r['world_cluster_id']:r for r in rows(worldfile)}
    safe={w:r for w,r in worlds.items() if not r['source_membership']['reasons']
          and not any('test' in str(x).lower() for x in r['source_membership']['source_splits'])}
    counts=Counter(); candidates=defaultdict(list); pairs=defaultdict(dict); schemas={}; n=0
    for row in rows(factfile):
        w=row['world_cluster_id']
        if w not in safe: continue
        f=row['fact']; ctx=f['context']; prov=f['provenance']
        key=(prov['source_dataset'],f['predicate'],ctx.get('state_id'),ctx.get('scope'),bool(f.get('derivation')))
        counts[key]+=1; n+=1
        if key not in schemas: schemas[key]=row
        if qualified_fact(f) and prov['source_dataset']=='CA-VQA':
            roles=f.get('grounding',{}).get('frame_roles',{})
            if len(roles)==5:
                pairs[(w,digest(roles))][f['fact_id']]=f
        if len(candidates[w])<12:
            candidates[w].append(dict(fact_id=f['fact_id'],predicate=f['predicate'],context=ctx,
                provenance=prov,source_graph=row['source_graph'],derivation=f.get('derivation'),grounding=f.get('grounding')))
    paired=defaultdict(set)
    for (w,frame), fs in pairs.items():
        ff=list(fs.values())
        for i,a in enumerate(ff):
            for b in ff[i+1:]:
                if independent_facts(a,b): paired[w].add('COUNT' if a['predicate']=='COUNT' else 'NONCOUNT_RELATION'); break
    out=[]
    for w,r in sorted(safe.items(),key=lambda item:digest([c['seed'],'BRANCH_ELIGIBILITY_V1',item[0]])):
        m=r['source_membership']; exposed=m['previously_exposed']
        reasons=[]
        if not exposed: reasons.append('GLOBAL_ASSET_NEAR_DUPLICATE_RECONCILIATION_AND_SPLIT_LEDGER_REQUIRED')
        if w in existing: reasons.append('ALREADY_IN_D01_NO_DUPLICATE_E1_E6_GENERATIONS')
        if not paired[w]: reasons.append('NO_SAME_FRAME_INDEPENDENT_FACT_PAIR_IN_CURRENT_CA_ADAPTER')
        out.append(dict(world_cluster_id=w,source_membership=m,already_d01=w in existing,
            source_qualified_pair_families=sorted(paired[w]),candidate_strata=r.get('candidate_strata'),
            next_stage='COMPILE_AND_CHECK_MEDIA' if exposed and paired[w] and w not in existing else 'SOURCE_ENGINEERING_REQUIRED',
            execution_blockers=reasons,human_review_blocks=False))
    save(dest/'world_eligibility.jsonl',out,'jsonl')
    save(dest/'source_schema_examples.jsonl',schemas.values(),'jsonl')
    save(dest/'source_only_e8_anchors.jsonl',[dict(world_cluster_id=w,facts=fs) for w,fs in candidates.items()],'jsonl')
    csvsave(dest/'source_schema_counts.csv',[dict(dataset=k[0],predicate=k[1],state=k[2],scope=k[3],derived=k[4],facts=v) for k,v in counts.items()])
    report=dict(status='SOURCE_PREPARATION_COMPLETE_NOT_MODEL_EXECUTION',job_id=os.environ['SLURM_JOB_ID'],
        source_inputs=[entry(worldfile),entry(factfile)],safe_membership_worlds=len(safe),facts_scanned=n,
        additional_exposed_ca_pair_worlds=sum(r['next_stage']=='COMPILE_AND_CHECK_MEDIA' for r in out),
        holdout_needs_global_asset_audit=sum(not r['source_membership']['previously_exposed'] for r in out),
        predictions_read=False,test_semantics_compiled=False,human_review_gate=False,
        E8_status='NATIVE_LEVEL_PREMISE_AND_ORACLE_REQUEST_COMPILER_REQUIRED_NOT_RELABELLED_D01',
        C1_status='NO_FROZEN_QUALIFIED_NEW_HOLDOUT_YET',C2_status='REQUIRES_MECHANISM_LOCK',
        outputs=[entry(dest/x) for x in ('world_eligibility.jsonl','source_schema_examples.jsonl','source_only_e8_anchors.jsonl','source_schema_counts.csv')])
    save(dest/'PREPARATION_ACCEPTANCE.json',report); print(json.dumps(report),flush=True)


def main():
    p=arguments(__doc__); p.add_argument('--stage',choices=['interface','eligibility'],required=True); p.add_argument('--model')
    a=p.parse_args(); c,root=setup(a)
    if a.stage=='interface':
        if a.model not in c['models']: raise ValueError('MODEL_NOT_ALLOWED')
        interface(c,root,a.model)
    else: eligibility(c,root)


if __name__=='__main__': main()
