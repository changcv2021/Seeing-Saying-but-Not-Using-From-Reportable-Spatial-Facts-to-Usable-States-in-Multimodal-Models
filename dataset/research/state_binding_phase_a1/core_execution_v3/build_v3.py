"""Trusted construction only. All new source-dependent requests are REVIEW DRAFTS."""
import collections
import re
from v3common import *
from contracts_v3 import *


def request(c, group, condition, text, schema, media, **meta):
    r = dict(run_id=c['run_id'], protocol_version=c['protocol_version'], group_id=group,
             condition=condition, schema=schema, models=c['models'],
             payload=dict(system=SYSTEM,text=text,media=media), **meta)
    r['request_id'] = 'a1c3_' + digest(r)[:28]
    return r


def build_core(c, panels, groups, old_requests, replays):
    requests, gold, cards, matches, eligibility, aliases = [], [], [], [], [], []
    for panel in panels:
        gid = panel['group_id']; g = groups[gid]; proof = replays[gid]
        assert panel['cluster_id'] == g['cluster_id'] and panel['world_id'] == g['world_id']
        assert digest(proof['source_truth']) == panel['source_truth_sha256']
        assert digest(proof['new_replay']) == panel['source_proof_sha256']
        aliases.append(dict(group_id=gid,underlying_world_id=g['cluster_id'],source_world_id=g['world_id'],
                            mapping_source='EXPLICIT_PHASE_A_GROUP_AND_SOURCE_TRUTH', source_truth_sha256=panel['source_truth_sha256']))
        card = dict(panel, underlying_world_id=g['cluster_id'], received_review_status=panel['review_status'])
        if panel['stratum'] == 'L4_BINARY_RELATION_SECONDARY':
            card.update(review_status='DEFERRED_REFERENCE_FRAME', execution_role='DEFERRED_REFERENCE_FRAME')
            cards.append(card)
            continue
        card['review_status'] = 'PENDING_REVIEW'
        card['execution_role'] = 'PRIMARY_IF_VERIFIED' if g['original_level']=='L4' else 'CONTROL_IF_VERIFIED'
        level = g['original_level']; media = g['media']; is_l4 = level == 'L4'
        vals = panel['values'] if is_l4 else {'OBJECT_A':panel['values']['OBJECT_1'],'OBJECT_B':panel['values']['OBJECT_2']}
        keys = ['PRE','POST'] if is_l4 else ['OBJECT_A','OBJECT_B']
        assert all(type(v) is int and v>=0 for v in vals.values()) and len(set(vals.values()))==2
        order = keys if int(digest([c['seed'],gid])[:8],16)%2==0 else keys[::-1]
        target_key = 'TARGET_STATE' if is_l4 else 'TARGET_OBJECT'
        roles = '; '.join(f'Image {i+1}: {m["role"]}' for i,m in enumerate(media))
        if is_l4:
            action = panel['action_expected']; category = action['target']
            assert action['operation'] in ['ADD','REMOVE'] and type(action['amount']) is int
            delta = action['amount'] * (1 if action['operation']=='ADD' else -1)
            assert vals['PRE']+delta == vals['POST']
            scope = 'the whole scene represented by the supplied views, not only the first camera crop'
            local = ('The supplied media depict the initial scene, before any hypothetical intervention.\n'
                     f'Query category: {category}\nCounting scope: {scope}.\nReference image / view roles: {roles}.\n'
                     'Count distinct instances within this scope. Do not count the same instance again merely because it appears in another view.')
            action_text = g['intervention']
            full = local + '\nHypothetical intervention: ' + action_text + '\nPRE denotes the initial scene.\nPOST denotes the result of applying this intervention exactly once within the stated scope.\nNo supplied image is a post-intervention image.'
            query = f'the count of category "{category}" within {scope}'
        else:
            action = None; category = {}; scope = 'visible instances in image 1, the designated reference image, not the support images'
            definitions = []
            for name,s in zip(keys,g['states']):
                found = re.findall(r'"([^"]+)"', s['definition'])
                if len(found)!=1: raise ValueError('CATEGORY_DEFINITION_REQUIRES_REVIEW:'+gid)
                category[name] = found[0]
                definitions.append(name + ': ' + s['definition'])
            local = ('Counting scope: '+scope+'.\nReference image / view roles: '+roles+'.\n'
                     'Do not sum counts across views. The OBJECT names identify categories, not time states.\n'+'\n'.join(definitions))
            full = local; query = 'the visible reference-image count of the category defined by each OBJECT record. ' + '; '.join(definitions)
        parent_pool = sorted([r for r in old_requests if r['group_id']==gid],key=lambda r:r['request_id'])
        assert parent_pool
        lookup = {}
        def add(condition, body, sch, expected, media_on=False, target='', variant='', claim_type='', claim_value=None,
                provenance='SOURCE_GROUNDED_DRAFT', witnesses=None, condition_eligible=True, reason='PENDING_WORLD_AND_CONDITION_REVIEW'):
            parent_map={'SELECT_MEDIA':'POST_VALUE','ORACLE_MULTI':'MULTI_STATE_TARGET_SELECT',
                        'ORACLE_SINGLE':'SINGLE_STATE_LOOKUP','ORACLE_SHAM':'SHAM','JOINT_OBJECT':'JOINT_OBJECT'}
            parent = next((r for r in parent_pool if r['condition']==parent_map.get(condition,condition)),parent_pool[0])
            r = request(c,gid,condition,body,sch,media if media_on else [],stage='core',level=level,
                        state_dimension=g['state_dimension'],underlying_world_id=g['cluster_id'],world_id=g['world_id'],
                        parent_request_id=parent['request_id'],target=target,variant=variant)
            requests.append(r); lookup[(condition,target,variant)] = r
            gold.append(dict(request_id=r['request_id'],group_id=gid,underlying_world_id=g['cluster_id'],schema=sch,
                             expected=expected,source_values=vals,claim_type=claim_type,claim_value=claim_value,
                             provenance=provenance,witnesses=witnesses,condition_eligible=condition_eligible,
                             condition_eligibility_reason=reason,source_truth_sha256=panel['source_truth_sha256'],
                             source_proof_sha256=panel['source_proof_sha256'],action_target_scope='CATEGORY_ONLY' if sch['kind']=='action' else None))
            eligibility.append(dict(request_id=r['request_id'],group_id=gid,condition=condition,target=target,variant=variant,
                                    source_rule_eligible=condition_eligible,human_condition_eligible='PENDING_REVIEW',reason=reason,
                                    provenance=provenance))
            return r
        def match(name, base, control, target='', provenance='MATCHED_INFORMATION_CONDITION'):
            m = dict(group_id=gid,underlying_world_id=g['cluster_id'],target=target,comparison=name,
                     base_request_id=base['request_id'],control_request_id=control['request_id'],provenance=provenance)
            m['match_id'] = 'm3_'+digest(m)[:24]; matches.append(m)
        if is_l4:
            add('PRE_VALUE',local+'\nWhat is the count in the initial scene?\n'+SCALAR,VALUE_SCHEMA,vals['PRE'],True,target='PRE')
            add('ACTION_PARSE',local+'\nIntervention: '+action_text+'\n'+ACTION,ACTION_SCHEMA,action,True)
            add('POST_VALUE',full+'\nWhat is the count after applying the stated intervention once?\n'+SCALAR,VALUE_SCHEMA,vals['POST'],True,target='POST')
            m = action['amount']; pre1 = 0 if action['operation']=='ADD' else m
            w = [dict(PRE=n,operation=action['operation'],amount=m,POST=n+delta) for n in [pre1,pre1+1]]
            assert w[0]['POST']!=w[1]['POST'] and min(x['POST'] for x in w)>=0
            body = (f'No images or scene counts are supplied. Query category: {category}. Counting scope: the whole scene.\n'
                    f'Hypothetical intervention: {action_text}\nWhat is the count after applying the stated intervention once?\n'+SCALAR)
            add('POST_NO_MEDIA',body,VALUE_SCHEMA,None,target='POST',provenance='RESTRICTED_EVIDENCE_COUNT_TRANSITION',
                witnesses=w,reason='REVIEW_ACTION_ONLY_TWO_COMPLETIONS_REQUIRED_NO_ALL_REMOVAL_RULE_ASSUMED')
            body = (f'This is a text-only state-update task. Query: count of category "{category}". Counting scope: the whole scene.\n'
                    f'Initial facts: the PRE count of this category is {vals["PRE"]}.\nApply exactly once: {action_text}\n'
                    'What is the resulting query count?\n'+SCALAR)
            add('TEXT_STATE_UPDATE',body,VALUE_SCHEMA,vals['POST'],target='POST',provenance='ORACLE_PRE_ONLY_AND_SOURCE_ACTION')
        else:
            for key in keys:
                add('OBJECT_VALUE',local+'\nWhat is the reference-image count of category "'+category[key]+'"?\n'+SCALAR,
                    VALUE_SCHEMA,vals[key],True,target=key)
        jcond = 'JOINT_STATE' if is_l4 else 'JOINT_OBJECT'
        for i,keyorder in enumerate([keys,keys[::-1]]):
            add(jcond,full+'\n'+joint_text(keyorder),dict(kind='joint',domain='count',nullable=True,keys=keyorder),vals,True,variant='forward' if i==0 else 'reverse')
        match('JOINT_REPORT_ORDER',lookup[jcond,'','forward'],lookup[jcond,'','reverse'])
        for target in keys:
            scond = 'SELECT_MEDIA' if is_l4 else 'SELECT_MEDIA_OBJECT'
            tail = f'\n{target_key}: {target}\nWhat is the count of the query category in {target_key}?\n'+SCALAR
            add(scond,full+tail,VALUE_SCHEMA,vals[target],True,target=target)
        scond = 'SELECT_MEDIA' if is_l4 else 'SELECT_MEDIA_OBJECT'
        match('MEDIA_TARGET_FLIP',lookup[scond,keys[0],''],lookup[scond,keys[1],''])
        third = max(vals.values())+1
        header = table_header(query)
        for target in keys:
            other = next(k for k in keys if k!=target)
            table = header+'\n'.join(f'{k}: query_count = {vals[k]}' for k in order)
            sham = header+'\n'.join(f'{k}: '+('query_count' if k==target else 'unrelated_register')+f' = {vals[k]}' for k in order)
            tail = f'\n{target_key}: {target}\nReturn query_count for {target_key}.\n'+SCALAR
            add('ORACLE_SINGLE',header+f'{target}: query_count = {vals[target]}'+tail,VALUE_SCHEMA,vals[target],target=target,provenance='EXPLICIT_SOURCE_TABLE')
            add('ORACLE_MULTI',table+tail,VALUE_SCHEMA,vals[target],target=target,provenance='EXPLICIT_SOURCE_TABLE')
            add('ORACLE_SHAM',sham+tail,VALUE_SCHEMA,vals[target],target=target,provenance='EXPLICIT_SOURCE_TABLE_WITH_UNRELATED_REGISTER')
            match('SINGLE_TO_MULTI',lookup['ORACLE_SINGLE',target,''],lookup['ORACLE_MULTI',target,''],target)
            match('MULTI_TO_SHAM',lookup['ORACLE_MULTI',target,''],lookup['ORACLE_SHAM',target,''],target)
            match('MEDIA_TO_ORACLE_MULTI',lookup[scond,target,''],lookup['ORACLE_MULTI',target,''],target)
            if not is_l4: continue
            reverse = header+'\n'.join(f'{k}: query_count = {vals[k]}' for k in order[::-1])
            add('ORACLE_MULTI_ORDER',reverse+tail,VALUE_SCHEMA,vals[target],target=target,provenance='EXPLICIT_SOURCE_TABLE')
            match('ORACLE_ROW_ORDER',lookup['ORACLE_MULTI',target,''],lookup['ORACLE_MULTI_ORDER',target,''],target)
            for cond,nonvar,base in [('SYMBOLIC_D2_MULTI','query_count','ORACLE_MULTI'),('SYMBOLIC_D2_SHAM','unrelated_register','ORACLE_SHAM')]:
                modified = header+'\n'.join(f'{k}: query_count = {vals[k]}' if k==target else f'{k}: {nonvar} = {third}' for k in order)
                add(cond,modified+tail,VALUE_SCHEMA,vals[target],target=target,provenance='SYMBOLIC_CONTROL_ONLY')
                match(base+'_D1_TO_D2',lookup[base,target,''],lookup[cond,target,''],target,'SYMBOLIC_CONTROL_ONLY')
            missing = header+f'{other}: query_count = {vals[other]}'
            witnesses = [dict(table={other:vals[other],target:n}) for n in [0,1]]
            add('ORACLE_MISSING_VALUE',missing+tail,VALUE_SCHEMA,None,target=target,provenance='RESTRICTED_EVIDENCE_NOT_HIDDEN_SOURCE_VALUE',witnesses=witnesses)
            for claim in [vals[keys[0]],vals[keys[1]],third]:
                typ = 'target_match' if claim==vals[target] else 'other_state' if claim==vals[other] else 'neither_state'
                claimtail = f'\n{target_key}: {target}\nCandidate statement: the query category count in {target_key} is exactly {claim}.\n'+LABEL
                for cond,context,on,prov in [('CLAIM_MEDIA',full,True,'SOURCE_GROUNDED_DRAFT'),('CLAIM_ORACLE',table,False,'EXPLICIT_SOURCE_TABLE')]:
                    add(cond,context+claimtail,dict(kind='verdict'),'SUPPORTED' if claim==vals[target] else 'CONTRADICTORY',on,
                        target=target,variant=str(claim),claim_type=typ,claim_value=claim,provenance=prov)
                match('CLAIM_MEDIA_TO_ORACLE',lookup['CLAIM_MEDIA',target,str(claim)],lookup['CLAIM_ORACLE',target,str(claim)],target)
            claim = vals[target]
            claimtail = f'\n{target_key}: {target}\nCandidate statement: the query category count in {target_key} is exactly {claim}.\n'+LABEL
            add('CLAIM_ORACLE_MISSING',missing+claimtail,dict(kind='verdict'),'UNKNOWN',target=target,claim_value=claim,
                provenance='RESTRICTED_EVIDENCE_TWO_SATISFYING_COMPLETIONS',
                witnesses=[dict(table={other:vals[other],target:n},claim_true=n==claim) for n in [claim,claim+1]])
        match('ORACLE_TARGET_FLIP',lookup['ORACLE_MULTI',keys[0],''],lookup['ORACLE_MULTI',keys[1],''])
        this = [r for r in requests if r['group_id']==gid]
        assert len(this)==(37 if is_l4 else 12)
        card.update(values=vals,category=category,count_scope=scope,local_pre_context=local,full_media_context=full,
                    request_ids=[r['request_id'] for r in this],draft_request_bundle_sha256=digest(this),
                    action_target_scope='CATEGORY_ONLY' if is_l4 else 'NOT_APPLICABLE',
                    entity_grounding='NOT_MEASURED',post_no_media_review_required=is_l4)
        cards.append(card)
    assert len(requests)==319 and len({r['request_id'] for r in requests})==319
    return requests,gold,cards,matches,eligibility,aliases


def build_precore(c, setup_groups, discovery_groups, setup_requests):
    bridge = import_file(Path(c['package'])/'scripts/build_semantic_bridge.py','provided_bridge')
    req,gold = bridge.build_records()
    result,truth = [],[]
    for r,g in zip(req,gold):
        new = request(c,r['synthetic_block_id'],r['condition'],r['payload']['text'],r['schema'],[],
                      stage='semantic_bridge',level='SETUP_SEMANTIC_DIAGNOSTIC',underlying_world_id=r['synthetic_block_id'],
                      parent_request_id=r['request_id'],target=r['metadata'].get('target_name',''),variant=r['metadata'].get('naming',''))
        # Preserve the supplied bridge's exact system and payload, not the media system template.
        new['payload'] = r['payload']; new['request_id']='a1c3_'+digest({k:v for k,v in new.items() if k!='request_id'})[:28]
        result.append(new)
        truth.append(dict(g,request_id=new['request_id'],group_id=r['synthetic_block_id'],metadata=r['metadata'],condition_eligible=True))
    seen = {g['cluster_id'] for g in discovery_groups}
    usable = sorted([g for g in setup_groups if g['partition']=='setup' and g['original_level']=='L4' and not g['domain']['binary_degenerate'] and g['media']],key=lambda g:g['group_id'])
    assert usable and all(g['cluster_id'] not in seen for g in usable)
    g = usable[0]; gid=g['group_id']
    parents = sorted([r['request_id'] for r in setup_requests if r.get('group_id')==gid])
    assert parents, 'SETUP_PARENT_REQUEST_REQUIRED'
    # Independent, already exposed setup media only. No correctness gate or scientific inclusion.
    ctx = ('All supplied images depict PRE. Count scene instances once across views. Query: '+g['fact_query']+
           '\nHypothetical intervention: '+g['intervention']+'\nPRE is before the intervention. POST is after applying it once.')
    smoke = [('SMOKE_VALUE',ctx+'\nReturn the PRE count.\n'+SCALAR,VALUE_SCHEMA,'PRE','')]
    for target in ['PRE','POST']:
        smoke.append(('SMOKE_SELECT_MEDIA',ctx+f'\nTARGET_STATE: {target}\nReturn the target count.\n'+SCALAR,VALUE_SCHEMA,target,''))
    for variant,keys in [('forward',['PRE','POST']),('reverse',['POST','PRE'])]:
        smoke.append(('SMOKE_JOINT',ctx+'\n'+joint_text(keys),dict(kind='joint',domain='count',nullable=True,keys=keys),'',variant))
    smoke.append(('SMOKE_VERDICT',ctx+'\nTARGET_STATE: PRE\nCandidate statement: the queried count is exactly 0.\n'+LABEL,dict(kind='verdict'),'PRE',''))
    for cond,text,sch,target,variant in smoke:
        r=request(c,gid,cond,text,sch,g['media'],stage='smoke',level='SETUP_MEDIA_ENGINEERING_ONLY',
                  underlying_world_id=g['cluster_id'],parent_request_id=parents[0],target=target,variant=variant)
        result.append(r); truth.append(dict(request_id=r['request_id'],schema=sch,expected=None,condition_eligible=False,reason='ENGINEERING_PARSE_ONLY_NO_ACCURACY'))
    assert len(result)==82
    result.sort(key=lambda r: (r['stage']!='smoke', r['request_id']))
    return result,truth,dict(setup_group_id=gid,underlying_world_id=g['cluster_id'],not_in_discovery=True,
                            selection_rule='LEXICOGRAPHIC_FIRST_SETUP_L4_COUNT_WITH_MEDIA_NO_MODEL_RESPONSES_READ',
                            source_group=g,smoke_requests=6,semantic_requests=76)


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('PLANNED: new drafts 319 and fixed bridge/smoke 82 per model; core blocked on review'); return
    compute()
    old=Path(c['format_v2_root']); pa=Path(c['phase_a_root'])
    panels=list(rows(old/'review/candidate_panel.jsonl')); groups={g['group_id']:g for g in rows(pa/'manifest/discovery/state_group_manifest.jsonl')}
    previous=list(rows(old/'review/draft_requests.jsonl')); replays={g['group_id']:g for g in rows(old/'review/source_replays.jsonl')}
    req,gold,cards,matches,elig,aliases=build_core(c,panels,groups,previous,replays)
    setup_groups=list(rows(pa/'manifest/setup_contract_v24/state_group_manifest.jsonl'))
    setup_requests=list(rows(pa/'inputs/setup_contract_v24/requests.jsonl'))
    precore,pre_gold,setup_source=build_precore(c,setup_groups,list(groups.values()),setup_requests)
    save(root/'inputs/precore/requests.jsonl',precore,'jsonl')
    save(root/'private_gold/precore.jsonl',pre_gold,'jsonl')
    save(root/'review/draft_requests.jsonl',req,'jsonl')
    save(root/'private_gold/core_draft.jsonl',gold,'jsonl')
    save(root/'review/candidate_panel.jsonl',cards,'jsonl')
    save(root/'review/source_replays.jsonl',list(replays.values()),'jsonl')
    save(root/'review/matched_controls.jsonl',matches,'jsonl')
    csvsave(root/'review/condition_eligibility.csv',elig)
    csvsave(root/'world_alias_map.csv',aliases)
    save(root/'manifest/independent_smoke_source.json',setup_source)
    for p in (root/'private_gold').iterdir(): p.chmod(0o600)
    save(root/'manifest/build_inventory.json',dict(status='DRAFTS_NOT_CORE_EXECUTION',candidate_worlds=16,
        l4_count_worlds=7,l1_worlds=5,deferred_binary_worlds=4,core_drafts_per_model=len(req),
        semantic_bridge_per_model=76,smoke_per_model=6,new_model_generations=0,
        core_conditions=dict(collections.Counter(r['condition'] for r in req)),
        source_files=[entry(old/'review/candidate_panel.jsonl'),entry(old/'review/source_replays.jsonl'),
                      entry(pa/'manifest/discovery/state_group_manifest.jsonl')]))
    print(json.dumps(load(root/'manifest/build_inventory.json')))


if __name__=='__main__': main()
