"""A1: source-based mining; never reads model responses or model correctness."""
import collections
import re
from base import *
from spaceconflict.l4_three_part.engine_a import execute_transition_a
from spaceconflict.l4_three_part.checker_b import check_transition_b
from spaceconflict.hypo3d_l4.verification import verify_count_pair_accessibly

OPPOSITE={'LEFT_OF':'RIGHT_OF','RIGHT_OF':'LEFT_OF','FRONT_OF':'BEHIND','BEHIND':'FRONT_OF','ABOVE':'BELOW','BELOW':'ABOVE'}
AXIS={'LEFT_OF':'horizontal left/right','RIGHT_OF':'horizontal left/right','FRONT_OF':'front/behind','BEHIND':'front/behind','ABOVE':'vertical above/below','BELOW':'vertical above/below'}

def aliases(seed,pid):
    return ['STATE_X','STATE_Y'] if int(stable_rank(seed,pid)[0],16)%2 else ['STATE_Y','STATE_X']

def context_for(r):
    text=r.get('media_context','')
    if r['level']=='L4': text+='\nAll supplied images show the initial scene. The intervention is hypothetical: '+r.get('intervention_text','')
    return text.strip()

def group_from_l4(pair, requests, prestates, cfg):
    graph=pair['supported_claim']['graph']; pred=graph['predicate']; pid=pair['pair_id']
    action=pair.get('intervention',{}); family=action.get('family') or pair.get('transition_family')
    pre=pair.get('pre_state_reference',{}).get('facts') or []
    post=pair.get('post_state_reference',{}).get('facts') or []
    replay={}; refs=[]
    if pair['l4_origin']=='BENCHMARK_CONTROLLED':
        aa=execute_transition_a(pre,action); bb=check_transition_b(pre,action)
        if aa['status']!='PASS' or bb['status']!='PASS' or aa['post_facts']!=bb['post_facts']: return None,'INDEPENDENT_TRANSITION_DISAGREEMENT'
        post=aa['post_facts']; replay=dict(engine_a=aa,checker_b=bb)
    else:
        if pred!='COUNT': return None,'NATIVE_NO_EXECUTABLE_PRESTATE_ADAPTER_FOR_PREDICATE'
        key=(pair.get('branch_id'),graph.get('subject'))
        if key not in prestates: return None,'NATIVE_PRESTATE_MISSING_FOR_QUERY'
        state,path=prestates[key]
        replay=verify_count_pair_accessibly(pre_state_subgraph=state['pre_state_subgraph'],accessible_transition=state['accessible_transition'],
            supported_claim=graph,contradictory_claim=pair['contradictory_claim']['graph'],necessary_pre_fact_ids=state['necessary_pre_fact_ids'])
        if replay['status']!='PASS': return None,'NATIVE_TRANSITION_REPLAY_FAILED'
        pre=state['pre_state_subgraph']['facts']; post=[graph]; refs=[str(path)]
    if pred=='COUNT':
        before=[f for f in pre if f['predicate']=='COUNT' and f['subject']==graph['subject']]
        after=[f for f in post if f['predicate']=='COUNT' and f['subject']==graph['subject']]
        if len(before)!=1 or len(after)!=1: return None,'COUNT_SCOPE_OR_ENTITY_NOT_UNIQUE'
        if before[0].get('scope')!=after[0].get('scope'): return None,'COUNT_SCOPE_CHANGED'
        values=[before[0]['value'],after[0]['value']]
        if any(type(v)!=int or v<0 for v in values): return None,'NONINTEGER_COUNT'
        subject=graph.get('subject_label') or graph['subject']
        if ':' in subject: return None,'NONVISIBLE_COUNT_CATEGORY'
        query=f'How many instances of the category "{subject}" are there in the declared scene scope?'
        canonical=lambda v: f'The number of instances of the category "{subject}" in the declared scene scope equals {v}.'
        domain=dict(type='nonnegative_integer',binary_degenerate=False,format='A nonnegative JSON integer; no forced choice list.')
    elif pred in OPPOSITE:
        before=[f for f in pre if f['predicate'] in OPPOSITE and f['subject']==graph['subject'] and f.get('object')==graph.get('object')]
        after=[f for f in post if f['predicate'] in OPPOSITE and f['subject']==graph['subject'] and f.get('object')==graph.get('object')]
        if len(before)!=1 or len(after)!=1: return None,'RELATION_NOT_UNIQUE'
        subject=graph.get('subject_label'); obj=graph.get('object_label')
        if not subject or not obj: return None,'NO_VISIBLE_ENTITY_NAMES'
        values=[before[0]['predicate'],after[0]['predicate']]
        if OPPOSITE[values[0]]!=values[1]: return None,'RELATION_NOT_AUTHORIZED_AXIS_TRANSITION'
        query=f'What is the {AXIS[pred]} relation of the {subject} relative to the {obj}, using the reference frame stated in the intervention?'
        canonical=lambda v: f'The {AXIS[pred]} relation of the {subject} relative to the {obj} is {v}.'
        domain=dict(type='relation',values=sorted([pred,OPPOSITE[pred]]),binary_degenerate=True,format='Use the stated axis relation ontology; UNDETERMINED when evidence is insufficient.')
    else: return None,'PREDICATE_ADAPTER_NOT_SUPPORTED'
    if values[0]==values[1]: return None,'NO_DISTINCT_PRE_POST_VALUE'
    members=requests.get(pid,[])
    if len(members)!=2: return None,'PARENT_PAIR_INCOMPLETE'
    if members[0]['media']!=members[1]['media']: return None,'PARENT_MEDIA_MISMATCH'
    x,y=aliases(cfg['seed'],pid); intervention=members[0].get('intervention_text')
    if not intervention: return None,'INTERVENTION_NOT_IN_ORIGINAL_INPUT'
    scope=str(graph.get('scope','question_local'))
    frame=action.get('parameters',{}).get('reference_frame','as defined by the original scene/task')
    definitions=[dict(alias=x,role='PRE',definition='The initial scene BEFORE the stated intervention.'),dict(alias=y,role='POST',definition='The scene AFTER applying this intervention once: '+intervention)]
    claims=[dict(claim_key='claim_'+digest(v)[:10],text=canonical(v),value=v,invariant=False) for v in values]
    if pred=='COUNT':
        # A proved label-invariant claim; NOT a claim that an unlisted physical fact is invariant.
        vv=max(values)+1; claims.append(dict(claim_key='claim_'+digest(vv)[:10],text=canonical(vv),value=vv,invariant=True))
    claim_gold={c['claim_key']:{s:'SUPPORTED' if v==c['value'] else 'CONTRADICTORY' for s,v in zip([x,y],values)} for c in claims}
    return dict(group_id='group_'+digest([pid,'PRE_POST',query])[:24],cluster_id=cluster(pair['global_world_id']),world_id=pair['global_world_id'],parent_ids=[pid],source='hypo3d',
        original_level='L4',l4_origin=pair['l4_origin'],native_subtype=pair.get('native_subtype'),dependency_type=pair.get('dependency_type'),operator=family,
        diagnostic_design='TARGET_ONLY_SWITCH',state_dimension='PRE_POST',provenance_type='REQUERY_DERIVED',media=members[0]['media'],
        media_context=members[0].get('media_context',''),frame=frame,scope=scope,intervention=intervention,states=definitions,
        fact_query=query,domain=domain,claims=claims,original_inputs=members,
        private=dict(values=dict(zip([x,y],values)),claim_gold=claim_gold,pre_facts=pre,post_facts=post,replay=replay,extra_source_files=refs,
                     local_premise_text=f'In the initial scene, '+canonical(values[0]),
                     local_eligibility='PASS',local_information='PRIVILEGED_SOURCE_UNTIL_DERIVED_INPUT_REVIEW',
                     action=dict(operation=family,target=subject,scope=scope))),None

def group_from_count_arguments(pair, candidate, members, project, cfg):
    if not candidate: return None,'NO_CANDIDATE_TRACE'
    path=project/candidate['evidence_subgraph_path']; ev=load(path)
    expected=candidate.get('artifacts',{}).get(candidate['evidence_subgraph_path'])
    if expected and sha(path)!=expected.removeprefix('sha256:'): return None,'EVIDENCE_HASH_MISMATCH'
    facts=[f for f in ev.get('facts',[]) if f.get('predicate')=='COUNT' and f.get('polarity','positive')=='positive' and type(f.get('value'))==int and str(f.get('subject','')).startswith('class:')]
    if len(facts)!=2 or facts[0]['subject']==facts[1]['subject']: return None,'NO_TWO_GROUNDED_COUNT_ARGUMENTS'
    if facts[0].get('context')!=facts[1].get('context'): return None,'COUNT_CONTEXTS_DIFFER'
    if any(not f.get('provenance') for f in facts): return None,'FACT_PROVENANCE_MISSING'
    if facts[0]['value']==facts[1]['value']: return None,'COUNT_VALUES_NOT_DISTINCT'
    x,y=aliases(cfg['seed'],pair['pair_id']); values={x:facts[0]['value'],y:facts[1]['value']}
    states=[dict(alias=s,role='OBJECT_SCOPE',definition='Use the object category "'+f['subject'][6:]+'" in the designated reference image, not the support images.') for s,f in zip([x,y],facts)]
    canonical=lambda v:f'The target category has exactly {v} visible instances in the designated reference image.'
    cc=list(dict.fromkeys(values.values())); cc.append(max(cc)+1)
    claims=[dict(claim_key='claim_'+digest(v)[:10],text=canonical(v),value=v,invariant=i==2) for i,v in enumerate(cc)]
    return dict(group_id='group_'+digest([pair['pair_id'],'OBJECT_ARGUMENT'])[:24],cluster_id=cluster(pair['source']['global_world_id']),world_id=pair['source']['global_world_id'],
        parent_ids=[pair['pair_id']],source=pair['source']['source_dataset'],original_level=pair['task']['level'],l4_origin=None,native_subtype=None,dependency_type=None,operator=pair['task']['operator_id'],
        diagnostic_design='TARGET_ONLY_SWITCH',state_dimension='OBJECT_ARGUMENT',provenance_type='REQUERY_DERIVED',media=members[0]['media'],media_context=members[0].get('media_context',''),
        frame=facts[0]['context'].get('reference_frame'),scope='reference_frame',intervention=None,states=states,
        fact_query='How many visible instances of the target-defined category are in the designated reference image?',
        domain=dict(type='nonnegative_integer',binary_degenerate=False,format='A nonnegative JSON integer; no forced choice list.'),claims=claims,original_inputs=members,
        private=dict(values=values,claim_gold={c['claim_key']:{s:'SUPPORTED' if v==c['value'] else 'CONTRADICTORY' for s,v in values.items()} for c in claims},
                     pre_facts=facts,post_facts=[],replay=dict(status='PASS',rule='EXACT_SOURCE_COUNT_COMPARISON',fact_ids=[f['fact_id'] for f in facts]),extra_source_files=[str(path)],local_eligibility='NOT_APPLICABLE',action=None)),None

def select_stratified(items,n,seed,key='cluster_id',stratum=None):
    selected=[]; seen=set(); bins=collections.defaultdict(list)
    for item in sorted(items,key=lambda r:stable_rank(seed,r.get('group_id',r.get('pair_id',r.get('sample_id',''))))):
        bins[stratum(item) if stratum else item.get('original_level',item.get('level'))].append(item)
    while len(selected)<n:
        added=False
        for name in sorted(bins,key=str):
            while bins[name] and bins[name][0][key] in seen: bins[name].pop(0)
            if bins[name] and len(selected)<n:
                item=bins[name].pop(0); selected.append(item); seen.add(item[key]); added=True
        if not added: break
    return selected

def main():
    a=args(__doc__).parse_args(); cfg,root,project=setup(a)
    if a.dry_run: print(json.dumps(dict(status='PLANNED',action='mine'))); return
    if load(root/'reports/a0_acceptance.json')['status']!='PASS': raise ValueError('A0_NOT_PASS')
    hist=Path(cfg['historical']); gold=resolved_gold(hist,project); original=list(rows(hist/'requests.jsonl'))
    splits=collections.defaultdict(set)
    for g in gold.values(): splits[cluster(g['global_world_id'])].add(g['split'])
    cross={c:ss for c,ss in splits.items() if len(ss)>1}
    request_by_pair=collections.defaultdict(list); coverage=[]; unknown=[]
    for r in original:
        g=gold[r['sample_id']]; cl=cluster(g['global_world_id'])
        if r['split']!='dev' or cl in cross: continue
        item=dict(r,cluster_id=cl,world_id=g['global_world_id'],original_level=r['level'])
        if r['component']=='binary': request_by_pair[r['pair_id']].append(r)
        else: unknown.append(item)
    for pid,members in request_by_pair.items():
        if len(members)!=2 or members[0]['media']!=members[1]['media']: raise ValueError('PAIR_PRESENTATION_OR_SIZE_MISMATCH:'+pid)
        g=gold[members[0]['sample_id']]
        coverage.append(dict(pair_id=pid,cluster_id=cluster(g['global_world_id']),world_id=g['global_world_id'],original_level=g['level'],source=g['dataset'],inputs=members))
    l4=list(rows(project/'l4/v3_3/release/pairs.l4_three_part_v3.jsonl'))
    prepath=project/'transition_micrographs/hypo3d_l4_v2_official_referit3d_fusion_v2_7/prestates.count_v2.jsonl'
    preindex={}
    for r in rows(prepath):
        for f in r['pre_state_subgraph']['facts']:
            if f['predicate']=='COUNT': preindex[r['branch_id'],f['subject']]=(r,prepath)
    groups=[]; excludes=[]
    for p in l4:
        if p['pair_id'] not in request_by_pair: continue
        group,reason=group_from_l4(p,request_by_pair,preindex,cfg)
        if group: groups.append(group)
        else: excludes.append(dict(parent_id=p['pair_id'],level='L4',source='hypo3d',reason=reason))
    candidate_index={}
    for file in ['pairs.proof_verification_p1_v2.jsonl','pairs.proof_verification_ca_train_production_v1.jsonl','pairs.proof_verification_l2_relation_graph_v1.jsonl','pairs.proof_verification_spar_7m_l1_v1.jsonl','pairs.proof_verification_spar_7m_l2_bbox_v3.jsonl','pairs.proof_verification_spar_7m_l3_xform_v1.jsonl']:
        for r in rows(project/'candidates/auto_accepted'/file):
            if r['pair_id'] in request_by_pair: candidate_index[r['pair_id']]=r
    l3_factkeys=collections.defaultdict(list)
    for pair in rows(project/'release/production_available_v10/pairs.jsonl'):
        pid=pair['pair_id']
        if pid not in request_by_pair: continue
        candidate=candidate_index.get(pid); level=pair['task']['level']; source=pair['source']['source_dataset']
        group=None; reason='NO_COUNT_ARGUMENT_ADAPTER_FOR_SOURCE'
        if source=='ca_vqa': group,reason=group_from_count_arguments(pair,candidate,request_by_pair[pid],project,cfg)
        elif level=='L3' and candidate:
            ev=load(project/candidate['evidence_subgraph_path'])
            for f in ev.get('facts',[]):
                key=(pair['source']['global_world_id'],f.get('subject'),f.get('object'),f.get('predicate'))
                l3_factkeys[key].append(dict(parent_id=pid,context=f.get('context'),grounding=f.get('grounding'),fact_id=f.get('fact_id')))
            reason='NO_VERIFIED_MULTI_STATE_VISUAL_IDENTITY_ADAPTER; see l3_feasibility.json'
        if group: groups.append(group)
        else: excludes.append(dict(parent_id=pid,level=level,source=source,reason=reason))
    # Inspect equal canonical entity IDs across state scopes, but do not certify cross-view identity by string alone.
    l3potential=[]
    for key,ff in l3_factkeys.items():
        contexts={digest(f['context']) for f in ff}
        if len(contexts)>1: l3potential.append(dict(key=key,facts=ff,status='REQUIRES_EXPLICIT_SHARED_IDENTITY_AND_REFERENCE_FRAME_VERIFIER'))
    write(root/'reports/l3_feasibility.json',dict(released_dev_parents_examined=sum(x['original_level']=='L3' for x in coverage),fact_keys_examined=len(l3_factkeys),
        cross_context_candidate_keys=len(l3potential),candidates=l3potential,verified_target_only_groups=0,
        limitation='First round adapter establishes L4 PRE_POST and CA exact-count OBJECT_ARGUMENT only; zero implemented L3 groups is not a proof of zero potential in the dataset.'))
    # Select setup BEFORE partition; stratified solely by structural metadata, no outputs.
    setup_groups=select_stratified(groups,4,cfg['seed'],stratum=lambda r:(r['state_dimension'],r.get('l4_origin') or '',r['domain']['type']))
    setup_clusters={g['cluster_id'] for g in setup_groups}
    for c in select_stratified([r for r in coverage if r['cluster_id'] not in setup_clusters],cfg['sampling']['setup_clusters']-len(setup_clusters),cfg['seed']+1): setup_clusters.add(c['cluster_id'])
    devclusters=sorted({r['cluster_id'] for r in coverage+unknown},key=lambda c:stable_rank(cfg['seed'],c))
    remaining=[c for c in devclusters if c not in setup_clusters]; splitat=int(len(remaining)*cfg['sampling']['discovery_fraction'])
    discovery=set(remaining[:splitat]); confirmation=set(remaining[splitat:])
    partition={c:'setup' if c in setup_clusters else 'discovery' if c in discovery else 'confirmation' for c in devclusters}
    assert not setup_clusters&discovery and not setup_clusters&confirmation and not discovery&confirmation
    for g in groups: g['partition']=partition[g['cluster_id']]
    for g in coverage+unknown: g['partition']=partition[g['cluster_id']]
    mechanisms=select_stratified([g for g in groups if g['partition']=='discovery'],cfg['sampling']['mechanism_cap'],cfg['seed'],stratum=lambda r:(r['original_level'],r.get('l4_origin') or '',r['domain']['type']))
    coverage_selected=[]; used=set()
    for level,n in cfg['sampling']['coverage_targets'].items():
        selected=select_stratified([c for c in coverage if c['partition']=='discovery' and c['original_level']==level and c['cluster_id'] not in used],n,cfg['seed'],stratum=lambda r:r['source'])
        coverage_selected.extend(selected); used.update(c['cluster_id'] for c in selected)
    unknown_selected=select_stratified([r for r in unknown if r['partition']=='discovery'],cfg['sampling']['unknown_cap'],cfg['seed'])
    for g in groups:
        for idx,state in enumerate(g['states']):
            state['state_key']=dict(view_id=None,reference_frame=g['frame'],time_scope=None,branch_id=g['parent_ids'][0] if g['state_dimension']=='PRE_POST' else 'actual',state_role=state['role'])
        g['review_status']='USER_ATTESTED_PARENT_REVIEW_PASS_DERIVED_QUERY_PROVISIONAL'
    frozen_write(root/'manifest/cluster_split.json',dict(seed=cfg['seed'],partition=partition,excluded_known_cross_split_clusters={c:sorted(s) for c,s in cross.items()},confirmation_inference=False))
    frozen_write(root/'manifest/all_eligible_groups.private.jsonl',groups,'jsonl')
    frozen_write(root/'manifest/prospective_mechanism.private.jsonl',mechanisms,'jsonl')
    frozen_write(root/'manifest/prospective_coverage.jsonl',coverage_selected,'jsonl')
    frozen_write(root/'manifest/prospective_unknown.jsonl',unknown_selected,'jsonl')
    frozen_write(root/'manifest/setup_groups.private.jsonl',[g for g in groups if g['group_id'] in {x['group_id'] for x in setup_groups}],'jsonl')
    frozen_write(root/'manifest/setup_coverage.jsonl',select_stratified([c for c in coverage if c['cluster_id'] in setup_clusters],8,cfg['seed']),'jsonl')
    frozen_write(root/'manifest/original_gold.dev.jsonl',[g for g in gold.values() if g['split']=='dev'],'jsonl')
    csvwrite(root/'tables/eligibility_exclusions.csv',excludes)
    coverage_stats=[]
    for level in ['L1','L2','L3','L4']:
        parent=[p for p in coverage if p['original_level']==level]; eligible=[g for g in groups if g['original_level']==level]
        coverage_stats.append(dict(level=level,released_dev_pairs=len(parent),eligible_groups=len(eligible),eligible_clusters=len({g['cluster_id'] for g in eligible}),
            prospective_mechanism=sum(g['original_level']==level for g in mechanisms),prospective_coverage=sum(g['original_level']==level for g in coverage_selected),model_outcomes_used=False))
    csvwrite(root/'tables/state_switch_coverage.csv',coverage_stats)
    csvwrite(root/'review/human_review_status.csv',[dict(group_id=g['group_id'],parent_dataset_review='PASS',basis=cfg['review']['basis'],reviewer_count=None,new_derivative_review='PROVISIONAL',codex_human_review=False) for g in groups])
    write(root/'reports/mining_report.json',dict(status='PASS' if mechanisms else 'BLOCKED',total_dev_clusters=len(devclusters),setup_clusters=len(setup_clusters),discovery_clusters=len(discovery),sealed_confirmation_clusters=len(confirmation),
        groups=len(groups),prospective_common_groups=len(mechanisms),coverage_pairs=len(coverage_selected),unknown=len(unknown_selected),scope='COUNT_OBJECT_ARGUMENT_AND_VERIFIED_L4_PRE_POST',
        invariant_note='Count-based additional claims have verified unchanged LABEL; no unsupported physical invariant inferred.',source_hashes=[evidence_entry(prepath)]))
    print(json.dumps(load(root/'reports/mining_report.json')))

if __name__=='__main__': main()
