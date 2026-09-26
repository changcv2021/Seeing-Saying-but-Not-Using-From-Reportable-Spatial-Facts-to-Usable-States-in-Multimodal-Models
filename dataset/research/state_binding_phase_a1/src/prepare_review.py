"""Prepare all 16 exposed groups for review. Never reads prediction fields or selects by failures."""
import re
from collections import Counter, defaultdict
from common import *
from interfaces import request

def main():
    a=arguments(__doc__).parse_args(); cfg,root=setup(a)
    if a.dry_run: print('PLANNED: 16-group derived review drafts; no core inference authorization'); return
    require_compute()
    if load(root/'reports/setup_calibration_acceptance.json')['status']!='PASS': raise ValueError('SETUP_GATE_MUST_PASS_FIRST')
    old=Path(cfg['phase_a_root']); project=Path(cfg['project'])
    groups=list(rows(old/'manifest/discovery/state_group_manifest.jsonl'))
    truth={r['group_id']:r for r in rows(old/'gold/discovery/state_truth.jsonl')}
    gidset={g['group_id'] for g in groups}
    assert len(groups)==len(gidset)==16
    # The user's CSV is the authoritative level column; ignore all response/score fields.
    levels=defaultdict(set); dimensions=defaultdict(set)
    with Path(cfg['phase_a_csv']).open(newline='') as f:
        for r in csv.DictReader(f):
            if r['group_id'] in gidset:
                levels[r['group_id']].add(r['level']); dimensions[r['group_id']].add(r['state_dimension'])
    source_pairs={}
    parentids={pid for g in groups for pid in g['parent_ids']}
    for r in rows(project/'l4/v3_3/release/pairs.l4_three_part_v3.jsonl'):
        if r['pair_id'] in parentids: source_pairs[r['pair_id']]=r
    nativepath=project/'transition_micrographs/hypo3d_l4_v2_official_referit3d_fusion_v2_7/prestates.count_v2.jsonl'
    native={}
    nativebranches={p.get('branch_id') for p in source_pairs.values() if p['l4_origin']=='SOURCE_NATIVE'}
    for r in rows(nativepath):
        if r['branch_id'] in nativebranches:
            for f in r['pre_state_subgraph']['facts']:
                if f['predicate']=='COUNT': native[r['branch_id'],f['subject']]=r
    sys.path.insert(0,str(project/'src'))
    from spaceconflict.l4_three_part.engine_a import execute_transition_a
    from spaceconflict.l4_three_part.checker_b import check_transition_b
    from spaceconflict.hypo3d_l4.verification import verify_count_pair_accessibly
    oldactions={r['group_id']:r for r in rows(old/'gold/discovery/gold.jsonl') if r.get('kind')=='action'}
    drafts=[]; gold=[]; panel=[]; review=[]; proofs=[]
    for g in groups:
        gid=g['group_id']; t=truth[gid]
        if levels[gid]!={g['original_level']} or dimensions[gid]!={g['state_dimension']}: raise ValueError('CSV_LEVEL_OR_DIMENSION_MISMATCH:'+gid)
        level=next(iter(levels[gid])); dim=next(iter(dimensions[gid])); binary=g['domain']['binary_degenerate']
        if (level,dim) not in [('L4','PRE_POST'),('L1','OBJECT_ARGUMENT')]: raise ValueError('OUT_OF_SCOPE_GROUP')
        if g['partition']!='discovery': raise ValueError('NO_CONFIRMATION_OR_TEST')
        dom=g['domain']['values'] if binary else 'count'
        names={s['alias']:s['role'] for s in g['states']} if level=='L4' else {s['alias']:f'OBJECT_{i+1}' for i,s in enumerate(g['states'])}
        values={names[s['alias']]:t['values'][s['alias']] for s in g['states']}
        states=list(values); assert len(states)==2 and len(set(values.values()))==2
        checks=[]; action=None; amount=None; source=None; proof={}
        if level=='L4':
            parent=source_pairs[g['parent_ids'][0]]; source=parent
            if parent['l4_origin']=='BENCHMARK_CONTROLLED':
                pre=parent['pre_state_reference']['facts']; act=parent['intervention']
                aa=execute_transition_a(pre,act); bb=check_transition_b(pre,act)
                if aa['status']!='PASS' or bb['status']!='PASS' or aa['post_facts']!=bb['post_facts']: raise ValueError('SOURCE_REPLAY_FAILED:'+gid)
                proof=dict(engine_a=aa,checker_b=bb)
                params=act.get('parameters',{})
                if g['operator']=='REMOVE_AND_RECOUNT' and params.get('target_id'): amount=1
                if g['operator']=='ADD_AND_RECOUNT': amount=params.get('quantity')
            else:
                graph=parent['supported_claim']['graph']; n=native[parent['branch_id'],graph['subject']]
                proof=verify_count_pair_accessibly(pre_state_subgraph=n['pre_state_subgraph'],accessible_transition=n['accessible_transition'],
                    supported_claim=graph,contradictory_claim=parent['contradictory_claim']['graph'],necessary_pre_fact_ids=n['necessary_pre_fact_ids'])
                if proof['status']!='PASS': raise ValueError('NATIVE_REPLAY_FAILED:'+gid)
                # Native quantity remains a review item. Do not infer amount from POST-PRE.
                actiontrace=n['accessible_transition']; proof=dict(replay=proof,accessible_transition=actiontrace)
                for key in ['quantity','count','amount']:
                    val=actiontrace.get(key)
                    if type(val)==int and val>0: amount=val; break
                if amount is None:
                    params=actiontrace.get('parameters',{})
                    for key in ['quantity','count','amount']:
                        val=params.get(key)
                        if type(val)==int and val>0: amount=val; break
                # Source-native English numeral is a deterministic parser, with exact source text retained for review.
                if amount is None:
                    txt=g['intervention'].lower()
                    if g['operator']=='ADDITION' and re.match(r'^two\b',txt): amount=2
                    elif g['operator']=='ADDITION' and re.match(r'^(a|one)\b',txt): amount=1
                    elif g['operator']=='REMOVAL' and txt=='the blanket on the sofa has been removed.': amount=1
                proof['amount_rule']='EXPLICIT_SOURCE_QUANTITY_OR_RESTRICTED_SOURCE_TEXT_NUMERAL; NOT_POST_MINUS_PRE'
            if not binary:
                pre=t['pre_facts']; post=t['post_facts']; category=t['action']['target']
                before=[f for f in pre if f['predicate']=='COUNT' and f['subject']==category]
                after=[f for f in post if f['predicate']=='COUNT' and f['subject']==category]
                if len(before)!=1 or len(after)!=1 or (before[0]['value'],after[0]['value'])!=(values['PRE'],values['POST']): raise ValueError('SOURCE_VALUE_ALIGNMENT_FAILED:'+gid)
                if amount is not None:
                    action=dict(operation=oldactions[gid]['operation'],target=category,amount=amount)
                    delta=amount if action['operation']=='ADD' else -amount
                    if values['PRE']+delta!=values['POST']: raise ValueError('SOURCE_ACTION_AMOUNT_DISAGREEMENT:'+gid)
                else: checks.append('ACTION_AMOUNT_REQUIRES_SOURCE_REVIEW')
                query=f'Query variable: the number of instances of category "{category}" in the whole scene represented by these views. Count scene instances once, not once per image.'
                context='All supplied images are different presentations of the initial scene (PRE), not observations of POST. The query scope is the whole represented scene, not only the first camera crop. If the supplied presentations do not establish an exact value, report null.'
            else:
                query='Query variable: '+g['fact_query']
                context=('All supplied images depict the initial scene (PRE). The source uses '+g['frame']+
                         '. Mapping of these axes to the displayed images is not yet certified. Do not substitute camera-left/right for source-world axes. If unclear, report null.')
                checks.append('REFERENCE_FRAME_UNCLEAR')
            intervention='Hypothetical intervention, applied once to PRE: '+g['intervention']
            definitions='PRE means before the intervention; POST means after applying it exactly once.'
        else:
            checks.append('REFERENCE_IMAGE_VISIBILITY_AND_CATEGORY_SCOPE_REQUIRE_REVIEW')
            query='Query variable: visible instance count of the target object category in image 1 (role reference_frame), not in the four support images.'
            context='Image 1 is the designated reference frame. Other images are support views; do not add counts across images.'
            definitions='\n'.join(names[s['alias']]+': '+s['definition'] for s in g['states'])
            intervention=''
            for f in t['pre_facts']:
                if not f.get('provenance') or f['predicate']!='COUNT': raise ValueError('L1_COUNT_PROVENANCE_MISSING')
            proof=dict(status='PASS',rule='EXACT_SOURCE_COUNT_COMPARISON',pre_facts=t['pre_facts'])
        stateorder=states if int(digest([cfg['seed'],gid])[:8],16)%2==0 else states[::-1]
        stratum='L1_OBJECT_ARGUMENT_CONTROL' if level=='L1' else 'L4_BINARY_RELATION_SECONDARY' if binary else 'L4_COUNT_PRIMARY'
        commonmeta=dict(level=level,state_dimension=dim,world_id=g['world_id'],source=g['source'],operator=g['operator'],stratum=stratum,review_status='DRAFT_NOT_VERIFIED')
        def add(cond,text,sch,expected,media=True,**extra):
            r=request(cfg,gid,cond,text,sch,g['media'] if media else [],**commonmeta,**extra)
            r['cluster_id']=g['cluster_id']
            # request ID is a stable input identity; cluster mutation is deterministic metadata only.
            drafts.append(r); gold.append(dict(request_id=r['request_id'],group_id=gid,schema=sch,expected=expected,
                source_group_id=gid,source_truth_sha256=digest(t),values=values,action_target_metric='EXACT_CANONICAL_CATEGORY_NOT_FULL_INSTANCE_SEMANTICS' if sch['kind']=='action' else None))
        visualschema=dict(kind='value',domain=dom,nullable=True); oracleschema=dict(kind='value',domain=dom,nullable=False)
        if level=='L4':
            add('PRE_VALUE',context+'\n'+query+'\nReturn the query variable in PRE.',visualschema,values['PRE'],target='PRE')
            if action is not None:
                add('ACTION_PARSE',context+'\n'+intervention+'\nParse the operation, affected category, and explicitly affected quantity. Do not compute final counts.',dict(kind='action'),action)
            add('POST_VALUE',context+'\n'+intervention+'\n'+query+'\nReturn the query variable in POST.',visualschema,values['POST'],target='POST')
        else:
            for s in g['states']:
                target=names[s['alias']]
                add('OBJECT_VALUE',context+'\n'+s['definition']+'\n'+query,visualschema,values[target],target=target)
        for order in [states,states[::-1]]:
            add('JOINT_STATE' if level=='L4' else 'JOINT_OBJECT',context+'\n'+intervention+'\n'+definitions+'\n'+query+'\nReport each named key in this order: '+', '.join(order)+'.',
                dict(kind='joint',domain=dom,nullable=True,keys=order),values,key_order=order)
        table_header='Explicit oracle table for an independent text-only task. QUERY_VALUE denotes the query variable. UNRELATED_REGISTER is not the query variable. No picture evidence is required.\n'
        table=table_header+\
              '\n'.join(f'{s}: QUERY_VALUE = {json.dumps(values[s])}' for s in stateorder)
        for j,target in enumerate(states):
            other=next(s for s in states if s!=target); suffix=f'\nTARGET = {target}. Return QUERY_VALUE for TARGET only.'
            add('SINGLE_STATE_LOOKUP',f'Explicit table.\n{target}: QUERY_VALUE = {json.dumps(values[target])}'+suffix,oracleschema,values[target],media=False,target=target,is_oracle=True)
            add('MULTI_STATE_TARGET_SELECT' if j==0 else 'TARGET_FLIP',table+suffix,oracleschema,values[target],media=False,target=target,is_oracle=True,matched_family='O2_TARGET_PAIR',table_order=stateorder)
            sham=table_header+'\n'.join(f'{s}: '+(f'QUERY_VALUE = {json.dumps(values[target])}' if s==target else f'UNRELATED_REGISTER = {json.dumps(values[s])}') for s in stateorder)
            add('SHAM',sham+suffix,oracleschema,values[target],media=False,target=target,is_oracle=True,table_order=stateorder)
            if not binary:
                for k in [2,3]:
                    d=max(values.values())+k
                    symbolic='SYMBOLIC CONTROL ONLY: this is a new independent register table, not a claim about the original scene.\n'+'\n'.join(f'{s}: QUERY_VALUE = {values[target] if s==target else d}' for s in stateorder)
                    add('DISTRACTOR_REPLACEMENT',symbolic+suffix,oracleschema,values[target],media=False,target=target,is_oracle=True,distractor_value=d,distractor_variant=k-1,table_order=stateorder)
            claims=[('target_match',values[target]),('other_state',values[other])]
            if not binary: claims.append(('neither_state',max(values.values())+1))
            for typ,c in claims:
                label='SUPPORTED' if c==values[target] else 'CONTRADICTORY'
                claim=f'\nTARGET = {target}. Claim: the query variable for TARGET equals {json.dumps(c)}.'
                add('CLAIM_MEDIA',context+'\n'+intervention+'\n'+definitions+'\n'+query+claim,dict(kind='verdict'),label,target=target,claim_type=typ,claim_value=c,is_oracle=False)
                add('CLAIM_ORACLE',table+claim,dict(kind='verdict'),label,media=False,target=target,claim_type=typ,claim_value=c,is_oracle=True)
        if level=='L4' and action is not None:
            # Transition control supplies verified PRE and operation, never a computed POST field.
            add('TEXT_STATE_UPDATE',f'Explicit PRE fact: category "{action["target"]}" has {values["PRE"]} instances.\n'+intervention+
                '\nCompute its count in POST after this single intervention.',oracleschema,values['POST'],media=False,target='POST',is_oracle=True)
        status='REFERENCE_FRAME_UNCLEAR' if binary else 'PENDING_REVIEW'
        card=dict(group_id=gid,world_id=g['world_id'],cluster_id=g['cluster_id'],level=level,state_dimension=dim,stratum=stratum,
            source=g['source'],operator=g['operator'],review_status=status,old_alias_to_a1_key=names,values=values,
            media=g['media'],query=query,context=context,intervention=intervention,action_expected=action,
            issues=checks,source_truth_sha256=digest(t),source_proof_sha256=digest(proof),partition='EXPOSED_DISCOVERY_REPAIR_NOT_CONFIRMATION')
        panel.append(card); proofs.append(dict(group_id=gid,source_pair=source,source_truth=t,new_replay=proof))
        review.append(dict(group_id=gid,world_id=g['world_id'],level=level,state_dimension=dim,stratum=stratum,review_status=status,
            automatic_source_replay='PASS',actual_processor_check='PENDING_RENDER',pre_visible='PENDING_REVIEW',
            intervention_present='PASS' if level=='L4' else 'NOT_APPLICABLE',target_unique='PENDING_REVIEW',
            reference_frame='UNRESOLVED_IMAGE_AXIS_MAPPING' if binary else 'COUNT_SCOPE_EXPLICIT_REVIEW_VISIBILITY',
            state_key_semantics='PASS',category_scope='PENDING_REVIEW',media_order='PENDING_RENDER',
            reviewer_name='',reviewed_at='',notes='; '.join(checks),human_review_completed=False))
    assert len({r['request_id'] for r in drafts})==len(drafts)
    # Target flip differs only in TARGET; SHAM only in the non-target variable name.
    for g in groups:
        rr=[r for r in drafts if r['group_id']==g['group_id']]
        oo=[r for r in rr if r['condition'] in ['MULTI_STATE_TARGET_SELECT','TARGET_FLIP']]
        assert len(oo)==2
        normalized=[r['payload']['text'].replace('TARGET = '+r['target'],'TARGET = <TARGET>') for r in oo]
        if normalized[0]!=normalized[1]: raise ValueError('TARGET_FLIP_NOT_MATCHED')
        for o in oo:
            s=next(r for r in rr if r['condition']=='SHAM' and r['target']==o['target'])
            non_target_line=next(line for line in s['payload']['text'].splitlines() if ': UNRELATED_REGISTER =' in line)
            if s['payload']['text'].replace(non_target_line,non_target_line.replace(': UNRELATED_REGISTER =',': QUERY_VALUE ='))!=o['payload']['text']:
                raise ValueError('SHAM_NOT_MATCHED')
    save(root/'review/draft_requests.jsonl',drafts,'jsonl',frozen=True)
    save(root/'review/draft_gold.jsonl',gold,'jsonl',frozen=True)
    save(root/'review/candidate_panel.jsonl',panel,'jsonl',frozen=True)
    save(root/'review/source_replays.jsonl',proofs,'jsonl',frozen=True)
    csvsave(root/'derived_input_review.csv',review)
    save(root/'review/design_inventory.json',dict(status='DRAFTS_FOR_REVIEW_NOT_CORE_FREEZE',worlds=len(panel),
        by_stratum=dict(Counter(p['stratum'] for p in panel)),requests_per_model=len(drafts),conditions=dict(Counter(r['condition'] for r in drafts)),
        csv_sha256=sha(cfg['phase_a_csv']),csv_fields_used=['group_id','level','state_dimension'],
        candidate_ids_selected_from_old_manifest_not_predictions=True,models=cfg['models'],verified_worlds=0,
        draft_input_sha256=sha(root/'review/draft_requests.jsonl'),draft_gold_sha256=sha(root/'review/draft_gold.jsonl')),frozen=True)
    print(json.dumps(load(root/'review/design_inventory.json')))

if __name__=='__main__': main()
