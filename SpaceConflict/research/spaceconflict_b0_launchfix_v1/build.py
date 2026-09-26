"""Freeze controlled B0 inputs based only on source truth, never model outputs."""
import re
from collections import Counter
from b0common import *
from contracts_v3 import SYSTEM, SCALAR, LABEL

JOINT = ('Report the exact target count and evaluate the candidate statement from the supplied evidence. '
         'Return exactly one JSON object with keys {order}. Write these keys in exactly this order. '
         'target_value must be a nonnegative JSON integer if uniquely determined, otherwise null. '
         'verdict must be SUPPORTED, CONTRADICTORY, or UNKNOWN. '
         'SUPPORTED means the evidence establishes the candidate; CONTRADICTORY means it establishes an incompatible fact; '
         'UNKNOWN means neither is established. No explanation or extra keys.')


def make_panel(c,root):
    panels=[]
    old=list(rows(root/'manifest/b0_a_source_cards.jsonl'))
    for r in old:
        panels.append(dict(world_id=r['world_id'],underlying_world_id=r['underlying_world_id'],group_id=r['group_id'],
            cohort='B0_A',source=r['source'],category=r['category'],values=r['values'],
            operation=r['action_expected']['operation'],amount=r['action_expected']['amount'],
            full_media_context=r['full_media_context'],local_pre_context=r['local_pre_context'],media=r['media'],
            provenance='EXPOSED_A1_RESEARCHER_ATTESTED_SOURCE_REPLAYED',source_proof_sha256=r['source_proof_sha256'],
            source_truth_sha256=r['source_truth_sha256'],parent_pair_ids=[],review_status='REUSED_A1_MEDIA_REVIEW',
            counting_scope=r['count_scope'],intervention=r['full_media_context'].split('Hypothetical intervention: ',1)[1].split('\nPRE denotes',1)[0]))
    for item in rows(root/'private_gold/selected_extension.jsonl'):
        g=item['group']; category=item['category']; roles='; '.join(f'Image {i+1}: {m["role"]}' for i,m in enumerate(g['media']))
        scope='the whole scene represented by the supplied views, not only the first camera crop'
        local=('The supplied media depict the initial scene, before any hypothetical intervention.\n'
               f'Query category: {category}\nCounting scope: {scope}.\nReference image / view roles: {roles}.\n'
               'Count distinct instances within this scope. Do not count the same instance again merely because it appears in another view.')
        full=local+'\nHypothetical intervention: '+g['intervention']+'\nPRE denotes the initial scene.\nPOST denotes the result of applying this intervention exactly once within the stated scope.\nNo supplied image is a post-intervention image.'
        panels.append(dict(world_id=g['world_id'],underlying_world_id=g['cluster_id'],group_id=g['group_id'],cohort='B0_B',source=g['source'],
            category=category,values=item['values'],operation=item['operation'],amount=item['amount'],full_media_context=full,
            local_pre_context=local,media=g['media'],provenance='SOURCE_CONTROLLED_DUAL_ENGINE_AUTO_REPLAY_EXPLORATORY',
            source_proof_sha256=digest(g['private']['replay']),source_truth_sha256=item['source_pair_sha256'],parent_pair_ids=g['parent_ids'],
            review_status='AUTO_PROOF_PASS_PENDING_PROCESSOR',counting_scope=scope,intervention=g['intervention']))
    assert len({p['underlying_world_id'] for p in panels})==len(panels)
    assert len(panels)<=7+c['extension_world_hard_max']
    return panels


def construct(c,panels):
    req=[]; gold=[]; matches=[]; unavailable=[]
    for p in panels:
        lookup={}; gid=p['group_id']; vals=p['values']
        assert vals['PRE']+(p['amount'] if p['operation']=='ADD' else -p['amount'])==vals['POST']
        def add(condition,target,claim=None,wording='W0',context='I1',order='',repeat=0,evidence='',organization=''):
            schema=dict(kind='fact_verdict',order=['target_value','verdict'] if order=='FACT_FIRST' else ['verdict','target_value']) if condition=='FACT_VERDICT' else dict(kind='verdict') if condition=='VERDICT_ONLY' else dict(kind='value',domain='count',nullable=True)
            if condition=='MISSING_FACTORIAL':
                common=('This is a controlled text-only record task. PRE and POST are state-indexed records for the count of category "'+p['category']+'". '
                        'Use only the records below; no media, intervention rule, or equality between states is supplied. '
                        'The absence of a value does not make it zero, nor equal to the other state.\n')
                available={k:v for k,v in vals.items() if evidence=='COMPLETE' or k!=target}
                if organization=='CORE_NARRATIVE': body=common+'\n'.join(f'The {k} record reports query_count = {v}.' for k,v in available.items())
                else: body=common+'state | query_count\n'+'\n'.join(f'{k} | {v}' for k,v in available.items())
                body+=f'\nTARGET_STATE: {target}\nReturn query_count for TARGET_STATE.\n'+SCALAR
                media=[]
            else:
                body=(p['full_media_context'] if context=='I1' else p['local_pre_context'].replace(
                    'The supplied media depict the initial scene, before any hypothetical intervention.',
                    'The supplied media depict the current scene.')+'\nPRE denotes the initial scene.')
                body+=f'\nTARGET_STATE: {target}'
                if claim is not None:
                    body+=(f'\nCandidate statement: the query category count in TARGET_STATE is exactly {claim}.\n'
                           'This statement is a claim to evaluate, not evidence.')
                if wording=='W0': query='Independently report the exact count of the query category in TARGET_STATE.'
                else: query='Using the supplied evidence independently, how many distinct instances of the query category are in TARGET_STATE?'
                if condition=='FACT_VERDICT': body+='\n'+query+'\n'+JOINT.format(order=', '.join(schema['order']))
                elif condition=='VERDICT_ONLY':
                    body+='\n'+('Evaluate the candidate statement for TARGET_STATE.' if wording=='W0' else 'Decide whether the supplied evidence supports, contradicts, or leaves undecided the candidate for TARGET_STATE.')+'\n'+LABEL
                else: body+='\n'+query+'\n'+SCALAR
                media=p['media']
            r=dict(run_id=c['run_id'],protocol_version=c['protocol_version'],models=c['models'],stage='core',level='L4',
                group_id=gid,underlying_world_id=p['underlying_world_id'],world_id=p['world_id'],cohort=p['cohort'],
                condition=condition,target=target,claim_value=claim,wording=wording,context=context,order=order,repeat=repeat,
                evidence=evidence,organization=organization,schema=schema,parent_request_id='',
                payload=dict(system=SYSTEM,text=body,media=media))
            r['request_id']='b0_'+digest(r)[:28]; req.append(r)
            typ='neutral' if claim is None else 'target_match' if claim==vals[target] else 'other_state' if claim==vals['POST' if target=='PRE' else 'PRE'] else 'neither_state'
            g=dict(request_id=r['request_id'],schema=schema,fact_gold=None if evidence=='MISSING' else vals[target],
                gold_verdict=None if claim is None else 'SUPPORTED' if claim==vals[target] else 'CONTRADICTORY',
                claim_value=claim,claim_type=typ,delta=None if claim is None else claim-vals[target],
                operation=p['operation'],amount=p['amount'],category=p['category'],source=p['source'],source_dataset=p['source'],
                source_family=p['underlying_world_id'].split(':')[0],source_values=vals,
                world_id=p['underlying_world_id'],cohort=p['cohort'],source_proof_sha256=p['source_proof_sha256'],
                source_truth_sha256=p['source_truth_sha256'],condition_eligible=True,
                missing_witnesses=[{**{k:v for k,v in vals.items() if k!=target},target:n} for n in [0,1]] if evidence=='MISSING' else None)
            gold.append(g); lookup[condition,target,claim,wording,context,order,repeat,evidence,organization]=r
            return r
        def get(cond,t,claim=None,w='W0',ctx='I1',order='',rep=0,ev='',org=''):
            return lookup[cond,t,claim,w,ctx,order,rep,ev,org]
        def match(kind,a,b):
            m=dict(comparison=kind,underlying_world_id=p['underlying_world_id'],cohort=p['cohort'],
                   base_request_id=a['request_id'],control_request_id=b['request_id'])
            m['match_id']='b0m_'+digest(m)[:24]; matches.append(m)
        for t in ['PRE','POST']:
            candidates={vals['PRE'],vals['POST']}
            for d in c['offsets']:
                if vals[t]+d>=0: candidates.add(vals[t]+d)
                else: unavailable.append(dict(world_id=p['underlying_world_id'],target=t,delta=d,reason='NEGATIVE_OFFSET_NOT_APPLICABLE'))
            assert any(v not in vals.values() for v in candidates)
            for ctx in (['I1','I0'] if t=='PRE' else ['I1']):
                for w in c['wording_variants']:
                    n0=add('FACT_NEUTRAL',t,wording=w,context=ctx)
                    n1=add('FACT_NEUTRAL',t,wording=w,context=ctx,repeat=1)
                    assert n0['payload']==n1['payload']
                    match('NEUTRAL_RECOUNT_REPEAT',n0,n1)
                    for claim in sorted(candidates):
                        fact=add('FACT_CLAIM',t,claim,w,ctx)
                        verdict=add('VERDICT_ONLY',t,claim,w,ctx)
                        ff=add('FACT_VERDICT',t,claim,w,ctx,'FACT_FIRST')
                        vf=add('FACT_VERDICT',t,claim,w,ctx,'VERDICT_FIRST')
                        match('NEUTRAL_TO_TRUE_CLAIM' if claim==vals[t] else 'NEUTRAL_TO_FALSE_CLAIM',n0,fact)
                        match('FACT_FIRST_TO_VERDICT_FIRST',ff,vf)
                        match('FACT_CLAIM_TO_JOINT_FACT_FIRST',fact,ff)
                        match('VERDICT_ONLY_TO_JOINT_FACT_FIRST',verdict,ff)
                for condition,claim,order,rep in [('FACT_NEUTRAL',None,'',0)]+[(co,cv,od,0) for cv in sorted(candidates) for co,od in [('FACT_CLAIM',''),('VERDICT_ONLY',''),('FACT_VERDICT','FACT_FIRST'),('FACT_VERDICT','VERDICT_FIRST')]]:
                    match('WORDING_W0_TO_W1',get(condition,t,claim,'W0',ctx,order,rep),get(condition,t,claim,'W1',ctx,order,rep))
            if t=='PRE':
                for w in c['wording_variants']:
                    for condition,claim,order,rep in [('FACT_NEUTRAL',None,'',0)]+[(co,cv,od,0) for cv in sorted(candidates) for co,od in [('FACT_CLAIM',''),('VERDICT_ONLY',''),('FACT_VERDICT','FACT_FIRST'),('FACT_VERDICT','VERDICT_FIRST')]]:
                        match('NO_INTERVENTION_TO_INTERVENTION',get(condition,t,claim,w,'I0',order,rep),get(condition,t,claim,w,'I1',order,rep))
            for ev in ['COMPLETE','MISSING']:
                for org in ['CORE_NARRATIVE','INDEPENDENT_TABLE']:
                    add('MISSING_FACTORIAL',t,evidence=ev,organization=org)
                match('FACTORIAL_ORGANIZATION_'+ev,get('MISSING_FACTORIAL',t,ev=ev,org='CORE_NARRATIVE'),get('MISSING_FACTORIAL',t,ev=ev,org='INDEPENDENT_TABLE'))
            for org in ['CORE_NARRATIVE','INDEPENDENT_TABLE']:
                match('FACTORIAL_COMPLETENESS_'+org,get('MISSING_FACTORIAL',t,ev='COMPLETE',org=org),get('MISSING_FACTORIAL',t,ev='MISSING',org=org))
    assert len(req)==len({r['request_id'] for r in req})<=c['max_requests_per_model']
    req.sort(key=lambda r:digest([c['seed'],r['request_id']]))
    return req,gold,matches,unavailable


def smoke(c):
    requests=[]; truth=[]
    # New interface smoke only: fixed explicit synthetic records, not a rerun of old bridge.
    for n,(value,claim) in enumerate([(2,2),(3,1),(None,2)]):
        for order in ['FACT_FIRST','VERDICT_FIRST']:
            schema=dict(kind='fact_verdict',order=['target_value','verdict'] if order=='FACT_FIRST' else ['verdict','target_value'])
            body=('This is an explicit record lookup. TARGET_STATE: PRE. No transition or relation between states is supplied.\n'
                  +('PRE query_count is not supplied.' if value is None else f'PRE query_count = {value}.')+
                  f'\nPOST query_count = 4.\nCandidate statement: PRE query_count = {claim}.\n'+JOINT.format(order=', '.join(schema['order'])))
            r=dict(run_id=c['run_id'],protocol_version=c['protocol_version'],models=c['models'],stage='smoke',level='SETUP',
                group_id=f'b0_setup_{n}',underlying_world_id=f'b0_setup_{n}',world_id=f'b0_setup_{n}',cohort='ENGINEERING',
                condition='FACT_VERDICT',target='PRE',claim_value=claim,wording='W0',context='EXPLICIT_TABLE',order=order,repeat=0,
                evidence='',organization='',schema=schema,parent_request_id='',payload=dict(system=SYSTEM,text=body,media=[]))
            r['request_id']='b0_'+digest(r)[:28]; requests.append(r)
            truth.append(dict(request_id=r['request_id'],schema=schema,fact_gold=value,claim_value=claim,
                              gold_verdict='UNKNOWN' if value is None else 'SUPPORTED' if value==claim else 'CONTRADICTORY'))
    source=load(Path(c['a1_root'])/'manifest/independent_smoke_source.json')['source_group']
    context=('All supplied images depict PRE. Count distinct instances once across views. Query: '+source['fact_query']+
             '\nHypothetical intervention: '+source['intervention']+'\nPRE is the initial scene. POST is after applying this intervention once.'+
             '\nTARGET_STATE: PRE\nCandidate statement: the queried count in PRE is exactly 2. This candidate is not evidence.')
    for order in ['FACT_FIRST','VERDICT_FIRST']:
        schema=dict(kind='fact_verdict',order=['target_value','verdict'] if order=='FACT_FIRST' else ['verdict','target_value'])
        r=dict(requests[0],group_id=source['group_id'],underlying_world_id=source['cluster_id'],world_id=source['world_id'],
               order=order,schema=schema,claim_value=2,context='INDEPENDENT_SETUP_MEDIA',
               payload=dict(system=SYSTEM,text=context+'\n'+JOINT.format(order=', '.join(schema['order'])),media=source['media']))
        r.pop('request_id'); r['request_id']='b0_'+digest(r)[:28]; requests.append(r)
        truth.append(dict(request_id=r['request_id'],schema=schema,fact_gold=None,claim_value=2,gold_verdict=None,
                          engineering_only_no_accuracy=True))
    return requests,truth


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('Construct B0 requests from source-only selected panel, no generation'); return
    compute(); panels=make_panel(c,root); req,gold,matches,unavailable=construct(c,panels); sr,sg=smoke(c)
    save(root/'02_B0_PANEL_MANIFEST.jsonl',panels,'jsonl')
    save(root/'inputs/core/requests.jsonl',req,'jsonl'); save(root/'private_gold/core.jsonl',gold,'jsonl')
    save(root/'inputs/smoke/requests.jsonl',sr,'jsonl'); save(root/'private_gold/smoke.jsonl',sg,'jsonl')
    save(root/'manifest/matched_pairs.jsonl',matches,'jsonl')
    union_csv(root/'tables/not_applicable_offsets.csv',unavailable)
    summary=dict(status='DRAFT_BUILT_AWAITING_ACTUAL_PROCESSOR',worlds=len(panels),core_requests_per_model=len(req),
                 core_requests_total=3*len(req),smoke_per_model=len(sr),matches=len(matches),conditions=dict(Counter(r['condition'] for r in req)))
    save(root/'manifest/build_summary.json',summary); print(json.dumps(summary),flush=True)


if __name__=='__main__': main()
