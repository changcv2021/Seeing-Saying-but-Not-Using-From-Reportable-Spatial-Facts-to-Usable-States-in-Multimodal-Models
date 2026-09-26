"""Freeze answer-blind requests and physically separate oracle/evaluation records."""
import itertools
from base import *
from mine import select_stratified

VERSION='phase_a_state_index_v2_3'
SYSTEM='Follow the specified evidence scope and output contract. A statement to evaluate is not evidence that it is true. Return concise JSON only, without Markdown. Your complete response must not exceed 512 generated tokens.'
VERDICT='SUPPORTED: evidence establishes the statement in the TARGET state. CONTRADICTORY: evidence establishes its negation or an incompatible fact in that state. UNKNOWN: neither is established. Return only {"label":"SUPPORTED|CONTRADICTORY|UNKNOWN"}.'
VALUE='Return only {"status":"VALUE","value":<value>} or {"status":"UNDETERMINED","value":null}. Do not report an explanation or values for other states.'

def local_action_arguments(params):
    # The source DSL also contains computed post_predicate/count_deltas.
    # G_LOCAL must give premises and operation arguments, not the derived answer.
    allowed={'target_id','target_a_id','target_b_id','anchor_id','category','old_category','new_category','new_entity_id','quantity','axis','reference_frame'}
    return {k:v for k,v in params.items() if k in allowed}

def public(g):
    allowed=['group_id','cluster_id','world_id','parent_ids','source','original_level','l4_origin','native_subtype','dependency_type','operator','diagnostic_design','state_dimension','provenance_type','media','media_context','frame','scope','intervention','states','fact_query','domain','claims','partition','review_status']
    return {k:g.get(k) for k in allowed}

def state_context(g,states=None):
    prefix='All media depict the initial scene before any hypothetical intervention.\n' if g['state_dimension']=='PRE_POST' else ''
    return prefix+g.get('media_context','')+f"\nDeclared reference frame: {g['frame']}. Observation scope: {g['scope']}.\nSTATE DEFINITIONS\n"+'\n'.join(s['alias']+': '+s['definition'] for s in (states or g['states']))

def construct(cfg,root,stage,mechanism_cap=None,coverage_cap=None,controls_cap=None,interfaces_cap=None,persist=True):
    version=cfg.get('prompt_version',VERSION); strict_contract=version=='phase_a_state_index_v2_4'
    if stage.startswith('setup'):
        groups=list(rows(root/'manifest/setup_groups.private.jsonl'))
        coverage=list(rows(root/'manifest/setup_coverage.jsonl')); unknown=[]
        control_groups=groups; interface_groups=groups[:1]
    else:
        allgroups=list(rows(root/'manifest/prospective_mechanism.private.jsonl'))
        groups=select_stratified(allgroups,mechanism_cap,cfg['seed'],stratum=lambda g:(g['original_level'],g.get('l4_origin') or '',g['domain']['type']))
        coverage=select_stratified(list(rows(root/'manifest/prospective_coverage.jsonl')),coverage_cap,cfg['seed'],stratum=lambda g:(g['original_level'],g['source']))
        unknown=list(rows(root/'manifest/prospective_unknown.jsonl'))
        control_groups=select_stratified(groups,controls_cap,cfg['seed']+2,stratum=lambda g:(g['original_level'],g['domain']['type']))
        interface_groups=select_stratified(control_groups,interfaces_cap,cfg['seed']+3,stratum=lambda g:(g['original_level'],g['domain']['type']))
    control_ids={g['group_id'] for g in control_groups}; interface_ids={g['group_id'] for g in interface_groups}
    originals=unique(rows(root/'manifest/original_gold.dev.jsonl'),'sample_id')
    l4pairs=unique(rows(Path(cfg['project'])/'l4/v3_3/release/pairs.l4_three_part_v3.jsonl'),'pair_id')
    reqs=[]; gg=[]; seen=set()
    def add(g,condition,text,*,target=None,claim=None,variant='base',outcome=None,media=True,oracle=False,models=None,extra=None):
        key=dict(group=g['group_id'],condition=condition,target=target,claim=claim['claim_key'] if claim else None,variant=variant)
        payload=dict(system=SYSTEM,text=text,media=g['media'] if media else [])
        rid='req_'+digest([version,key,payload,cfg['max_new_tokens'],cfg['seed']])[:32]
        if rid in seen: raise ValueError('DUPLICATE_REQUEST:'+rid)
        seen.add(rid)
        rec=dict(request_id=rid,group_id=g['group_id'],cluster_id=g['cluster_id'],parent_ids=g.get('parent_ids',[]),condition=condition,target=target,
            claim_id=claim['claim_key'] if claim else None,variant=variant,phase=stage,payload=payload,source=g['source'],level=g['original_level'],
            state_dimension=g.get('state_dimension'),diagnostic_design='ORACLE_TABLE_SWITCH' if oracle else g.get('diagnostic_design'),
            provenance_type=('SYMBOLIC_CONTROL_ONLY' if condition=='G_DISTRACTOR_SWAP' else 'ORACLE_FROM_VERIFIED_STATES') if oracle else g.get('provenance_type','REUSED_NATIVE'),
            is_oracle=oracle,models=models or cfg['models'],prompt_version=version,max_new_tokens=cfg['max_new_tokens'],**(extra or {}))
        reqs.append(rec); gg.append(dict(request_id=rid,group_id=g['group_id'],cluster_id=g['cluster_id'],**(outcome or {})))
    # Original tasks have unique sample IDs even if also included in mechanism panel.
    source_requests={}
    for item in coverage:
        for r in item['inputs']: source_requests[r['sample_id']]=(r,item)
    for g in groups:
        for r in g['original_inputs']: source_requests[r['sample_id']]=(r,g)
    for r in unknown: source_requests[r['sample_id']]=(r,r)
    for sid,(r,info) in sorted(source_requests.items()):
        if r['split']!='dev': raise ValueError('OFFICIAL_TEST_OR_TRAIN_REQUEST_FORBIDDEN')
        obj=dict(group_id='orig_'+r['pair_id'] if r.get('pair_id') else 'orig_'+sid,cluster_id=info['cluster_id'],parent_ids=[r.get('pair_id')],
            source=r['dataset'],original_level=r['level'],media=r['media'],state_dimension='ORIGINAL',diagnostic_design='ORIGINAL_TASK',provenance_type='REUSED_NATIVE')
        # Actual messages are rendered by the unchanged existing original-task adapter.
        add(obj,'D_ORIG',r['claim_text'],variant=sid,outcome=dict(kind='verdict',label=originals[sid]['gold'],sample_id=sid,pair_id=r.get('pair_id')),
            extra=dict(original_input={k:r[k] for k in ['claim_text','component','dataset','level','media','pair_id','sample_id','split','track','media_context','intervention_text'] if k in r}))
    for private in groups:
        g=public(private); truth=private['private']; states=g['states']; values=truth['values']; aliases=[s['alias'] for s in states]
        context=state_context(g)
        if strict_contract:
            fmt='A nonnegative JSON integer, not a quoted string, list, or object.' if g['domain']['type']=='nonnegative_integer' else 'One JSON string from '+json.dumps(g['domain']['values'])+', not a list or object.'
            fmt+=' If status is UNDETERMINED, value must be null. Do not output the format description as a value.'
        else: fmt=json.dumps(g['domain'],ensure_ascii=False)
        query='FACT QUERY: '+g['fact_query']+'\nVALUE FORMAT: '+fmt
        for state in states:
            target=state['alias']; outcome=dict(kind='value',value=values[target],gold_by_state=values,target=target,domain=g['domain'])
            add(g,'FACT_SEPARATE',state_context(g,[state])+'\n'+query+'\n'+VALUE,target=target,outcome=outcome)
            add(g,'SELECT_VALUE',context+'\nTARGET STATE: '+target+'\n'+query+'\n'+VALUE,target=target,outcome=outcome)
            for claim in g['claims']:
                label=truth['claim_gold'][claim['claim_key']][target]
                add(g,'STATE_VERDICT',context+'\nTARGET STATE: '+target+'\nSTATEMENT: '+claim['text']+'\n'+VERDICT,target=target,claim=claim,
                    outcome=dict(kind='verdict',label=label,claim_value=claim['value'],invariant=claim['invariant'],target=target,gold_by_state=values))
        joint=context+'\n'+query+'\nREPORT ORDER: '+', '.join(aliases)+'.\nFor each listed state, report the query value in that state. Return one JSON object keyed by these state aliases; each entry must have status VALUE or UNDETERMINED and value. Do not add other fields.'
        if strict_contract: joint+='\nEach state entry is an object with exactly status and value. VALUE requires a scalar value of the type above; UNDETERMINED requires value null. Never report a numerical placeholder for an undetermined value.'
        joint_gold=dict(kind='joint',gold_by_state=values,domain=g['domain'])
        if strict_contract: joint_gold['require_null_for_undetermined']=True
        add(g,'FACT_JOINT',joint,outcome=joint_gold)
        if g['state_dimension']=='PRE_POST':
            parent=l4pairs[g['parent_ids'][0]]
            params=parent.get('intervention',{}).get('parameters',{})
            graph=parent['supported_claim']['graph']
            terms=[truth['action']['target']]
            if g['operator']=='REPLACE_AND_RECOUNT': terms=[params['old_category'],params['new_category']]
            elif g['operator']=='SWAP_POSITIONS': terms=[graph['subject_label'],graph['object_label']]
            action_source=dict(parent_id=parent['pair_id'],parameters=params,rule='EXACT_DSL_OR_NATIVE_ACTION_CATEGORY; lexical target check is auxiliary, not semantic action comprehension')
            canonical_op={'REMOVE_AND_RECOUNT':'REMOVE','REMOVAL':'REMOVE','ADD_AND_RECOUNT':'ADD','ADDITION':'ADD','REPLACE_AND_RECOUNT':'REPLACE','REPLACEMENT':'REPLACE','MOVE_TO_OPPOSITE_SIDE':'MOVE','MOVEMENT':'MOVE','SWAP_POSITIONS':'SWAP'}.get(g['operator'])
            if canonical_op:
                add(g,'ACTION_PARSE','VISIBLE INTERVENTION: '+g['intervention']+f"\nDeclared scope: {g['scope']}.\nReport its operation, target description, and scope. Do not compute a final state. Return {{\"status\":\"RESOLVED|UNDETERMINED\",\"operation\":\"REMOVE|ADD|REPLACE|MOVE|SWAP\",\"target\":\"description\",\"scope\":\"scope\"}}.",
                    outcome=dict(kind='action',operation=canonical_op,target_terms=terms,scope=g['scope'],source=action_source))
        if g['group_id'] not in control_ids: continue
        # Every table is a separate controlled text task. SHAM's unrelated register is not claimed to be a real scene object.
        def table_text(mode,target,rename=None,reverse=False,distractor=None):
            ren=rename or {s:s for s in aliases}; table=[]
            order=aliases[::-1] if reverse else aliases
            for s in order:
                if mode=='TARGET' and s!=target: continue
                record_scope='UNRELATED_REGISTER' if mode=='SHAM' and s!=target else 'QUERY_VARIABLE'
                vv=values[s] if distractor is None or s==target else distractor
                table.append(dict(state=ren[s],variable=record_scope,value=vv))
            return 'The following table defines the available facts for this controlled text task. QUERY_VARIABLE denotes the FACT QUERY; UNRELATED_REGISTER does not.\n'+json.dumps(table,ensure_ascii=False)+'\nTARGET STATE: '+ren[target]+'\n'+query+'\n', table
        for target in aliases:
            other=next(s for s in aliases if s!=target)
            outcome=dict(kind='value',value=values[target],target=target,gold_by_state=values,domain=g['domain'],distractor_value=values[other])
            for mode in ['MULTI','SHAM','TARGET']:
                tt,tab=table_text(mode,target)
                add(g,'G_'+mode+'_VALUE',tt+VALUE,target=target,outcome=outcome,media=False,oracle=True,extra=dict(oracle_table=tab))
                if mode in ['MULTI','SHAM'] or g['group_id'] in interface_ids:
                    for claim in g['claims'][:2]:
                        add(g,'G_'+mode+'_VERDICT',tt+'STATEMENT: '+claim['text']+'\n'+VERDICT,target=target,claim=claim,media=False,oracle=True,
                            outcome=dict(kind='verdict',label=truth['claim_gold'][claim['claim_key']][target],claim_value=claim['value'],target=target),extra=dict(oracle_table=tab),
                            models=cfg['models'] if g['group_id'] in interface_ids else cfg['models'][:2])
            if truth['local_eligibility']=='PASS':
                # Give all verified preconditions, not just the queried category's count.
                premise=truth['local_premise_text']+'\nVerified initial-state fact records: '+json.dumps(truth['pre_facts'],ensure_ascii=False)
                if g['state_dimension']=='PRE_POST': premise+='\nAction argument identifiers (not post-state facts): '+json.dumps(local_action_arguments(params),ensure_ascii=False)
                add(g,'G_LOCAL','KNOWN LOCAL PREMISES:\n'+premise+'\n'+context+'\nTARGET STATE: '+target+'\n'+query+'\n'+VALUE,target=target,
                    media=False,oracle=True,outcome=outcome,models=cfg['models'] if g['group_id'] in interface_ids else cfg['models'][:2])
        if g['group_id'] not in interface_ids: continue
        rename=dict(zip(aliases,['STATE_K','STATE_M']))
        for target in aliases:
            for mode in ['MULTI','SHAM']:
                tt,tab=table_text(mode,target,rename=rename,reverse=True)
                add(g,'G_'+mode+'_VALUE',tt+VALUE,target=target,variant='renamed_reversed',outcome=dict(kind='value',value=values[target],target=target,gold_by_state=values,domain=g['domain'],distractor_value=values[next(s for s in aliases if s!=target)]),
                    media=False,oracle=True,extra=dict(oracle_table=tab,alias_map=rename))
        # Both label mappings are predetermined, never chosen after observing answers.
        order=list(itertools.permutations(LABELS))[int(stable_rank(cfg['seed'],g['group_id'])[:8],16)%6]
        mapping=dict(zip('ABC',order)); semantic={'supported by evidence':'SUPPORTED','refuted by evidence':'CONTRADICTORY','insufficient evidence':'UNKNOWN'}
        for state in states:
            target=state['alias']
            for claim in g['claims'][:2]:
                tt=context+'\nTARGET STATE: '+target+'\nSTATEMENT: '+claim['text']+'\n'+VERDICT.split('Return only')[0]
                for variant,field,mp in [('ABC','label_code',mapping),('semantic','semantic_label',semantic)]:
                    add(g,'LABEL_INTERFACE_CONTROL',tt+'\nOUTPUT MAP: '+json.dumps(mp)+f'\nReturn only a JSON object with the key "{field}" and one code/key from this mapping.',target=target,claim=claim,variant=variant,
                        outcome=dict(kind='verdict',label=truth['claim_gold'][claim['claim_key']][target],field=field,mapping=mp,target=target),extra=dict(label_map=mp,output_field=field))
        if g['domain']['type']=='nonnegative_integer':
            target=aliases[0]; vt=values[target]; d1=vt+2; d2=vt+3
            for ix,dd in enumerate([d1,d2]):
                tt,tab=table_text('MULTI',target,distractor=dd)
                add(g,'G_DISTRACTOR_SWAP','SYMBOLIC CONTROL ONLY. This table defines a new text task, not the original scene.\n'+tt+VALUE,target=target,variant='d'+str(ix+1),media=False,oracle=True,
                    outcome=dict(kind='value',value=vt,target=target,domain=g['domain'],distractor_value=dd,distractor_pair=[d1,d2]),extra=dict(oracle_table=tab),models=cfg['models'][:2])
    byid=unique(reqs,'request_id'); unique(gg,'request_id')
    # No private state dictionary or outcomes are serialized to ordinary inference payloads.
    for r in reqs:
        if set(r['payload'])!={'system','text','media'}: raise ValueError('PAYLOAD_ALLOWLIST_FAILURE')
        if not r['is_oracle'] and 'oracle_table' in r: raise ValueError('ORACLE_LEAKAGE')
        if r['phase']=='discovery' and any(rootpart in r.get('original_input',{}).get('split','') for rootpart in ['test','train']): raise ValueError('BAD_SPLIT')
    for g in groups:
        for cond in ['SELECT_VALUE','STATE_VERDICT']:
            matches=[r for r in reqs if r['group_id']==g['group_id'] and r['condition']==cond]
            for ck in {r['claim_id'] for r in matches}:
                pair=[r for r in matches if r['claim_id']==ck]
                if len(pair)!=2: raise ValueError('TARGET_PAIR_INCOMPLETE')
                normalized=[dict(r['payload'],text=r['payload']['text'].replace('TARGET STATE: '+r['target'],'TARGET STATE: <TARGET>')) for r in pair]
                if normalized[0]!=normalized[1]: raise ValueError('TARGET_ONLY_PAYLOAD_DIFF_FAILED')
    if not persist: return reqs,gg,groups
    frozen_write(root/'inputs'/stage/'requests.jsonl',reqs,'jsonl')
    frozen_write(root/'gold'/stage/'gold.jsonl',gg,'jsonl')
    frozen_write(root/'manifest'/stage/'state_group_manifest.jsonl',[public(g) for g in groups],'jsonl')
    frozen_write(root/'gold'/stage/'state_truth.jsonl',[dict(group_id=g['group_id'],**g['private']) for g in groups],'jsonl')
    from collections import Counter
    plan=dict(status='PASS',stage=stage,group_count=len(groups),group_clusters=len({g['cluster_id'] for g in groups}),coverage_pairs=len(coverage),unknown=len(unknown),
        controls=len(control_groups),interfaces=len(interface_groups),request_count=len(reqs),by_condition=dict(Counter(r['condition'] for r in reqs)),
        by_model={key:sum(key in r['models'] for r in reqs) for key in cfg['models']},input_hash=sha(root/'inputs'/stage/'requests.jsonl'),gold_hash=sha(root/'gold'/stage/'gold.jsonl'),
        gold_in_ordinary_payload=False,target_only_diff='PASS',prompt_version=version,confirmation_requests=0,test_requests=0,
        sample_selection_used_model_outcomes=False,all_models_common_core=True)
    frozen_write(root/'manifest'/stage/'request_plan.json',plan)
    print(json.dumps(plan)); return plan

def main():
    a=args(__doc__).parse_args(); cfg,root,project=setup(a)
    if a.dry_run: print(json.dumps(dict(status='PLANNED',action='build_setup'))); return
    construct(cfg,root,cfg.get('setup_input_stage','setup'))

if __name__=='__main__': main()
