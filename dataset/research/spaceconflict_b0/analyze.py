"""B0 deterministic, per-world paired analysis. Never starts any model job."""
from collections import Counter,defaultdict
from b0common import *
from b0score import score
stats=import_file(A1CODE/'analysis_v1/cluster_stats.py','b0_reused_world_stats')


def aggregate(data, fields, metrics, c):
    groups=defaultdict(list)
    for r in data: groups[tuple(r.get(k) for k in fields)].append(r)
    result=[]
    for key,rs in groups.items():
        cohort={r['underlying_world_id'] for r in rs}
        for metric in metrics:
            observations=[(r['underlying_world_id'],int(bool(r[metric])),1) for r in rs if r.get(metric) is not None]
            est=stats.estimate(observations,cohort,c['seed'],c['bootstrap_repetitions'])
            result.append(dict(zip(fields,key),metric=metric,requests_or_matched_units=len(rs),**est))
    return result


def compare(a,b,kind):
    fa=a.get('fact_pred'); fb=b.get('fact_pred')
    va=a.get('pred_verdict'); vb=b.get('pred_verdict')
    factmeasured=a.get('fact_present') and b.get('fact_present') and type(fa) is int and type(fb) is int
    verdictmeasured=a.get('verdict_present') and b.get('verdict_present')
    available=a['execution_status']=='RESPONDED' and b['execution_status']=='RESPONDED'
    pairedcorrect=available and a.get('correct') is not None and b.get('correct') is not None
    actual_order=(a.get('order_compliant') and b.get('order_compliant')) if kind=='FACT_FIRST_TO_VERDICT_FIRST' else None
    return dict(model=a['model'],underlying_world_id=a['underlying_world_id'],cohort=a['cohort'],comparison=kind,
        base_request_id=a['request_id'],control_request_id=b['request_id'],target=a['target'],claim_value=a['claim_value'],
        delta=a['delta'],operation=a['operation'],category=a['category'],wording=a['wording'],context=a['context'],
        base_fact=fa,control_fact=fb,base_verdict=va,control_verdict=vb,base_status=a['status'],control_status=b['status'],
        fact_shift=fa!=fb if factmeasured else None,verdict_flip=va!=vb if verdictmeasured else None,
        numeric_fact_comparison_available=bool(factmeasured),verdict_comparison_available=bool(verdictmeasured),
        rescue=(not a['correct'] and b['correct']) if pairedcorrect else None,
        harm=(a['correct'] and not b['correct']) if pairedcorrect else None,
        no_change=(a['correct']==b['correct']) if pairedcorrect else None,
        net_accuracy_delta=int(b['correct'])-int(a['correct']) if pairedcorrect else None,
        actual_order_pair_compliant=bool(actual_order) if actual_order is not None else None,
        actual_order_fact_shift=fa!=fb if factmeasured and actual_order else None,
        actual_order_verdict_flip=va!=vb if verdictmeasured and actual_order else None,
        self_consistency_changed=(a['self_consistency_violation']!=b['self_consistency_violation']) if a.get('self_consistency_violation') is not None and b.get('self_consistency_violation') is not None else None,
        same_media_hash=a.get('presentation_hash')==b.get('presentation_hash'),
        same_fact_gold=type(a['fact_gold']) is type(b['fact_gold']) and a['fact_gold']==b['fact_gold'],
        base_input_tokens=a.get('input_tokens'),control_input_tokens=b.get('input_tokens'),
        token_difference=(b['input_tokens']-a['input_tokens']) if a.get('input_tokens') is not None and b.get('input_tokens') is not None else None)


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('Score current B0 only; matched worlds/CI/report then STOP; no model calls'); return
    compute(); lock=load(root/'manifest/core_lock.json'); check_entries(lock['code'])
    if sha(root/'inputs/core/requests.jsonl')!=lock['inputs_sha256']: raise ValueError('INPUT_LOCK_MISMATCH')
    rr=list(rows(root/'inputs/core/requests.jsonl')); gg={g['request_id']:g for g in rows(root/'private_gold/core.jsonl')}
    panels=list(rows(root/'02_B0_PANEL_MANIFEST.jsonl')); all_rows=[]; index=[]; lookup={}; byid={}; counts={}
    if sha(root/'private_gold/core.jsonl')!=lock['private_gold_sha256']: raise ValueError('GOLD_LOCK_MISMATCH')
    for model in c['models']:
        directory=root/'raw/core'/model; compact=directory/'responses.jsonl'; raws={}
        if compact.exists():
            completion=load(directory/'completion.json'); check_entries([completion['responses_file']])
            raws={r['request_id']:r for r in rows(compact)}; index.append(entry(compact))
        elif directory.exists():
            for r in rr:
                path=directory/(r['request_id']+'.json')
                if path.is_file(): raws[r['request_id']]=load(path)
        if set(raws)-{r['request_id'] for r in rr}: raise ValueError('UNPLANNED_RESPONSE')
        for r in rr:
            g=gg[r['request_id']]; raw=raws.get(r['request_id']); p=score(raw,g)
            if raw and (raw['request_sha256']!=digest(r) or raw['lock_sha256']!=sha(root/'manifest/core_lock.json')): raise ValueError('RESPONSE_PROTOCOL_MISMATCH')
            row={k:v for k,v in r.items() if k not in ['payload','models']}
            row.update(g); row.update(p); row.update(model=model,underlying_world_id=r['underlying_world_id'],
                source_world_id=r['world_id'],execution_status='NOT_RUN' if raw is None else 'INFRA_FAILURE' if raw.get('infrastructure_error') else 'RESPONDED',
                raw_response=raw.get('raw_response') if raw else None,raw_path=str(directory/(r['request_id']+'.json')) if raw else None,
                actual_rendered_prompt=raw.get('actual_rendered_prompt') if raw else None,
                planned_text=r['payload']['text'],media=r['payload']['media'],
                input_tokens=raw.get('input_tokens') if raw else None,output_tokens=raw.get('output_tokens') if raw else None,
                finish_reason=raw.get('finish_reason') if raw else None,presentation_hash=raw.get('presentation_hash') if raw else None,
                raw_record=raw,neutral_repeat_stable=None)
            row['response_available']=row['execution_status']=='RESPONDED'
            row['invalid']=row['status']=='INVALID' if row['response_available'] else None
            row['null_fact']=row.get('fact_present') and row['fact_pred'] is None if row['response_available'] and r['schema']['kind']!='verdict' else None
            row['unsupported_acceptance']=row['pred_verdict']=='SUPPORTED' if row.get('verdict_present') and g['gold_verdict']=='CONTRADICTORY' else None
            all_rows.append(row); byid[model,r['request_id']]=row
            lookup[model,r['group_id'],r['condition'],r['target'],r['claim_value'],r['wording'],r['context'],r['order'],r['repeat'],r['evidence'],r['organization']]=row
        current=[r for r in all_rows if r['model']==model]
        counts[model]=dict(planned=len(current),responses=sum(r['response_available'] for r in current),
            invalid=sum(r['status']=='INVALID' for r in current),null_fact=sum(r.get('null_fact') is True for r in current),
            infrastructure=sum(r['status']=='INFRA_FAILURE' for r in current),not_run=sum(r['status']=='NOT_RUN' for r in current))
    def get(model,gid,cond,target,claim=None,w='W0',ctx='I1',order='',repeat=0,evidence='',organization=''):
        return lookup[model,gid,cond,target,claim,w,ctx,order,repeat,evidence,organization]
    pairs=[]
    for model in c['models']:
        for m in rows(root/'manifest/matched_pairs.jsonl'):
            pair=compare(byid[model,m['base_request_id']],byid[model,m['control_request_id']],m['comparison']); pair['match_id']=m['match_id']; pairs.append(pair)
    claimrows=[]
    for r in all_rows:
        if r['condition']!='FACT_CLAIM': continue
        m,gid,t,cv,w,ctx=r['model'],r['group_id'],r['target'],r['claim_value'],r['wording'],r['context']
        neutral=get(m,gid,'FACT_NEUTRAL',t,w=w,ctx=ctx); repeat=get(m,gid,'FACT_NEUTRAL',t,w=w,ctx=ctx,repeat=1)
        verdict=get(m,gid,'VERDICT_ONLY',t,cv,w,ctx)
        joint=get(m,gid,'FACT_VERDICT',t,cv,w,ctx,'FACT_FIRST')
        truefact=get(m,gid,'FACT_CLAIM',t,r['fact_gold'],w,ctx)
        numeric=neutral.get('fact_present') and r.get('fact_present') and type(neutral['fact_pred']) is int and type(r['fact_pred']) is int
        falsity=r['claim_type']!='target_match'; vp=verdict.get('verdict_present')
        repeatnum=neutral.get('fact_present') and repeat.get('fact_present') and type(neutral['fact_pred']) is int and type(repeat['fact_pred']) is int
        stable_correct=neutral.get('fact_correct') and repeat.get('fact_correct')
        cr={k:r[k] for k in ['model','group_id','underlying_world_id','cohort','target','wording','context','claim_value','delta','operation','category','source','source_family','source_values','fact_gold','claim_type']}
        cr.update(neutral_request_id=neutral['request_id'],neutral_repeat_request_id=repeat['request_id'],
            true_claim_fact_request_id=truefact['request_id'],claim_fact_request_id=r['request_id'],verdict_request_id=verdict['request_id'],joint_request_id=joint['request_id'],
            neutral_fact=neutral.get('fact_pred'),neutral_repeat_fact=repeat.get('fact_pred'),true_claim_fact=truefact.get('fact_pred'),claim_fact=r.get('fact_pred'),verdict=verdict.get('pred_verdict'),
            numeric_fact_comparison_available=bool(numeric),claim_fact_shift=(r['fact_pred']!=neutral['fact_pred']) if numeric else None,
            neutral_repeat_shift=(neutral['fact_pred']!=repeat['fact_pred']) if repeatnum else None,
            neutral_repeat_stable_correct=bool(stable_correct) if repeatnum else None,
            claim_attraction=(r['fact_pred']==cv) if numeric and falsity and neutral['fact_pred']!=cv else None,
            fact_corruption=bool(neutral['fact_correct'] and r['fact_pred']==cv) if numeric and falsity else None,
            verdict_follows_false_claim=(verdict['pred_verdict']=='SUPPORTED') if falsity and vp else None,
            stable_fact_wrong_verdict=bool(neutral['fact_correct'] and r['fact_correct'] and not verdict['verdict_correct']) if numeric and falsity and vp else None,
            same_run_dissociation=joint.get('same_run_fact_correct_verdict_wrong') if falsity else None,
            controlled_utilization_case=bool(stable_correct and r.get('fact_correct') and joint.get('same_run_fact_correct_verdict_wrong')) if numeric and falsity and joint.get('same_run_fact_correct_verdict_wrong') is not None else None,
            controlled_attraction_case=bool(stable_correct and r['fact_pred']==cv and verdict['pred_verdict']=='SUPPORTED') if numeric and falsity and vp else None)
        claimrows.append(cr)
    factorial=[]
    for m in c['models']:
        for p in panels:
            for target in ['PRE','POST']:
                other='POST' if target=='PRE' else 'PRE'
                row=dict(model=m,group_id=p['group_id'],underlying_world_id=p['underlying_world_id'],cohort=p['cohort'],target=target,
                         target_value=p['values'][target],other_value=p['values'][other],operation=p['operation'],category=p['category'])
                for evidence in ['COMPLETE','MISSING']:
                    for org in ['CORE_NARRATIVE','INDEPENDENT_TABLE']:
                        r=get(m,p['group_id'],'MISSING_FACTORIAL',target,evidence=evidence,organization=org)
                        prefix=evidence.lower()+'_'+org.lower()
                        row.update({prefix+'_request_id':r['request_id'],prefix+'_value':r.get('fact_pred'),prefix+'_status':r['status'],
                            prefix+'_correct':r['fact_correct'],prefix+'_borrow_other':r['fact_pred']==p['values'][other] if r.get('fact_present') else None,
                            prefix+'_null':r['fact_pred'] is None if r.get('fact_present') else None})
                cells=[row[k+'_correct'] for k in ['complete_core_narrative','missing_core_narrative','complete_independent_table','missing_independent_table']]
                if all(v is not None for v in cells):
                    cn,mn,ct,mt=map(int,cells)
                    row.update(narrative_missing_penalty=cn-mn,table_missing_penalty=ct-mt,missing_table_rescue=mt-mn,
                               table_by_missing_interaction=(mt-ct)-(mn-cn))
                else:
                    row.update(narrative_missing_penalty=None,table_missing_penalty=None,missing_table_rescue=None,table_by_missing_interaction=None)
                factorial.append(row)
    # All response/invalid/null/NOT_RUN rows remain available, not only interesting examples.
    union_csv(root/'03_B0_RAW_RESPONSES_WITH_PROMPTS.csv',all_rows)
    union_csv(root/'tables/b0_same_run_fact_verdict.csv',[r for r in all_rows if r['condition']=='FACT_VERDICT'])
    union_csv(root/'tables/b0_claim_conditioned_fact.csv',claimrows)
    union_csv(root/'tables/b0_intervention_ablation.csv',[r for r in pairs if r['comparison']=='NO_INTERVENTION_TO_INTERVENTION'])
    union_csv(root/'tables/b0_matched_controls.csv',pairs)
    union_csv(root/'tables/b0_missing_target_factorial.csv',factorial)
    save(root/'manifest/raw_response_index.json',index)
    measures=['fact_correct','verdict_correct','same_run_fact_correct_verdict_wrong','self_consistency_violation','unsupported_acceptance','invalid','null_fact','response_available']
    summary=aggregate(all_rows,['model','cohort','condition','context','wording','order'],measures,c)
    union_csv(root/'tables/b0_model_summary.csv',summary)
    numeric=[]
    for strat in ['operation','target','fact_gold','delta','category','source_family']:
        result=aggregate([r for r in all_rows if r['claim_value'] is not None],['model','cohort','condition',strat],measures[:5],c)
        numeric.extend(dict(row,stratification=strat) for row in result)
        claims=aggregate([r for r in claimrows if r['claim_type']!='target_match'],['model','cohort',strat],
            ['claim_attraction','fact_corruption','claim_fact_shift'],c)
        numeric.extend(dict(row,stratification=strat,condition='FACT_CLAIM') for row in claims)
    union_csv(root/'tables/b0_numeric_offset_summary.csv',numeric)
    claims_summary=aggregate(claimrows,['model','cohort','claim_type','context','wording'],
        ['claim_fact_shift','claim_attraction','fact_corruption','stable_fact_wrong_verdict','neutral_repeat_shift','controlled_utilization_case','controlled_attraction_case'],c)
    union_csv(root/'tables/b0_claim_conditioned_summary.csv',claims_summary)
    matched_summary=aggregate(pairs,['model','cohort','comparison'],['fact_shift','verdict_flip','rescue','harm','no_change','actual_order_fact_shift','actual_order_verdict_flip','self_consistency_changed'],c)
    # Paired signed differences are not booleans; explicitly use their numeric values.
    for key,rs in __import__('itertools').groupby(sorted(pairs,key=lambda r:(r['model'],r['cohort'],r['comparison'])),key=lambda r:(r['model'],r['cohort'],r['comparison'])):
        rs=list(rs); est=stats.estimate([(r['underlying_world_id'],r['net_accuracy_delta'],1) for r in rs if r['net_accuracy_delta'] is not None],{r['underlying_world_id'] for r in rs},c['seed'],c['bootstrap_repetitions'])
        matched_summary.append(dict(zip(['model','cohort','comparison'],key),metric='net_accuracy_delta',requests_or_matched_units=len(rs),**est))
    union_csv(root/'tables/b0_matched_control_summary.csv',matched_summary)
    fm=[k for k in factorial[0] if k.endswith(('_correct','_borrow_other','_null'))] if factorial else []
    union_csv(root/'tables/b0_missing_target_summary.csv',aggregate(factorial,['model','cohort'],fm,c))
    contrasts=[]
    for model in c['models']:
        for cohort in ['B0_A','B0_B','ALL']:
            ff=[r for r in factorial if r['model']==model and (cohort=='ALL' or r['cohort']==cohort)]
            for metric in ['narrative_missing_penalty','table_missing_penalty','missing_table_rescue','table_by_missing_interaction']:
                result=stats.estimate([(r['underlying_world_id'],r[metric],1) for r in ff if r[metric] is not None],
                    {r['underlying_world_id'] for r in ff},c['seed'],c['bootstrap_repetitions'])
                contrasts.append(dict(model=model,cohort=cohort,metric=metric,**result))
    union_csv(root/'tables/b0_missing_target_contrasts.csv',contrasts)
    from decision import finalize
    finalize(c,root,panels,all_rows,claimrows,pairs,factorial,counts,summary,claims_summary,matched_summary)


if __name__=='__main__': main()
