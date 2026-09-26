"""Read-only historical closure. CPU only; never write under the historical root."""
from collections import defaultdict,Counter
from v2_common import *
from state_contracts import Program,Action

def decode(s):return json.loads(s) if s else None
def w0():
    out=ROOT/'W0';src=OLD_ROOT/'batches/B1';panels=list(rows(src/'private_gold/world_panel.jsonl'))
    worlds=sorted({p['world_cluster_id'] for p in panels},key=lambda w:digest([SEED,'SSM_V2_SPLIT',w]))
    splits={w:('LOCALIZE' if i<round(.6*len(worlds)) else 'SELECT') for i,w in enumerate(worlds)}
    save(out/'WORLD_PARTITION.json',dict(partition=splits,seed=SEED,rule='rank sha256([seed, SSM_V2_SPLIT, world]); first round(0.6*N) LOCALIZE',
        historical_exposure='All are previously exposed SSM discovery materials, including old LOCKED_EVAL. New SELECT is a patch-selection holdout only, NOT fresh confirmation/test.',
        old_memberships={p['world_cluster_id']:p['split'] for p in panels}))
    table=[];refs=[entry(src/'private_gold/world_panel.jsonl')];indices=[]
    for m in MODELS:
        path=next((src/'scores'/m).glob('snapshot_*/logical_scores.csv'));rr=csvrows(path);refs.append(entry(path))
        ix={(r['world_cluster_id'],r['sequence'],r['condition']):r for r in rr}
        for p in panels:
            w=p['world_cluster_id'];seq=p['sequence'];pr=p['program'];prog=Program(pr['s0'],Action(**pr['a1']),Action(**pr['a2']),pr['source_type'])
            assert (prog.s1,prog.s2)==(p['s1'],p['s2'])
            r=dict(model=m,world_cluster_id=w,sequence_id=seq,split=splits[w],historical_split=p['split'],gold_s0=prog.s0,gold_s1=prog.s1,gold_s2=prog.s2,
                   action_1=pr['a1'],action_2=pr['a2'],protected_gold=p['protected'],source_graphs=p['source_graphs'],source_facts=p['source_facts'])
            for cond in ['B01','B02','B03','B05','B06','B07','B08','B09','B10','B11','B12','B15','B16','B17','PROTECTED_PRE_SUPPLEMENT']:
                x=ix[(w,'SHARED' if cond=='PROTECTED_PRE_SUPPLEMENT' else seq,cond)];k=cond.lower()
                r.update({k+'_pred':decode(x['prediction']),k+'_correct':x['content_correct']=='True' if x['execution_status']=='RETURNED' else None,
                          k+'_status':x['execution_status'],k+'_parser':x['normalized_status'],k+'_request_id':x['request_id'],k+'_raw':decode(x['raw'])})
                indices.append(dict(model=m,world_cluster_id=w,sequence_id=seq,condition=cond,request_id=x['request_id'],raw=decode(x['raw'])))
            cats=[];b1=r['b01_correct'];b2=r['b02_correct'];b5=r['b05_correct']
            if b2 is True and b1 is False and b5 is True:cats.append('A_REPORTABLE_NOT_RELIABLY_UTILIZED_S0')
            if b2 is False and b1 is False and b5 is True:cats.append('B_INITIAL_EXTRACTION_CANDIDATE')
            if b2 is True and b1 is True:cats.append('C_SUCCESS_CONTROL')
            if b2 is False and b1 is True:cats.append('D_COUNTEREXAMPLE')
            if b1 is False and b5 is False:cats.append('E_EXPLICIT_S0_NONRESCUE')
            r['cohorts']=cats or ['UNRESOLVED_MISSING'];r['invalid_or_null_conditions']=[k for k in ['b01','b02','b05'] if r[k+'_parser']!='VALID' or r[k+'_pred']=={'value':None}]
            r['primary_i1_eligible']=not r['invalid_or_null_conditions'] and 'A_REPORTABLE_NOT_RELIABLY_UTILIZED_S0' in cats
            for cond in ['b01','b06']:
                pred=r[cond+'_pred'];value=pred.get('value') if isinstance(pred,dict) else None
                sig=prog.signatures(value) if r[cond+'_parser']=='VALID' else ['INVALID']
                if type(value) is int:
                    extras={'A2_ON_S0':None,'A1_REPEATED_ON_S1':None,'SHAM_S1_VALUE':prog.s1}
                    for k,act,initial in [('A2_ON_S0',prog.a2,prog.s0),('A1_REPEATED_ON_S1',prog.a1,prog.s1)]:
                        try:extras[k]=act.apply(initial)
                        except ValueError:pass
                    sig=[s for s in sig if s!='OTHER_INTEGER']+[k for k,v in extras.items() if v is not None and v==value]
                    sig=sig or ['OTHER_INTEGER']
                r[cond+'_numeric_signatures']=sig;r[cond+'_numeric_class']='AMBIGUOUS_NUMERIC_PATTERN' if len(sig)>1 else sig[0]
            table.append(r)
    csvsave(out/'W0_B1_CASE_MATRIX.csv',table);save(out/'cases.jsonl',table,'jsonl');save(out/'RAW_RESPONSE_INDEX.jsonl',indices,'jsonl')
    metrics=[]
    for m in MODELS:
        rs=[r for r in table if r['model']==m]
        tests=[('B01_WRONG_GIVEN_B02_CORRECT',lambda r:r['b02_correct'] is True,lambda r:r['b01_correct'] is False),
               ('B05_RESCUE_GIVEN_B02_CORRECT_B01_WRONG',lambda r:r['b02_correct'] is True and r['b01_correct'] is False,lambda r:r['b05_correct'] is True),
               ('B06_RESCUE_GIVEN_B03_CORRECT_B01_WRONG',lambda r:r['b03_correct'] is True and r['b01_correct'] is False,lambda r:r['b06_correct'] is True)]
        for name,cond,value in tests:metrics.append(dict(model=m,metric=name,**cluster_ci([dict(world_cluster_id=r['world_cluster_id'],value=int(value(r))) for r in rs if cond(r)])))
    csvsave(out/'CONDITIONAL_METRICS.csv',metrics)
    save(out/'ACCEPTANCE.json',dict(status='COMPLETE',rows=len(table),worlds=len(worlds),models=MODELS,historical_source_refs=refs,
        matrix=entry(out/'W0_B1_CASE_MATRIX.csv'),raw_index=entry(out/'RAW_RESPONSE_INDEX.jsonl'),
        cohorts={m:dict(Counter(t for r in table if r['model']==m for t in r['cohorts'])) for m in MODELS},
        not_internal_S0_proof=True,source_files_unchanged=all(sha(r['path'])==r['sha256'] for r in refs)))
    print(json.dumps(load(out/'ACCEPTANCE.json')),flush=True)

def w2():
    out=ROOT/'W2';src=OLD_ROOT/'i2_interchange_v1';inp=src/'reports/snapshot_8201958/ALL_RAW_RESPONSES.jsonl';source=entry(inp)
    table=[];missing=[]
    def get(candidates,value):
        matches=[r['logprob'] for r in candidates if json.loads(r['answer'])=={'value':value}]
        assert len(matches)<=1
        return matches[0] if matches else None
    for r in rows(inp):
        rec,g=r['record'],r['gold'];t=rec['trial'];status=rec['status'];base=r.get('baseline',{}).get('normalized',{}).get('normalized',{})
        norm=rec.get('normalized',{}).get('normalized',{});pred=norm.get('component_values',{}).get('value');bp=base.get('component_values',{}).get('value')
        row=dict(trial_id=t['trial_id'],pair_id=t['base_pair_id'],world_cluster_id=t['cluster_id'],control=t['control'],depth=t['depth'],anchor=t['anchor'],status=status,
            raw_ref=entry(src/'raw/qwen35_9b'/f'shard_{t["shard"]:03}/trials'/(t['trial_id']+'.json')),baseline=bp,prediction=pred,
            cf=g['expected_counterfactual'],original_gold=g['recipient_final_gold'],donor_final=g['donor_final_gold'],donor_s1=g['donor_s1'])
        if status!='RETURNED':missing.append(row);table.append(row);continue
        cs=rec['candidate_scores'];un=cs['unpatched'];pa=cs['patched']
        for name,key in [('cf','expected_counterfactual'),('original_gold','recipient_final_gold'),('donor_final','donor_final_gold'),('donor_s1','donor_s1')]:
            l0,l1=get(un,g[key]),get(pa,g[key]);row[name+'_lp_before']=l0;row[name+'_lp_after']=l1
            row['delta_'+name+'_lp']=l1-l0 if l0 is not None and l1 is not None else None
        row.update(free_answer_changed=pred!=bp or norm.get('status')!=base.get('status'),cf_hit=norm.get('status')=='VALID' and pred==g['expected_counterfactual'],
                   donor_final_copy=norm.get('status')=='VALID' and pred==g['donor_final_gold'],donor_s1_copy=norm.get('status')=='VALID' and pred==g['donor_s1'],
                   null=norm.get('status')=='VALID' and pred is None,invalid=norm.get('status')!='VALID')
        table.append(row)
    csvsave(out/'I2_LOGPROB_DIAGNOSTICS.csv',table);csvsave(out/'TECHNICAL_GAPS.csv',missing)
    groups=defaultdict(list)
    for r in table:
        if r['status']=='RETURNED':groups[r['control']].append(r)
    summary=[]
    for control,rs in groups.items():
        for metric in ['delta_cf_lp','delta_original_gold_lp','delta_donor_final_lp','delta_donor_s1_lp','free_answer_changed','cf_hit','donor_final_copy','donor_s1_copy']:
            summary.append(dict(control=control,metric=metric,**cluster_ci(rs,value_key=metric)))
    csvsave(out/'GROUP_RESULTS.csv',summary)
    primary={(r['pair_id'],r['depth']):r for r in table if r['control']=='PRIMARY' and r['anchor']=='P_CHECKPOINT'}
    comparisons=[]
    for control,rs in groups.items():
        if control in ['PRIMARY','SAME_DONOR_DIFFERENT_A2']:continue
        matched=[]
        for r in rs:
            pr=primary.get((r['pair_id'],r['depth']))
            # Only compare identical candidate values, never different counterfactual targets.
            if pr and pr['status']=='RETURNED' and pr['cf']==r['cf'] and r.get('delta_cf_lp') is not None and pr.get('delta_cf_lp') is not None:
                matched.append(dict(world_cluster_id=r['world_cluster_id'],value=pr['delta_cf_lp']-r['delta_cf_lp']))
        comparisons.append(dict(control=control,metric='primary_checkpoint_minus_control_same_CF_logprob',**cluster_ci(matched)))
    csvsave(out/'MATCHED_CONTROLS.csv',comparisons)
    primaryrows=groups['PRIMARY'];point=next(x for x in summary if x['control']=='PRIMARY' and x['metric']=='delta_cf_lp')
    save(out/'I2_CLOSURE.json',dict(status='CONTINUOUS_ANALYSIS_COMPLETE_TECHNICAL_GAPS_RETAINED',primary_returned=len(primaryrows),
        primary_cf_hits=sum(r['cf_hit'] for r in primaryrows),primary_delta_cf_lp=point,missing_controls=len(missing),
        conclusion='I2_SINGLE_TOKEN_S1_INTERCHANGE_NOT_SUPPORTED_AT_ARGMAX; continuous specificity requires matched-control interpretation',
        no_new_primary_trials=True,no_expanded_grid=True,source=source,source_unchanged=sha(inp)==source['sha256'],
        next='Diagnose the one cached/uncached disagreement without changing gold, output-selected retry, or primary panel; fill only after equivalence PASS.'))
    print(json.dumps(load(out/'I2_CLOSURE.json')),flush=True)

if __name__=='__main__':
    p=cli(__doc__);p.add_argument('--stage',choices=['w0','w2'],required=True);a=p.parse_args();context(a)
    {'w0':w0,'w2':w2}[a.stage]()
