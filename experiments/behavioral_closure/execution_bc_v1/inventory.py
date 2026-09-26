"""Trace modality/state evidence back to construction records, not model accuracy."""
from collections import defaultdict,Counter
from bc_common import *
from data_continuation_v1.prepare import source_guard

def main():
    p=cli(__doc__);p.add_argument('--stage',choices=['P5','P6','P7'],required=True);a=p.parse_args();c,sws,out=context(a)
    if a.dry_run:print('Source provenance inventory '+a.stage);return
    guard=source_guard();dest=out/a.stage
    cat=sws/'repairs/world_identity_v2/inventory/private_gold/source_fact_catalog.jsonl'
    groups=defaultdict(lambda:dict(facts=0,sources=set(),states=set(),branches=set(),views=set(),times=set(),
        direct_observations={},derivation_examples=[],frame_roles=set()))
    for line,row in enumerate(rows(cat),1):
        w=row['world_cluster_id'];f=row['fact'];ctx=f.get('context',{});g=f.get('grounding',{});v=groups[w];v['facts']+=1
        v['sources'].add(f['provenance']['source_dataset'])
        for key,dst in [('state_id','states'),('branch_id','branches'),('reference_frame','views'),('time_scope','times')]:
            if ctx.get(key) is not None:v[dst].add(json.dumps(ctx[key],sort_keys=True))
        v['frame_roles'].update(g.get('frame_roles',{}))
        ref=dict(catalog_line=line,fact_id=f['fact_id'],source_graph=row['source_graph'],context=ctx,
                 grounding=g,provenance=f['provenance'],derivation=f.get('derivation'))
        if f['provenance']['origin_type'] in ('QA_DIRECT','NATIVE_DIRECT') and ctx.get('state_id') in ('observed','actual'):
            key=(ctx.get('media_id'),json.dumps(ctx.get('time_scope'),sort_keys=True))
            v['direct_observations'].setdefault(key,ref)
        if f.get('derivation') is not None and len(v['derivation_examples'])<2:v['derivation_examples'].append(ref)
    matrix=[]
    for w,v in sorted(groups.items()):
        common=dict(world_cluster_id=w,sources=sorted(v['sources']),facts=v['facts'],states=sorted(v['states']),
            branches=sorted(v['branches']),views=sorted(v['views']),time_scopes=sorted(v['times']),
            provenance_catalog=str(cat),direct_observation_contexts=len(v['direct_observations']))
        if a.stage=='P5':
            candidate=len(v['views'])>1 or len(v['frame_roles'])>1
            if not candidate:continue
            matrix.append(dict(common,status='MULTIVIEW_SOURCE_CANDIDATE_NOT_NECESSITY_CERTIFIED',
                single_view_counterworld_certificate=False,joint_sufficiency_certificate=False,
                reason='MULTIPLE_REFERENCES_DO_NOT_PROVE_EVERY_SINGLE_VIEW_INSUFFICIENT',
                construction_derivation_examples=v['derivation_examples']))
        elif a.stage=='P6':
            matrix.append(dict(common,status='SOURCE_STATE_INVENTORY_NOT_NEW_INPUT_QUALIFICATION',
                time_candidate=len(v['times'])>1,frame_candidate=len(v['views'])>1,branch_candidate=len(v['branches'])>1,
                native_pre_post_available=any('pre' in x.lower() for x in v['states']) and any('post' in x.lower() for x in v['states']),
                controlled_count_is_not_native_time=True,source_examples=list(v['direct_observations'].values())[:2]))
        else:
            if not v['direct_observations']:continue
            matrix.append(dict(common,status='REAL_OBSERVATION_CANDIDATE_NOT_MATCHED_ROLE_TEST',
                source_supported_multiple_observations=len(v['direct_observations'])>1,
                source_examples=list(v['direct_observations'].values())[:2],
                remaining='MATCH_ENTITY_SCOPE_AND_ACTUAL_NEW_MEDIA_THEN_FREEZE_ROLE_CONTRAST; TEXT_ASSERTION_NOT_OBSERVATION'))
    csvsave(dest/'source_inventory.csv',matrix)
    # Reuse explicit construction certificates as evidence, without upgrading their scope.
    refs=[entry(cat),entry(__file__)];certs=[]
    if a.stage=='P5':
        for path in sorted((sws/'batches/multiview_breadth_v2_20260910/private_gold/ablation_certificates').glob('*.json')):
            x=load(path);refs.append(entry(path));certs.append(dict(world_cluster_id=x['world_cluster_id'],certificate=entry(path),
                genuine_multiview_necessity=x.get('genuine_multiview_necessity',False),
                pixel_consistent_counterworlds_verified=x.get('pixel_consistent_counterworlds_verified',False),scope=x.get('scope')))
        csvsave(dest/'existing_multiview_certificates.csv',certs)
    acc=dict(status='SOURCE_INVENTORY_COMPLETE_QUALIFICATION_GAPS_RETAINED',stage=a.stage,job_id=os.environ['SLURM_JOB_ID'],
        rows=len(matrix),catalog_worlds=len(groups),sources=refs,source_guard=guard,
        selected_by_model_error=False,model_calls=0,
        certified_multiview_required_worlds=sum(r['genuine_multiview_necessity'] and r['pixel_consistent_counterworlds_verified'] for r in certs) if a.stage=='P5' else None,
        next='SOURCE_CANDIDATES_REQUIRE_TYPED_EVIDENCE_REPLAY; NO_UNQUALIFIED_GPU_INFERENCE')
    save(dest/'ACCEPTANCE.json',acc);print(json.dumps({k:v for k,v in acc.items() if k!='sources'}),flush=True)

if __name__=='__main__':main()
