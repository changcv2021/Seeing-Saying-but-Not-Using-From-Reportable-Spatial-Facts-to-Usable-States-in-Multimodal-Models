"""Predeclared LOCALIZE-only selection and independently gated SELECT evidence."""
from collections import defaultdict,Counter
from v2_common import *

def diagnostics(stage):
    out=ROOT/'I1';panel={p['case_id']:p for p in rows(out/'public_inputs/panel.jsonl')};result=[];refs=[]
    for directory in sorted((out/'raw'/stage).glob('shard_*')):
        ac=directory/'EXECUTION_ACCEPTANCE.json'
        if not ac.exists():continue
        acc=load(ac);check(acc['index']);refs.append(entry(ac))
        for item in rows(acc['index']['path']):
            check(item['raw']);raw=load(item['raw']['path']);t=raw['trial'];case=panel[t['case_id']]
            base=load(t['baseline_ref']['path']);bn=base['normalized']['normalized'];bv=bn.get('component_values',{}).get('value')
            gold={'S2':case['s2'],'S0':case['program']['s0'],'PROTECTED':case['protected']}[t['query']]
            baseline_correct=bn['status']=='VALID' and bv==gold;norm=raw.get('normalized',{}).get('normalized',{});pred=norm.get('component_values',{}).get('value')
            returned=raw['status']=='RETURNED';correct=norm.get('status')=='VALID' and pred==gold if returned else None
            cs=raw.get('candidate_scores',{})
            def lp(kind):
                matches=[s['logprob'] for s in cs.get(kind,[]) if json.loads(s['answer'])=={'value':gold}]
                assert len(matches)<=1;return matches[0] if matches else None
            l0,l1=lp('unpatched'),lp('patched')
            donor_value=raw.get('score_only_values',{}).get('donor_final')
            result.append(dict(**t,status=raw['status'],gold=gold,baseline_prediction=bv,prediction=pred,baseline_correct=baseline_correct,correct=correct,
                rescue=(not baseline_correct and correct) if returned else None,harm=(baseline_correct and not correct) if returned else None,
                delta_correct_lp=l1-l0 if l1 is not None and l0 is not None else None,donor_value=donor_value,
                donor_copy_identifiable=donor_value is not None and donor_value!=gold,
                donor_copy=pred==donor_value and donor_value!=gold if returned and donor_value is not None else None,
                null=norm.get('status')=='VALID' and pred is None if returned else None,invalid=norm.get('status')!='VALID' if returned else None,
                raw_response=raw.get('response',{}).get('raw_response'),raw=item['raw']))
    return result,refs

def specificity(result,split):
    groups=defaultdict(dict)
    for r in result:
        if r['split']==split and r['cohort']=='A' and r['query']=='S2' and r['status']=='RETURNED' and r['eligibility']=='HISTORICAL_VALID_COHORT':
            groups[(r['case_id'],r['depth'],r['anchor'])][r['donor_kind']]=r
    matched=[]
    for (cid,depth,anchor),rs in groups.items():
        if not {'INFORMATIVE_S0','SAME_VALUE_SHAM'}<=set(rs):continue
        r,s=rs['INFORMATIVE_S0'],rs['SAME_VALUE_SHAM']
        if r['delta_correct_lp'] is None or s['delta_correct_lp'] is None:continue
        matched.append(dict(case_id=cid,world_cluster_id=r['world_cluster_id'],depth=depth,anchor=anchor,
            value=r['delta_correct_lp']-s['delta_correct_lp'],informative_delta=r['delta_correct_lp'],sham_delta=s['delta_correct_lp'],
            informative_raw=r['raw'],sham_raw=s['raw']))
    summary=[]
    for depth,anchor in sorted({(r['depth'],r['anchor']) for r in matched}):
        rs=[r for r in matched if r['depth']==depth and r['anchor']==anchor]
        # Mechanism window ranking gives each independent world equal weight.
        byworld=defaultdict(list)
        for r in rs:byworld[r['world_cluster_id']].append(r['value'])
        worldvalues=[dict(world_cluster_id=w,value=sum(v)/len(v)) for w,v in byworld.items()]
        summary.append(dict(depth=depth,anchor=anchor,sequence_pairs=len(rs),**cluster_ci(worldvalues)))
    return matched,summary

def main():
    p=cli(__doc__);p.add_argument('--stage',choices=['localize','selected'],required=True);a=p.parse_args();context(a);out=ROOT/'I1'
    result,refs=diagnostics(a.stage);expected=len(load(out/'manifest/shards.json')) if a.stage=='localize' else 8
    dest=out/'reports'/a.stage/('snapshot_'+os.environ['SLURM_JOB_ID']);csvsave(dest/'DIAGNOSTIC_MATRIX.csv',result)
    counts=dict(Counter(r['status'] for r in result));complete=len(refs)==expected
    save(dest/'ACCEPTANCE.json',dict(status='COMPLETE_WITH_RETAINED_GAPS' if complete else 'PARTIAL',finished_shards=len(refs),expected_shards=expected,counts=counts,sources=refs))
    split='LOCALIZE' if a.stage=='localize' else 'SELECT';matched,summary=specificity(result,split)
    csvsave(dest/'MATCHED_SPECIFICITY.csv',matched);csvsave(dest/'WINDOW_SUMMARY.csv',summary)
    if a.stage=='localize':
        if not complete:return
        qualified=[s for s in summary if s['mean'] is not None and s['mean']>0]
        qualified.sort(key=lambda s:(-s['mean'],s['depth'],s['anchor']));windows=[dict(depth=s['depth'],anchor=s['anchor'],localize=s) for s in qualified[:2]]
        save(out/'selection/CANDIDATE_LOCK.json',dict(status='CANDIDATES_FROZEN' if windows else 'STOP_NO_POSITIVE_LOCALIZE_SPECIFICITY',windows=windows,
            source=entry(dest/'WINDOW_SUMMARY.csv'),source_shards=refs,runtime_lock=entry(out/'manifest/RUNTIME_LOCK.json'),
            selector=entry(__file__),selected_before_SELECT=True,primary='TYPE_A_ONLY_WORLD_WEIGHTED',model='qwen35_9b'))
        return
    # No permissive GO on missing evidence: collateral damage and independent worlds required.
    gates=[];windows=load(out/'selection/CANDIDATE_LOCK.json')['windows']
    for window in windows:
        depth,anchor=window['depth'],window['anchor'];rs=[r for r in result if r['depth']==depth and r['anchor']==anchor and r['split']=='SELECT']
        info=[r for r in rs if r['cohort']=='A' and r['query']=='S2' and r['donor_kind']=='INFORMATIVE_S0' and r['status']=='RETURNED']
        ms=[r for r in matched if r['depth']==depth and r['anchor']==anchor];specific=next((s for s in summary if s['depth']==depth and s['anchor']==anchor),{})
        # 97.5% marginal interval for two-window Bonferroni familywise 95% (95% when one).
        import numpy as np
        byworld=defaultdict(list)
        for r in ms:byworld[r['world_cluster_id']].append(r['value'])
        vals=np.array([sum(x)/len(x) for x in byworld.values()]);lower=None
        if len(vals)>1:
            rng=np.random.default_rng(SEED);b=vals[rng.integers(len(vals),size=(5000,len(vals)))].mean(1)
            lower=float(np.quantile(b,.025/len(windows)))
        checks=dict(complete_execution=complete,all_matched_controls_returned=bool(rs) and all(r['status']=='RETURNED' for r in rs),enough_primary_worlds=len(vals)>=8,
            positive_specificity=lower is not None and lower>0,positive_informative=bool(info) and sum(r['delta_correct_lp'] for r in info)/len(info)>0,
            positive_world_fraction=bool(len(vals)) and float((vals>0).mean())>=.5)
        harms={}
        for name,query,cohort in [('initial','S0',None),('protected','PROTECTED',None),('success','S2','C')]:
            group=[r for r in rs if r['query']==query and (cohort is None or r['cohort']==cohort) and r['donor_kind']=='INFORMATIVE_S0' and r['status']=='RETURNED' and r['baseline_correct']]
            rate=sum(r['harm'] for r in group)/len(group) if group else None
            harms[name]=dict(n=len(group),worlds=len({r['world_cluster_id'] for r in group}),rate=rate,ci=cluster_ci([dict(world_cluster_id=r['world_cluster_id'],value=int(r['harm'])) for r in group]))
            checks[name+'_damage_bounded']=rate is not None and rate<=.1
        copyrows=[r for r in rs if r['query']=='S2' and r['donor_kind']=='SUCCESS_DONOR' and r['status']=='RETURNED' and r['donor_copy_identifiable']]
        copyrate=sum(r['donor_copy'] for r in copyrows)/len(copyrows) if copyrows else None
        checks['donor_copy_bounded']=copyrate is not None and copyrate<=.25
        gates.append(dict(window=window,status='GO' if all(checks.values()) else 'STOP_OR_UNRESOLVED',checks=checks,
            matched_specificity=specific,familywise_specificity_lower=lower,collateral=harms,copy_rate=copyrate,copy_n=len(copyrows)))
    save(out/'selection/SELECT_DECISION.json',dict(status='GO' if any(g['status']=='GO' for g in gates) else 'NO_GO',windows=gates,
        report=entry(dest/'DIAGNOSTIC_MATRIX.csv'),I3='ELIGIBLE_FOR_FROZEN_COMPONENT_PLAN' if any(g['status']=='GO' for g in gates) else 'NOT_RUN_GATE_NOT_MET',
        cross_scale='NOT_RUN_MECHANISM_LOCK_REQUIRED',automatic_training=False))
if __name__=='__main__':main()
