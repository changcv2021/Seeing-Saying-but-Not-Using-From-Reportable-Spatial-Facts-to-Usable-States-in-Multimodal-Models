"""Deterministic A.1 v3 analysis; no model calls, prompt changes, or prediction-based selection."""
import subprocess
from collections import Counter,defaultdict
from v3common import *
from score_v3 import score
from cluster_stats import estimate

HERE=Path(__file__).resolve().parent
LABELS=['SUPPORTED','CONTRADICTORY','UNKNOWN']


def observed(r):
    return r is not None and r['execution_status']=='RESPONDED'


def hit(r,value):
    return observed(r) and r['parse_status']=='VALUE' and type(r['prediction']) is int and r['prediction']==value


def pair_pattern(a,b,values,keys):
    if not observed(a) or not observed(b): return 'NOT_RUN_OR_INFRA',None
    if a['parse_status']=='INVALID' or b['parse_status']=='INVALID': return 'INVALID',False
    if a['prediction'] is None or b['prediction'] is None: return 'NULL',False
    x,y=a['prediction'],b['prediction']; u,v=(values[k] for k in keys)
    if (x,y)==(u,v): return 'BOTH_CORRECT',True
    if u!=v and (x,y)==(v,u): return 'SWAPPED',False
    if x==y: return 'CONSTANT',False
    return 'OTHER_VALUES',False


def joint_pattern(r,values,keys):
    if not observed(r): return 'NOT_RUN_OR_INFRA'
    if r['parse_status']=='INVALID': return 'INVALID'
    p=r['prediction']
    if any(p.get(k) is None for k in keys): return 'NULL_OR_INCOMPLETE_MAP'
    if p==values: return 'EXACT_MAP'
    if values[keys[0]]!=values[keys[1]] and p=={keys[0]:values[keys[1]],keys[1]:values[keys[0]]}: return 'SWAPPED_MAP'
    return 'VALUE_ERROR'


def load_records(c,root,cards):
    locked=set(load(root/'manifest/reviewed_core_plan.json')['request_ids'])
    gold={g['request_id']:g for g in rows(root/'private_gold/core_draft.jsonl')}
    requests=list(rows(root/'review/draft_requests.jsonl')); output=[]
    core_lock=load(root/'manifest/core_lock.json'); check_entries(core_lock['code'])
    if sha(root/'inputs/core/requests.jsonl')!=core_lock['inputs_sha256']: raise ValueError('CORE_INPUT_CHANGED')
    actual_ids={r['request_id'] for r in rows(root/'inputs/core/requests.jsonl')}
    if actual_ids!=locked: raise ValueError('LOCKED_PANEL_CHANGED')
    for model in c['models']:
        known={r['request_id']+'.json' for r in requests}
        for p in (root/'raw/core'/model).glob('a1c3_*.json'):
            if p.name not in known: raise ValueError('UNREGISTERED_RAW:'+str(p))
        for r in requests:
            rid=r['request_id']; eligible=rid in locked; card=cards[r['group_id']]
            p=root/'raw/core'/model/(rid+'.json'); raw=load(p) if p.is_file() else None
            if raw is not None and not eligible: raise ValueError('RAW_FOR_INELIGIBLE_REQUEST')
            if raw:
                if raw['model']!=model or raw['request_id']!=rid or raw['request_sha256']!=digest(r):
                    raise ValueError('RAW_REQUEST_ALIGNMENT')
                if raw['lock_sha256']!=sha(root/'manifest/core_lock.json'): raise ValueError('RAW_LOCK_MISMATCH')
            preflight=load(root/'review/rendered'/model/(rid+'.json'))
            rendered=preflight
            if raw and raw.get('rendered_path'):
                rendered=load(raw['rendered_path'])
                if (rendered['rendered_prompt_sha256'],rendered['presentation_hash'])!=(preflight['rendered_prompt_sha256'],preflight['presentation_hash']):
                    raise ValueError('GENERATED_INPUT_DIFFERS_FROM_REVIEW')
            g=dict(gold[rid],condition_eligible=eligible)
            scored=score(raw,g)
            execution='NOT_ELIGIBLE' if not eligible else 'NOT_RUN' if raw is None else 'INFRA_FAILURE' if raw.get('infrastructure_error') else 'RESPONDED'
            status='NOT_ELIGIBLE' if not eligible else scored['status']
            output.append(dict(model=model,request_id=rid,parent_request_id=r['parent_request_id'],
                group_id=r['group_id'],underlying_world_id=r['underlying_world_id'],world_id=card['world_id'],
                level=r['level'],stratum=card['stratum'],state_dimension=card['state_dimension'],
                condition=r['condition'],target=r['target'],variant=r['variant'],schema=r['schema'],
                condition_eligible=eligible,eligibility_reason='RESEARCHER_VERIFIED' if eligible else 'POST_NO_MEDIA_WITNESSES_NOT_SEPARATELY_ATTESTED',
                provenance=g['provenance'],claim_type=g.get('claim_type'),claim_value=g.get('claim_value'),
                gold=g['expected'],source_values=g['source_values'],gold_record=g,
                execution_status=execution,parse_status=status,prediction=scored['pred'],correct=scored['correct'],
                strict_contract_ok=scored['strict_contract_ok'],normalization=scored['normalization'],
                score=scored,raw_response=raw.get('raw_response') if raw else None,
                raw_path=str(p) if raw else None,raw_sha256=sha(p) if raw else None,
                actual_rendered_prompt=rendered['rendered_prompt'],rendered_prompt_sha256=rendered['rendered_prompt_sha256'],
                presentation_hash=rendered['presentation_hash'],input_tokens=rendered['input_tokens'],
                media=r['payload']['media'],raw_record=raw))
    return output


def cohorts(cards,review):
    result=defaultdict(set)
    for gid,card in cards.items():
        if review[gid]['new_review_status']=='VERIFIED_FOR_A1': result[card['stratum']].add(card['underlying_world_id'])
    return {k:sorted(v) for k,v in result.items()}


def coverage(rr):
    elig=[r for r in rr if r['condition_eligible']]; responses=[r for r in elig if observed(r)]
    attempted=[r for r in elig if r['raw_record'] is not None]
    correct=sum(r['correct'] is True for r in responses)
    return dict(N_planned=len(elig),N_attempted=len(attempted),N_responses=len(responses),
        N_scored=sum(r['correct'] is not None for r in responses),N_correct=correct,
        N_invalid=sum(r['parse_status']=='INVALID' for r in responses),N_null=sum(r['parse_status']=='NULL' for r in responses),
        N_partial_null_map=sum(r['schema']['kind']=='joint' and isinstance(r['prediction'],dict) and any(v is None for v in r['prediction'].values()) for r in responses),
        N_infra=sum(r['execution_status']=='INFRA_FAILURE' for r in elig),N_not_run=sum(r['execution_status']=='NOT_RUN' for r in elig),
        N_not_eligible=len(rr)-len(elig),N_normalized=sum(r['normalization']!='NONE' for r in responses),
        N_strict_contract_ok=sum(r['strict_contract_ok'] is True for r in responses),
        unique_worlds=len({r['underlying_world_id'] for r in elig}),
        response_coverage=len(responses)/len(elig) if elig else None,
        response_accuracy=correct/len(responses) if responses else None,
        attempted_execution_accuracy=correct/len(attempted) if attempted else None,
        attempt_count_caveat='PER_REQUEST_RAW_PRESENT; job-level load failures and interrupted requests without a raw record are reported separately, not fabricated as observed attempts')


def condition_summary(records,cohort):
    groups=defaultdict(list)
    for r in records: groups[r['model'],r['stratum'],r['condition']].append(r)
    output=[]
    for (model,stratum,condition),rr in groups.items():
        obs=[(r['underlying_world_id'],int(r['correct'] is True),1) for r in rr if observed(r)]
        output.append(dict(model=model,stratum=stratum,condition=condition,**coverage(rr),**estimate(obs,cohort[stratum])))
    return output


def controls(records,matches,cards,cohort):
    idx={(r['model'],r['request_id']):r for r in records}; output=[]; samples=defaultdict(list)
    for model in sorted({r['model'] for r in records}):
        for m in matches:
            a=idx[model,m['base_request_id']]; b=idx[model,m['control_request_id']]
            both=observed(a) and observed(b); ca=a['correct']; cb=b['correct']
            same_gold=type(a['gold']) is type(b['gold']) and a['gold']==b['gold']
            rescue=int(ca is False and cb is True) if both else None
            harm=int(ca is True and cb is False) if both else None
            row=dict(model=model,**m,stratum=a['stratum'],base_condition=a['condition'],control_condition=b['condition'],
                base_prediction=a['prediction'],control_prediction=b['prediction'],base_status=a['parse_status'],control_status=b['parse_status'],
                base_correct=ca,control_correct=cb,same_gold=same_gold,
                rescue=rescue,harm=harm,unchanged=int(ca==cb) if both else None,net=rescue-harm if both else None,
                both_responses=both,eligibility_reason='LOCKED_MATCHED_PAIR',
                raw_paths=[a['raw_path'],b['raw_path']],base_tokens=a['input_tokens'],control_tokens=b['input_tokens'],
                token_length_difference=b['input_tokens']-a['input_tokens'],
                token_lengths_equal=a['input_tokens']==b['input_tokens'],intrusion_excess=None,accuracy_cost=None,
                tracking=None,base_distractor_value=None,control_distractor_value=None,
                interpretation='TARGET_FLIP_IS_TASK_CHANGE_NOT_RESCUE_INTERVENTION' if 'TARGET_FLIP' in m['comparison'] else 'MATCHED_SEPARATE_REQUEST_BEHAVIOR')
            card=cards[m['group_id']]; vals=card['values']; target=m['target']; world=a['underlying_world_id']
            def add(metric,value):
                samples[model,a['stratum'],m['comparison'],metric].append((world,value if value is not None else 0,1 if value is not None else 0))
            if 'TARGET_FLIP' not in m['comparison']:
                for key in ['rescue','harm','net','unchanged']: add(key,row[key])
            if m['comparison']=='MULTI_TO_SHAM':
                d=next(v for k,v in vals.items() if k!=target)
                row.update(base_distractor_value=d,control_distractor_value=d,
                    intrusion_excess=int(hit(a,d))-int(hit(b,d)) if both else None,
                    accuracy_cost=int(cb is True)-int(ca is True) if both else None)
                add('intrusion_excess',row['intrusion_excess']); add('accuracy_cost',row['accuracy_cost'])
            if m['comparison'] in ['ORACLE_MULTI_D1_TO_D2','ORACLE_SHAM_D1_TO_D2']:
                d1=next(v for k,v in vals.items() if k!=target); d2=max(vals.values())+1
                if len({d1,d2,vals[target]})!=3: raise ValueError('DEGENERATE_TRACKING')
                row.update(base_distractor_value=d1,control_distractor_value=d2,
                           tracking=int(hit(a,d1) and hit(b,d2)) if both else None)
                add('tracking',row['tracking'])
            output.append(row)
    summary=[dict(model=m,stratum=s,comparison=k,metric=metric,**estimate(obs,cohort[s])) for (m,s,k,metric),obs in samples.items()]
    return output,summary


def diagnostic_matrix(records,cards,review,matches,cohort):
    index={(r['model'],r['group_id'],r['condition'],r['target'],r['variant']):r for r in records}
    models=sorted({r['model'] for r in records}); output=[]; pairs=[]; conditional=[]; transitions=[]
    for model in models:
        for gid,card in cards.items():
            row=dict(model=model,group_id=gid,underlying_world_id=card['underlying_world_id'],
                source_world_aliases_json=[card['world_id'],card['cluster_id']],level=card['level'],source=card['source'],
                stratum=card['stratum'],review_status=review[gid]['new_review_status'],
                category=card.get('category'),count_scope=card.get('count_scope'),action_target_scope=card.get('action_target_scope'),
                failure_candidate_tags_json=[],competing_explanations_json=[],notes='Independent requests do not expose a single run internal state; no mechanistic proof.')
            if review[gid]['new_review_status']!='VERIFIED_FOR_A1':
                row.update(failure_candidate_tags_json=['INPUT_OR_PRESENTATION_LIMITATION'],notes='DEFERRED_REFERENCE_FRAME; no core requests run or scored.')
                output.append(row); continue
            keys=['PRE','POST'] if card['level']=='L4' else ['OBJECT_A','OBJECT_B']; vals=card['values']
            rr=[r for r in records if r['model']==model and r['group_id']==gid]
            row['all_eligible_requests_responded']=all(observed(r) for r in rr if r['condition_eligible'])
            get=lambda cond,t='',v='':index.get((model,gid,cond,t,v))
            def put(prefix,r):
                row[prefix+'_request_id']=r['request_id'] if r else None
                row[prefix+'_pred']=r['prediction'] if r else None
                row[prefix+'_parse_status']=r['parse_status'] if r else 'NOT_APPLICABLE'
                row[prefix+'_correct']=r['correct'] if r else None
            row['presentation_id']=next(r['presentation_hash'] for r in rr if r['media'])
            row['eligibility_by_condition_json']={r['condition']:r['condition_eligible'] for r in rr}
            row['matched_control_ids_json']=[m['match_id'] for m in matches if m['group_id']==gid]
            row['all_request_results_json']=[dict(request_id=r['request_id'],condition=r['condition'],target=r['target'],variant=r['variant'],
                                                   pred=r['prediction'],parse_status=r['parse_status'],correct=r['correct']) for r in rr]
            scond='SELECT_MEDIA' if card['level']=='L4' else 'SELECT_MEDIA_OBJECT'
            jcond='JOINT_STATE' if card['level']=='L4' else 'JOINT_OBJECT'
            jf,jr=get(jcond,v='forward'),get(jcond,v='reverse')
            for name,r in [('joint_pre_first' if card['level']=='L4' else 'joint_object_a_first',jf),
                           ('joint_post_first' if card['level']=='L4' else 'joint_object_b_first',jr)]:
                row[name+'_request_id']=r['request_id']; row[name+'_values_json']=r['prediction']; row[name+'_exact']=r['correct']
                row[name+'_pattern']=joint_pattern(r,vals,keys)
                row[name+'_requested_order_followed']=(r['score'].get('key_order')==r['schema']['keys']) if observed(r) else None
            row['joint_both_orders_exact']=bool(jf['correct'] and jr['correct']) if observed(jf) and observed(jr) else None
            for prefix,cond in [('select_media',scond),('oracle_single','ORACLE_SINGLE'),('oracle_multi','ORACLE_MULTI')]:
                for target in keys: put(prefix+'_'+target.lower(),get(cond,target))
            for prefix,cond in [('media',scond),('oracle','ORACLE_MULTI')]:
                a,b=[get(cond,k) for k in keys]; pattern,correct=pair_pattern(a,b,vals,keys)
                row[prefix+'_target_pair_correct']=correct; row[prefix+'_target_pair_pattern']=pattern
                pairs.append(dict(model=model,group_id=gid,underlying_world_id=card['underlying_world_id'],stratum=card['stratum'],
                    condition=cond,pattern=pattern,correct=correct,request_ids=[a['request_id'],b['request_id']],
                    predictions=[a['prediction'],b['prediction']],gold=[vals[k] for k in keys],both_responses=observed(a) and observed(b)))
            if card['level']=='L1':
                for k in keys: put('object_value_'+k.lower(),get('OBJECT_VALUE',k))
                row['object_gold_json']=vals
                row['notes']+=' L1 object control only; all time-state/action fields N/A.'
            else:
                row.update(pre_gold=vals['PRE'],post_gold=vals['POST'],neither_claim_value=max(vals.values())+1)
                for cond in ['PRE_VALUE','POST_VALUE','TEXT_STATE_UPDATE','POST_NO_MEDIA']:
                    put(cond.lower(),get(cond,'PRE' if cond=='PRE_VALUE' else 'POST'))
                pre,post,act=get('PRE_VALUE','PRE'),get('POST_VALUE','POST'),get('ACTION_PARSE')
                row.update(action_request_id=act['request_id'],action_prediction_json=act['prediction'],
                           action_component_scores_json=act['score']['component_scores'],action_parse_status=act['parse_status'],
                           action_exact=act['correct'],entity_grounding='NOT_MEASURED')
                if pre['parse_status']=='VALUE' and pre['correct'] is False: row['failure_candidate_tags_json'].append('PRE_REPORT_FAILURE')
                if pre['parse_status']=='NULL': row['failure_candidate_tags_json'].append('PRE_NULL_REPORT')
                if act['parse_status']=='VALID_ACTION' and act['correct'] is False: row['failure_candidate_tags_json'].append('ACTION_REPORT_FAILURE')
                if pre['correct'] and act['correct'] and post['parse_status']=='VALUE' and post['correct'] is False:
                    row['failure_candidate_tags_json'].append('UPDATE_GAP_CANDIDATE')
                pp=pre['prediction']; rule=card['action_expected']; derived=None
                if type(pp) is int and pp>=0:
                    delta=rule['amount']*(1 if rule['operation']=='ADD' else -1)
                    if pp+delta>=0: derived=pp+delta
                transitions.append(dict(model=model,group_id=gid,underlying_world_id=card['underlying_world_id'],pre_request_id=pre['request_id'],
                    post_request_id=post['request_id'],reported_pre=pp,gold_action=rule,derived_post_from_reported_pre=derived,
                    reported_post=post['prediction'],applicable=derived is not None and post['parse_status']=='VALUE',
                    consistent=(derived==post['prediction']) if derived is not None and post['parse_status']=='VALUE' else None,
                    caveat='Cross-request self-premise transition consistency, not gold correctness or internal-state evidence'))
                conditional.append(dict(model=model,group_id=gid,underlying_world_id=card['underlying_world_id'],stratum=card['stratum'],
                    metric='POST_FAILURE_GIVEN_PRE_ACTION_CORRECT',target='',eligible=pre['correct'] is True and act['correct'] is True,
                    outcome_observed=observed(post),failure=post['correct'] is False,outcome_status=post['parse_status'],
                    request_ids=[pre['request_id'],act['request_id'],post['request_id']]))
            for target in keys:
                sel=get(scond,target); multi=get('ORACLE_MULTI',target); single=get('ORACLE_SINGLE',target)
                if single['correct'] and multi['parse_status']=='VALUE' and multi['correct'] is False:
                    row['failure_candidate_tags_json'].append('EXPLICIT_SELECTION_GAP_CANDIDATE')
                if row['joint_both_orders_exact'] and sel['parse_status']=='VALUE' and sel['correct'] is False:
                    row['failure_candidate_tags_json'].append('MULTIMODAL_SELECTION_GAP_CANDIDATE')
                for jname,predicate in [('FORWARD',jf['correct'] is True),('REVERSE',jr['correct'] is True),('BOTH',row['joint_both_orders_exact'] is True)]:
                    conditional.append(dict(model=model,group_id=gid,underlying_world_id=card['underlying_world_id'],stratum=card['stratum'],
                        metric='SELECT_FAILURE_GIVEN_JOINT_'+jname+'_EXACT',target=target,eligible=predicate,
                        outcome_observed=observed(sel),failure=sel['correct'] is False,outcome_status=sel['parse_status'],
                        request_ids=[jf['request_id'],jr['request_id'],sel['request_id']]))
                if card['level']=='L4':
                    missing=get('ORACLE_MISSING_VALUE',target); other=next(v for k,v in vals.items() if k!=target)
                    if hit(missing,other): row['failure_candidate_tags_json'].append('MISSING_TARGET_BORROWING_PATTERN')
            for cond,select in [('CLAIM_MEDIA',scond),('CLAIM_ORACLE','ORACLE_MULTI')]:
                claims=[r for r in rr if r['condition']==cond]
                row[cond.lower()+'_results_json']=[dict(request_id=r['request_id'],target=r['target'],claim_value=r['claim_value'],claim_type=r['claim_type'],
                    gold_label=r['gold'],prediction_label=r['prediction'],parse_status=r['parse_status'],correct=r['correct']) for r in claims]
                for claim in claims:
                    value=get(select,claim['target'])
                    if value['correct'] and claim['parse_status']=='VALID_LABEL' and claim['correct'] is False:
                        row['failure_candidate_tags_json'].append('COMPARISON_GAP_CANDIDATE')
                    if claim['claim_type']=='neither_state' and claim['parse_status']=='VALID_LABEL' and claim['prediction']=='SUPPORTED':
                        row['failure_candidate_tags_json'].append('UNSUPPORTED_ACCEPTANCE_PATTERN')
                    conditional.append(dict(model=model,group_id=gid,underlying_world_id=card['underlying_world_id'],stratum=card['stratum'],
                        metric=cond+'_FAILURE_GIVEN_TARGET_VALUE_CORRECT',target=claim['target']+'|'+str(claim['claim_value']),
                        eligible=value['correct'] is True,outcome_observed=observed(claim),failure=claim['correct'] is False,
                        outcome_status=claim['parse_status'],request_ids=[value['request_id'],claim['request_id']]))
            if any(r['normalization']!='NONE' for r in rr if observed(r)): row['failure_candidate_tags_json'].append('INTERFACE_SENSITIVITY')
            if any(r['parse_status']=='INVALID' for r in rr): row['failure_candidate_tags_json'].append('ANSWER_INTERFACE_INVALID')
            row['failure_candidate_tags_json']=sorted(set(row['failure_candidate_tags_json']))
            row['competing_explanations_json']=['VISUAL_EVIDENCE_SUFFICIENCY','QUERY_UNDERSTANDING','CROSS_REQUEST_RECOMPUTATION','ACTION_TEXT_SHORTCUT','CONTEXT_OR_POSITION_EFFECT','CLAIM_ACCEPTANCE_BIAS','ANSWER_INTERFACE']
            output.append(row)
    return output,pairs,conditional,transitions


def conditional_summary(conditions,cohort,models):
    index=defaultdict(dict)
    for r in conditions: index[r['group_id'],r['metric'],r['target']][r['model']]=r
    groups=defaultdict(list)
    for r in conditions:
        same=index[r['group_id'],r['metric'],r['target']]
        common=len(same)==len(models) and all(x['eligible'] for x in same.values())
        for scope,eligible in [('MODEL_SPECIFIC',r['eligible']),('THREE_MODEL_COMMON',common)]:
            den=int(eligible and r['outcome_observed'])
            groups[r['model'],r['stratum'],r['metric'],scope].append((r['underlying_world_id'],int(r['failure'])*den,den))
    return [dict(model=m,stratum=s,metric=k,subset=scope,**estimate(obs,cohort[s])) for (m,s,k,scope),obs in groups.items()]


def claim_summary(records,cohort):
    groups=defaultdict(list); confusion=Counter()
    for r in records:
        if r['condition'].startswith('CLAIM_'):
            groups[r['model'],r['stratum'],r['condition'],r['claim_type'] or 'missing_target'].append(r)
            confusion[r['model'],r['stratum'],r['condition'],r['claim_type'] or 'missing_target',r['gold'],r['prediction'] if r['parse_status']=='VALID_LABEL' else r['parse_status']]+=1
    summary=[]
    for (model,stratum,condition,kind),rr in groups.items():
        for metric in ['accuracy','unsupported_acceptance','unknown_response']:
            obs=[]
            for r in rr:
                if not observed(r): continue
                num=(r['correct'] is True) if metric=='accuracy' else (r['parse_status']=='VALID_LABEL' and r['prediction']==('SUPPORTED' if metric=='unsupported_acceptance' else 'UNKNOWN'))
                if metric=='unsupported_acceptance' and r['gold']=='SUPPORTED': continue
                obs.append((r['underlying_world_id'],int(num),1))
            summary.append(dict(model=model,stratum=stratum,condition=condition,claim_type=kind,metric=metric,**coverage(rr),**estimate(obs,cohort[stratum])))
    table=[dict(model=m,stratum=s,condition=c,claim_type=k,gold=g,prediction=p,count=n) for (m,s,c,k,g,p),n in confusion.items()]
    return summary,table


def write_csv(path,rr,default=None):
    rr=list(rr); fields=list(dict.fromkeys(k for r in rr for k in r)) or default or ['status']
    csvsave(path,rr,fields,frozen=False)


def component_summaries(records,matrix,cohort):
    groups=defaultdict(list)
    for r in records:
        if not observed(r): continue
        s=r['stratum']; m=r['model']; world=r['underlying_world_id']
        if r['condition']=='ACTION_PARSE':
            for key in ['operation','target','amount']:
                groups[m,s,'ACTION_'+key.upper()].append((world,int(r['score']['component_scores'][key]),1))
        if r['schema']['kind']=='joint':
            groups[m,s,'JOINT_'+r['variant'].upper()+'_EXACT'].append((world,int(r['correct']),1))
            pat=joint_pattern(r,r['source_values'],r['schema']['keys'])
            for category in ['SWAPPED_MAP','VALUE_ERROR','NULL_OR_INCOMPLETE_MAP','INVALID']:
                groups[m,s,'JOINT_'+r['variant'].upper()+'_'+category].append((world,int(pat==category),1))
    for r in matrix:
        if r.get('joint_both_orders_exact') is not None:
            groups[r['model'],r['stratum'],'JOINT_BOTH_ORDERS_EXACT'].append((r['underlying_world_id'],int(r['joint_both_orders_exact']),1))
    return [dict(model=m,stratum=s,metric=k,**estimate(obs,cohort[s])) for (m,s,k),obs in groups.items()]


def semantic_breakdown(root,c):
    requests=list(rows(root/'inputs/precore/requests.jsonl'))
    gold={r['request_id']:r for r in rows(root/'private_gold/precore.jsonl')}
    groups=defaultdict(Counter)
    for m in c['models']:
        for r in requests:
            if r['stage']!='semantic_bridge': continue
            g=gold[r['request_id']]; path=root/'raw/precore'/m/(r['request_id']+'.json')
            raw=load(path) if path.is_file() else None; s=score(raw,g)
            count=groups[m,r['condition'],r['variant'],r['target']]; count['planned']+=1
            if s['status'] in ['NOT_RUN','INFRA_FAILURE']:
                count[s['status']]+=1; continue
            count['responses']+=1; count['correct']+=int(s['correct'] is True)
            if s['status']=='INVALID': count['invalid']+=1
            elif s['status']=='NULL': count['correct_null' if g['expected'] is None else 'incorrect_null']+=1
            elif r['schema']['kind']=='value':
                count['correct_value' if s['correct'] else 'incorrect_value']+=1
                # Visible wrong-value borrowing is classified from the public explicit table, never a hidden gold state.
                import re
                visible=[int(v) for v in re.findall(r'(?:query_value|query_count)\s*=\s*(\d+)',r['payload']['text'])]
                if g['expected'] is None and type(s['pred']) is int and s['pred'] in visible:
                    count['copied_visible_other_value']+=1
            elif s['status']=='VALID_LABEL': count['label_'+s['pred']]+=1
    return [dict(model=m,condition=cond,naming=naming,target=target,**dict(n),scope='DESCRIPTIVE_FIXED_ONE_PASS_SYNTHETIC_NOT_CORE_MECHANISM_EVIDENCE')
            for (m,cond,naming,target),n in groups.items()]


def main():
    p=arguments(__doc__); p.add_argument('--lock-only',action='store_true'); a=p.parse_args(); c,root=setup(a)
    if a.dry_run: print('PLANNED: score only frozen core and preserve unrun/invalid/null; no model calls'); return
    compute()
    sources=[entry(p) for p in sorted(HERE.glob('*.py'))]+[entry(HERE/'job.sh')]
    if a.lock_only:
        for i,record in enumerate(sources):
            source=Path(record['path']); target=root/'manifest/core_analysis_v1_snapshot'/f'{i:03d}_{source.name}'
            save(target,source.read_text(),'text')
            if sha(target)!=record['sha256']: raise ValueError('ANALYSIS_SOURCE_SNAPSHOT_MISMATCH')
        save(root/'manifest/core_analysis_v1_lock.json',dict(version='A1_CORE_ANALYSIS_V1',code=sources,
            research_rules='User core v3 sections 10-12',models=c['models'],primary_model='qwen35_9b',seed=c['seed'],bootstrap_repetitions=2000,
            raw_core_not_read_for_analysis_design=True,panel='EXACT_REVIEWED_CORE_312_PER_MODEL',
            candidate_rules='Explicit wrong value separated from NULL/INVALID; strict both-joint-orders gate for multimodal-selection tag; competing explanations retained',
            rank_rule='Primary 9B supported candidate-world count is descriptive only; no significance/4-of-7 cutoff and no automatic Phase B',
            next_stage_default='NEEDS_BOUNDED_BEHAVIORAL_REPLICATION_IF_FAILURES_ELSE_NO_STABLE_FAILURE'))
        print('ANALYSIS_CODE_LOCKED_NO_CORE_RESPONSES_READ'); return
    check_entries(load(root/'manifest/core_analysis_v1_lock.json')['code'])
    cards={r['group_id']:r for r in rows(root/'review/candidate_panel.jsonl')}; review={r['group_id']:r for r in csvrows(root/'review/researcher_records.csv')}
    cohort=cohorts(cards,review); records=load_records(c,root,cards)
    output=root/'analysis_v1'; handoff=root/'handoff'; tables=root/'tables'
    matches=list(rows(root/'manifest/reviewed_matched_controls.jsonl'))
    condition=condition_summary(records,cohort); matched,matched_stats=controls(records,matches,cards,cohort)
    matrix,pairs,conditional,transitions=diagnostic_matrix(records,cards,review,matches,cohort)
    condstats=conditional_summary(conditional,cohort,c['models']); claims,confusion=claim_summary(records,cohort)
    components=component_summaries(records,matrix,cohort); semantic=semantic_breakdown(root,c)
    pair_stats=[]
    for model in c['models']:
        for stratum,worlds in cohort.items():
            for cond in sorted({r['condition'] for r in pairs if r['stratum']==stratum}):
                rr=[r for r in pairs if r['model']==model and r['stratum']==stratum and r['condition']==cond]
                obs=[(r['underlying_world_id'],int(r['correct'] is True),int(r['both_responses'])) for r in rr]
                pair_stats.append(dict(model=model,stratum=stratum,condition=cond,patterns=dict(Counter(r['pattern'] for r in rr)),**estimate(obs,worlds)))
    for name,rr in [('request_results',records),('condition_summary',condition),('matched_controls',matched),('matched_control_summary',matched_stats),
                    ('a1_failure_matrix',matrix),('target_pairs',pairs),('target_pair_summary',pair_stats),('conditional_cases',conditional),
                    ('conditional_summary',condstats),('self_reported_transition',transitions),('claim_summary',claims),('claim_confusion',confusion),
                    ('component_and_joint_summary',components),('semantic_bridge_detailed_summary',semantic)]:
        write_csv(output/(name+'.csv'),rr)
    write_csv(tables/'a1_failure_matrix.csv',matrix)
    raw_index=[dict(model=r['model'],request_id=r['request_id'],group_id=r['group_id'],underlying_world_id=r['underlying_world_id'],
                    execution_status=r['execution_status'],raw_path=r['raw_path'],raw_sha256=r['raw_sha256']) for r in records]
    write_csv(output/'raw_response_index.csv',raw_index)
    measures=[]
    for model in c['models']:
        for tag in sorted({t for r in matrix if r['stratum']=='L4_COUNT_PRIMARY' for t in r['failure_candidate_tags_json']}):
            rr=[r for r in matrix if r['model']==model and r['stratum']=='L4_COUNT_PRIMARY']
            active=[r for r in rr if tag in r['failure_candidate_tags_json']]
            measures.append(dict(model=model,candidate=tag,worlds=[r['underlying_world_id'] for r in active],
                group_ids=[r['group_id'] for r in active],operation_distribution=dict(Counter(cards[r['group_id']]['action_expected']['operation'] for r in active)),
                category_distribution=dict(Counter(cards[r['group_id']]['category'] for r in active)),
                eligibility='Only worlds with all eligible requests responded enter candidate-frequency denominator; partial-world observations remain in matrix',
                **estimate([(r['underlying_world_id'],int(tag in r['failure_candidate_tags_json'] and r['all_eligible_requests_responded']),
                             int(r['all_eligible_requests_responded'])) for r in rr],cohort['L4_COUNT_PRIMARY'])))
    write_csv(output/'candidate_summary.csv',measures)
    value_dist=[dict(group_id=gid,underlying_world_id=card['underlying_world_id'],pre=card['values']['PRE'],post=card['values']['POST'],
        operation=card['action_expected'],operator=card['operator'],category=card['category']) for gid,card in cards.items() if card['stratum']=='L4_COUNT_PRIMARY']
    write_csv(output/'l4_value_operation_distribution.csv',value_dist)
    baselines=[]
    for stratum in cohort:
        base=[r for r in records if r['model']==c['models'][0] and r['stratum']==stratum and r['condition_eligible'] and r['schema']['kind']=='value']
        for val in [0,1]:
            for cond in sorted({r['condition'] for r in base}):
                rr=[r for r in base if r['condition']==cond]
                baselines.append(dict(stratum=stratum,condition=cond,constant_prediction=val,**estimate([(r['underlying_world_id'],int(type(r['gold']) is int and r['gold']==val),1) for r in rr],cohort[stratum])))
    write_csv(output/'constant_value_baselines.csv',baselines)
    totals={m:coverage([r for r in records if r['model']==m]) for m in c['models']}
    complete=all(n['N_responses']==312 and n['N_infra']==0 for n in totals.values())
    status='COMPLETE_FOR_LOCKED_PANEL' if complete else 'PARTIAL_BLOCKED_INFRA'
    routes=[r for r in measures if r['model']=='qwen35_9b' and r['numerator']>0]
    routes.sort(key=lambda r:(-r['numerator'],r['candidate']))
    responses=[r for r in records if observed(r)]; all_correct=complete and all(r['correct'] for r in responses)
    decision=dict(stage='PHASE_A1_CORE_V3',execution_status=status,
        scientific_status='NO_STABLE_FAILURE_IN_THIS_PANEL' if all_correct else 'MIXED_OR_UNRESOLVED',
        generated_core_responses=len(responses),verified_l4_count_worlds=7,verified_l1_control_worlds=5,primary_model='qwen35_9b',
        candidate_routes=routes,remaining_competing_explanations=['VISUAL_EVIDENCE_SUFFICIENCY','QUERY_UNDERSTANDING','ACTION_TEXT_SHORTCUT',
        'CROSS_REQUEST_RECOMPUTATION','CONTEXT_POSITION_EFFECTS','CLAIM_ACCEPTANCE_BIAS','ANSWER_INTERFACE'],
        excluded_complete_explanations=([dict(explanation='ONLY_OTHER_STATE_SELECTION_EXPLAINS_ALL_ACCEPTANCE',scope='World/model rows with neither-state acceptance',
         evidence=[dict(model=r['model'],group_id=r['group_id']) for r in matrix if 'UNSUPPORTED_ACCEPTANCE_PATTERN' in r['failure_candidate_tags_json']])]
         if any('UNSUPPORTED_ACCEPTANCE_PATTERN' in r['failure_candidate_tags_json'] for r in matrix) else []),
        evidence_request_ids=[r['request_id'] for r in responses if r['correct'] is False],
        counterexample_request_ids=[r['request_id'] for r in responses if r['correct'] is True],
        recommendation='INSPECT_INFRA_AND_MISSING_OUTPUTS' if not complete else 'NO_STABLE_FAILURE_IN_THIS_PANEL' if all_correct else 'NEEDS_BOUNDED_BEHAVIORAL_REPLICATION',
        leading_descriptive_candidate=routes[0]['candidate'] if routes else None,mechanism_proven=False,auto_execute_phase_b=False,
        caution='Frequency ranking is descriptive, not mechanism selection or permission for a next phase. Different-query success does not establish latent knowledge in an erroneous run.')
    save(output/'next_stage_decision.json',decision,frozen=False)
    protected=check_entries(list(rows(root/'manifest/history_before.jsonl')))
    jobs=load(root/'resources/core_submissions.json')['jobs']
    accounting=subprocess.run(['sacct','-j',','.join(j['job_id'] for j in jobs),'--format=JobID,State,ExitCode,Elapsed,ElapsedRaw,AllocCPUS,ReqMem,MaxRSS,AllocTRES','-P'],text=True,capture_output=True)
    save(output/'slurm_accounting.txt',accounting.stdout+accounting.stderr,'text',frozen=False)
    acceptance=dict(status=status,G0=dict(status='PASS',historical_files_checked=protected,changed_files=[]),
        G1=load(root/'reports/researcher_review_acceptance.json'),G2=load(root/'reports/gpu_engineering.json'),
        G3=load(root/'reports/core_launch_acceptance.json'),G4=dict(status=status,per_model=totals),
        resource_authorization=load(root/'resources/core_authorization.json'),analysis_lock=entry(root/'manifest/core_analysis_v1_lock.json'),
        no_new_model_calls=True,stop_after_a1=True)
    save(output/'acceptance.json',acceptance,frozen=False)
    for name,rr in [('02_A1_FAILURE_MATRIX.csv',matrix),('03_CORE_RESPONSES_WITH_PROMPTS.csv',records),('04_MATCHED_CONTROLS.csv',matched),
                    ('05_DERIVED_INPUT_REVIEW.csv',list(review.values())),('condition_summary.csv',condition),('matched_control_summary.csv',matched_stats),
                    ('target_pair_summary.csv',pair_stats),('conditional_summary.csv',condstats),('claim_summary.csv',claims),
                    ('claim_confusion.csv',confusion),('candidate_summary.csv',measures),('raw_response_index.csv',raw_index),
                    ('l4_value_operation_distribution.csv',value_dist),('constant_value_baselines.csv',baselines),('self_reported_transition.csv',transitions),
                    ('component_and_joint_summary.csv',components),('semantic_bridge_detailed_summary.csv',semantic)]:
        write_csv(handoff/name,rr)
    save(handoff/'06_ACCEPTANCE_AND_PROTOCOL.json',acceptance,frozen=False)
    save(handoff/'08_NEXT_STAGE_DECISION.json',decision,frozen=False)
    report=report_cn(status,totals,condition,pair_stats,matched_stats,condstats,routes,decision)
    save(handoff/'01_A1_CORE_REPORT_CN.md',report,'text',frozen=False)
    save(root/'phase_a1_report_cn.md',report,'text',frozen=False)
    save(handoff/'00_README_CN.md','# SpaceConflict A.1 core v3\n\n先读 [执行与诊断报告](01_A1_CORE_REPORT_CN.md)。完整原始响应保留服务器；本目录 03 表内嵌全部核心响应/实际提示，包括未运行与不合格行。\n\n状态：'+status+'。L4 count 与 L1 object 分开；不将行为分离称作内部机制证明。本阶段后停止，不自动进入下一研究阶段。\n','text',frozen=False)
    sources=[root/'manifest/core_lock.json',root/'manifest/core_protocol_lock.json',root/'manifest/core_analysis_v1_lock.json',root/'manifest/core_code_snapshot_index.json',
        root/'review/researcher_records.csv',root/'review/user_chat_confirmation_20260908.json',root/'resources/core_authorization.json',root/'resources/core_submissions.json',
        output/'raw_response_index.csv',output/'slurm_accounting.txt',root/'private_gold/core.jsonl']
    write_csv(handoff/'SOURCE_INDEX.csv',[entry(p) for p in sources])
    save(handoff/'SHA256SUMS.txt',''.join(sha(p)+'  '+p.name+'\n' for p in sorted(handoff.iterdir()) if p.is_file() and p.name!='SHA256SUMS.txt'),'text',frozen=False)
    live=load(root/'LIVE_STATUS.json'); live.update(status=status,core_responses=len(responses),core_per_model=totals,
        core_budget_approved=True,core_analysis_report=str(root/'phase_a1_report_cn.md'),updated_at_utc=now(),auto_execute_phase_b=False)
    save(root/'LIVE_STATUS.json',live,frozen=False)
    print(json.dumps(dict(status=status,core_responses=len(responses),per_model=totals)),flush=True)


def fmt(x):
    return 'N/A' if x is None else f'{100*x:.1f}%'


def report_cn(status,totals,condition,pairs,matched,conditional,routes,decision):
    t='# SpaceConflict A.1 真实核心执行与诊断报告\n\n'
    t+='## 1. 执行与范围\n\n状态：'+status+'。本报告仅分析新 A.1 core，不是重跑 Phase A 或全量 L1–L4 benchmark。\n\n'
    t+='| 模型 | 计划 | 返回 | 评分 | INVALID | NULL | INFRA | 未运行 |\n|---|---:|---:|---:|---:|---:|---:|---:|\n'
    for m,n in totals.items(): t+=f'| {m} | {n["N_planned"]} | {n["N_responses"]} | {n["N_scored"]} | {n["N_invalid"]} | {n["N_null"]} | {n["N_infra"]} | {n["N_not_run"]} |\n'
    t+='\n共同 12 个独立底层 world：7 个 L4 count 主分析、5 个 L1 object 控制；4 个关系 world 暂缓。各 312 条，共 936 条计划请求；另 7 条/模型 POST_NO_MEDIA 缺单独补全审核而 NOT_ELIGIBLE，不计错误。前置 76 语义补测+6 smoke/模型共 246 条另表保留，不混入 core 分数。人工审核依据为研究者 anonymous 在聊天明确确认已看过并无问题，非第二审核者或代理独立审核。\n\n'
    t+='## 2. 固定协议与不确定性\n\n三模型 BF16/SDPA、greedy、thinking=false、最多 512 新 token；仅保留已生成内容，解析器不补全截断内容。query_value→value 唯一别名沿用，保留 strict 与 normalization。SELECT_MEDIA 与 ORACLE_MULTI 分开；所有单值条件统一 nullable。每次请求独立，只有一次正常 attempt，无错误答案/null/INVALID 重试。\n\n'
    t+='正确率分母为已返回响应，包含 INVALID；执行口径另含有 raw 的基础设施失败，缺 raw 的作业故障和中断只能在 Slurm 层描述，不能虚构逐请求尝试。未运行不当 false。CI 按底层 world 配对 bootstrap 2,000 次、seed=20260907，条件指标对完整 cohort 重采样再算分母；退化区间不代表没有不确定性。主面板仅 7 个已暴露 discovery world，不支持总体泛化或模型规模因果结论。\n\n'
    t+='## 3. 分层条件测量\n\n| 模型 | 分层 | 条件 | 正确/返回 | world | 准确率 | 95% world-cluster CI |\n|---|---|---|---:|---:|---:|---|\n'
    chosen={'PRE_VALUE','ACTION_PARSE','POST_VALUE','TEXT_STATE_UPDATE','JOINT_STATE','SELECT_MEDIA','ORACLE_SINGLE','ORACLE_MULTI','ORACLE_SHAM','CLAIM_MEDIA','CLAIM_ORACLE','ORACLE_MISSING_VALUE','CLAIM_ORACLE_MISSING','OBJECT_VALUE','JOINT_OBJECT','SELECT_MEDIA_OBJECT'}
    for r in condition:
        if r['condition'] in chosen: t+=f'| {r["model"]} | {r["stratum"]} | {r["condition"]} | {r["N_correct"]}/{r["N_responses"]} | {r["contributing_worlds"]} | {fmt(r["estimate"])} | {fmt(r["ci95_low"])}–{fmt(r["ci95_high"])} |\n'
    t+='\n每行条件、覆盖与区间限制见 [完整条件表](condition_summary.csv)，[动作组件与两种 JOINT 顺序](component_and_joint_summary.csv)另列；实际题目/响应/评分见 [全部逐请求表](03_CORE_RESPONSES_WITH_PROMPTS.csv)。L1 不是 PRE/POST 任务，不能混同解释。\n\n'
    t+='## 4. 状态选择、联合报告和匹配控制\n\n| 模型 | 分层 | 选择条件 | target pair 全对 | world | 95% CI |\n|---|---|---|---:|---:|---|\n'
    for r in pairs: t+=f'| {r["model"]} | {r["stratum"]} | {r["condition"]} | {int(r["numerator"])}/{int(r["denominator"])} | {r["cohort_worlds"]} | {fmt(r["ci95_low"])}–{fmt(r["ci95_high"])} |\n'
    t+='\n完整/反向/恒值/NULL/INVALID 模式见 [target-pair 表](target_pair_summary.csv)，两种 JOINT 顺序与逐 world 值见 [诊断矩阵](02_A1_FAILURE_MATRIX.csv)。Oracle 成功只约束显式查表条件，不排除媒体条件下选择/重算问题；独立请求答对不证明错误运行内部知道答案。\n\n'
    t+='[匹配控制逐对](04_MATCHED_CONTROLS.csv)保留救回、破坏、无变化、净差、token 长度差；[匹配汇总及 CI](matched_control_summary.csv)保留 MULTI−SHAM 非目标值命中净差、SHAM−MULTI 准确率差和 d1/d2 tracking 的两条基线。符号 D2 是 SYMBOLIC_CONTROL_ONLY，不冒充原场景真值。target flip 改变正确目标，不当成修复性 rescue 干预。\n\n'
    t+='## 5. Claim 比较、条件子集与反例\n\n[分类型 claim 指标](claim_summary.csv)和 [S/C/U 混淆](claim_confusion.csv)分别报告 target-match、other-state、neither-state 与缺目标条件；不得忽略完整表的 1:2 S/C 比例。neither 固定为 max(a,b)+1，数值大小不平衡，不靠能拒绝它单独证明选择机制。\n\n'
    t+='[条件指标](conditional_summary.csv)区分模型自己的资格子集与三模型共同子集，包括 PRE+动作正确后的 POST 失败、各 JOINT 顺序/双顺序正确后的 SELECT 失败，以及目标值正确后的 claim 错误。每项保留分母、贡献 world 与空分母 bootstrap 比例。NULL/INVALID 和明确错误值仍在逐样本表中区分。\n\n'
    t+='[来源值/动作分布](l4_value_operation_distribution.csv)及 [恒值 0/1 基线](constant_value_baselines.csv)用于披露 1→0 等常见模板捷径。[自报前提转移一致性](self_reported_transition.csv)不是 gold 正确性或同一内部状态的证据。无图控制本轮未取得额外资格，动作措辞捷径仍未排除。全部反例与成功案例均保留在逐请求表，不只提交支持某一路线的案例。\n\n'
    t+='## 6. 下一阶段候选：建议而非机制结论\n\n'
    if not routes: t+='主探索模型 9B 暂无满足预先候选规则的事件；不据此制造更难题或强行选择机制。\n\n'
    else:
        t+='9B 描述性支持数量如下；频次排序不是统计门槛，也不自动批准下一阶段。\n\n| 候选 | 支持 world/7 | 95% CI | world 证据 |\n|---|---:|---|---|\n'
        for r in routes: t+=f'| {r["candidate"]} | {int(r["numerator"])}/{int(r["denominator"])} | {fmt(r["ci95_low"])}–{fmt(r["ci95_high"])} | '+', '.join(r['worlds'])+' |\n'
        t+='\n目前最值得优先人工检查的描述性候选：'+routes[0]['candidate']+'；仍需核对其具体条件、反例及 [候选分布表](candidate_summary.csv)，不能称其内部机制已成立。\n\n'
    t+='已测量排除的是本轮可检测的输入/输出错位、target-only 视觉变化和未批准字段适配；只限已验收路径。未普遍排除视觉证据充分性、指令理解、动作文本捷径、独立请求重算、位置/上下文影响、claim 接受偏置和接口效应。若出现 neither-state 接受，仅在那些 world/model 上排除“全部错误都只因选择另一合法状态”这一完整解释，不排除混合机制。\n\n'
    t+='对更新候选，可证伪观察是在等信息、同目标的匹配条件下差异消失；对选择候选，可证伪观察是差异可由重算/上下文改变解释而非目标切换；对比较候选，可证伪观察是同信息条件的取值并不稳定；对缺目标借值候选，可证伪观察是效应完全由缺失语义或命名解释。这里只提出待检验预测，不运行新增控制。\n\n'
    t+='最终科学状态：'+decision['scientific_status']+'；建议：'+decision['recommendation']+'。本阶段停止，不进入白盒、hidden-state、训练、confirmation、test 或新增模型。\n\n'
    t+='## 7. 归档与复现\n\n[验收与预算](06_ACCEPTANCE_AND_PROTOCOL.json)、[下一步决策](08_NEXT_STAGE_DECISION.json)、[原始响应索引](raw_response_index.csv)、[来源索引](SOURCE_INDEX.csv)。来源索引中的绝对路径仅服务器可用；服务器保留完整 raw/token、实际 processor 提示/视觉 hash、私有 gold、代码快照和 Slurm 记录。完整复现命令见 resources/core_submissions.json 与 analysis_v1/job.sh；重建/评分不授权重跑已有预测。\n'
    return t


if __name__=='__main__': main()
