"""Freeze new S0 donor triangle and protection queries before any I1 output."""
from collections import Counter
from v2_common import *

def main():
    a=cli(__doc__).parse_args();context(a);out=ROOT/'I1';src=OLD_ROOT/'batches/B1'
    cases=list(rows(ROOT/'W0/cases.jsonl'));partition=load(ROOT/'W0/WORLD_PARTITION.json')
    historical={r['request_id']:r for r in rows(src/'public_inputs/requests.jsonl')}
    selected=[r for r in cases if r['model']=='qwen35_9b' and any(c.startswith(('A_','B_','C_')) for c in r['cohorts'])]
    # Existing historical cases, not fresh holdout; all models' fixed worlds preserved for later functional tests.
    reqs={};gold={};panel=[];gaps=[]
    for c in selected:
        w,seq=c['world_cluster_id'],c['sequence_id'];ids={};cohort=c['cohorts'][0].split('_')[0]
        b05=historical[c['b05_request_id']];oracle=f'ORACLE INITIAL FACT: the target count in S0 is exactly {c["gold_s0"]}.\n'
        assert oracle in b05['payload']['text']
        # Similar lexical length, same numerical value and insertion region, explicitly unrelated.
        sham=f'UNRELATED REGISTER: its bookkeeping value is exactly {c["gold_s0"]}, not the scene state.\n'
        for q,cond,expected,target in [('S2','b01',c['gold_s2'],'S2'),('S0','b15',c['gold_s0'],'S0'),('PROTECTED','b16',c['protected_gold'],'S2')]:
            original=historical[c[cond+'_request_id']];text=original['payload']['text']
            assert text.count('The following two actions')==1
            info=text.replace('The following two actions',oracle+'The following two actions',1)
            irrelevant=text.replace('The following two actions',sham+'The following two actions',1)
            if q=='S2':assert info==b05['payload']['text']
            ids[q]={}
            for kind,txt in [('BASE',text),('INFORMATIVE_S0',info),('SAME_VALUE_SHAM',irrelevant)]:
                r=request(original,'I1',kind+'_'+q,txt,target);r['split']=c['split'];r['models']=['qwen35_9b']
                r['model_independent_request_hash']=digest({k:v for k,v in r.items() if k!='model_independent_request_hash'})
                rid=r['request_id'];ids[q][kind]=rid;reqs[rid]=r
                gold[rid]=dict(request_id=rid,expected=dict(value=expected),world_cluster_id=w,query=q,source_case=entry(ROOT/'W0/cases.jsonl'),
                               s0=c['gold_s0'],s1=c['gold_s1'],s2=c['gold_s2'],protected=c['protected_gold'])
        panel.append(dict(case_id=digest([RUN,w,seq])[:24],world_cluster_id=w,sequence_id=seq,split=c['split'],historical_split=c['historical_split'],
            cohort=cohort,primary_eligible=c['primary_i1_eligible'],invalid_or_null_conditions=c['invalid_or_null_conditions'],
            program=dict(s0=c['gold_s0'],a1=c['action_1'],a2=c['action_2']),s1=c['gold_s1'],s2=c['gold_s2'],protected=c['protected_gold'],
            source_graphs=c['source_graphs'],source_facts=c['source_facts'],requests=ids,historical_raw={k:c[k+'_raw'] for k in ['b01','b02','b05','b15','b16']},
            old_wrong_prediction=c['b01_pred']))
    for p in panel:
        opts=[d for d in panel if d['cohort']=='C' and d['split']==p['split'] and d['world_cluster_id']!=p['world_cluster_id']
              and d['sequence_id']==p['sequence_id'] and d['program']['a1']['kind']==p['program']['a1']['kind'] and d['program']['a2']['kind']==p['program']['a2']['kind']]
        opts.sort(key=lambda d:(d['s2']==p['s2'],digest([SEED,'SUCCESS_DONOR',p['case_id'],d['case_id']])))
        d=opts[0] if opts else None
        p['success_donor_case']=d['case_id'] if d else None
        p['success_donor_world']=d['world_cluster_id'] if d else None
        p['success_donor_requests']={q:d['requests'][q]['BASE'] for q in p['requests']} if d else {}
        p['donor_copy_identifiable']=d is not None and d['s2']!=p['s2']
        if not d:gaps.append(dict(case_id=p['case_id'],reason='NO_SAME_SPLIT_OTHER_WORLD_TEMPLATE_MATCHED_C_SUCCESS_DONOR',status='NOT_RUN_SUCCESS_DONOR'))
    positions=['P_CONTEXT_END','P_A1_END','P_A2_END','P_QUERY'];depths=[0,.15,.30,.45,.60,.72,.85,1]
    protocol=dict(run_id=RUN,primary_model='qwen35_9b',guide=entry(GUIDE),relative_depths=depths,anchors=positions,
        patch='ONE_ACTUAL_BLOCK_OUTPUT_TOKEN; full causal prefix replay every generated token; no cache',
        recipients='All frozen 9B Type A and B separately; null/invalid baseline cases retained and flagged, never credited as valid rescue',
        case_partition=partition,sham='New B07_MATCHED_V2 inserts same S0 value before actions; old B07 was S1 after A1 and is NOT reinterpreted.',
        success_donor='same new split + action kinds + sequence; other world; different final value preferred structurally then fixed hash; historical C eligibility only',
        independent_units='recipient world; donor-reuse connected components also reported; same-world sham primary contrast has no external donor dependence',
        technical_gate=dict(noop_tokens_exact=True,self_tokens_exact=True,cached_uncached_tokens_exact=True,score_max_abs_error=.5,
                            prompt_media_hash_exact=True,per_context_discrepancies='NOT_RUN_ENGINE_EQUIVALENCE_UNRESOLVED; no accuracy-based retry'),
        localize='8 depths x 4 anchors x 3 donor types per eligible A/B sequence. No scores from SELECT may choose candidates.',
        candidate_rule='Rank mean per-world informative-minus-sham correct logP on Type A LOCALIZE; positive mean only; top <=2 depth+anchor single-block windows; deterministic depth/anchor tiebreak.',
        protection='S0 and PROTECTED are independently processed queries with their own baselines and same-query donors; run both plus all C success cases at <=2 frozen candidate windows, before SELECT GO.',
        reverse='At frozen candidate windows only, B01 activation into B05 for A/B, with own baseline and self control.',
        select_gate=dict(min_independent_primary_worlds=8,informative_mean_gt=0,specific_effect_simultaneous_lower_ci_gt=0,
                         ci='Bonferroni 95% familywise across <=2 frozen windows; bootstrap recipient worlds',min_positive_world_fraction=.5,
                         max_baseline_correct_protected_damage=.10,max_baseline_correct_initial_damage=.10,max_success_damage=.10,
                         max_identifiable_donor_copy_fraction=.25,missing_controls='UNRESOLVED_NOT_PASS',
                         source='Conservative numerical operationalization of qualitative guide gate; frozen before outputs, not post-hoc thresholds.'),
        generation=dict(max_new_tokens=512,do_sample=False,enable_thinking=False,truncate='score retained content'),
        no_global_gpu_hour_cap=True,no_auto_training=True,I3='NOT_RUN_UNTIL_I1_SELECT_GO',cross_scale='NOT_RUN_UNTIL_MECHANISM_LOCK',
        hypotheses_can_fail=True)
    save(out/'manifest/PROTOCOL.json',protocol)
    save(out/'public_inputs/requests.jsonl',reqs.values(),'jsonl');save(out/'public_inputs/panel.jsonl',panel,'jsonl')
    save(out/'private_gold/requests.jsonl',gold.values(),'jsonl');save(out/'manifest/GAPS.jsonl',gaps,'jsonl')
    ws=sorted({p['world_cluster_id'] for p in panel if p['split']=='LOCALIZE' and p['cohort'] in ['A','B']},key=lambda w:digest([SEED,'I1_SHARD',w]))
    shards=[dict(shard=i,worlds=ws[i::8]) for i in range(8) if ws[i::8]]
    save(out/'manifest/shards.json',shards)
    tech_candidates=sorted([p for p in panel if p['split']=='LOCALIZE' and p['cohort']=='A'],key=lambda p:digest([SEED,'I1_TECH',p['case_id']]))
    save(out/'manifest/TECHNICAL_CASE.json',tech_candidates[0])
    save(out/'manifest/INPUT_LOCK.json',dict(status='FROZEN_BEFORE_I1_OUTPUTS',guide=entry(GUIDE),compiler=entry(__file__),
        public_inputs=[entry(out/n) for n in ['public_inputs/requests.jsonl','public_inputs/panel.jsonl','manifest/PROTOCOL.json','manifest/shards.json','manifest/TECHNICAL_CASE.json']],
        private_inputs=[entry(out/'private_gold/requests.jsonl')],historical_inputs=[entry(src/'public_inputs/requests.jsonl'),entry(ROOT/'W0/cases.jsonl'),entry(ROOT/'W0/WORLD_PARTITION.json')]))
    report=dict(status='INPUTS_FROZEN_RUNTIME_TECHNICAL_PENDING',requests=len(reqs),cases=len(panel),
        split_cohorts=dict(Counter(p['split']+'_'+p['cohort'] for p in panel)),shards=len(shards),
        localize_primary_patch_upper=sum(p['split']=='LOCALIZE' and p['cohort'] in ['A','B'] for p in panel)*96,
        protection_candidate_max=2,source_gold_not_model_guessed=True)
    save(out/'manifest/BUILD_ACCEPTANCE.json',report);print(json.dumps(report),flush=True)
if __name__=='__main__':main()
