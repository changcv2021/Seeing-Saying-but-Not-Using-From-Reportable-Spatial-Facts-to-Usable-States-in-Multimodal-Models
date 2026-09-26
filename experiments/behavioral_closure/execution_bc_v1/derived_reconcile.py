"""Reconcile superseded historical placeholders; retain original matrices and CIs."""
from collections import defaultdict
from math import sqrt
from bc_common import *
from quality_audit import status_counts

def main():
    p=cli(__doc__);p.add_argument('--model',required=True);a=p.parse_args();c,sws,out=context(a)
    if a.model not in c['models']:raise ValueError('MODEL_SCOPE')
    if a.dry_run:print('Versioned E5 placeholder reconciliation and sparse-event uncertainty.');return
    src=out/'updated_analysis/e5_measurement_v1'/a.model;ac=load(src/'ACCEPTANCE.json');check(ac['matrix'])
    rr=csvrows(ac['matrix']['path']);result=[];groups=defaultdict(list)
    for r in rr:
        ep=json.loads(r['endpoints']);retired={}
        for key in ('action_1','action_2','intermediate_state'):
            old=ep.get(key)
            if old is not None:
                if old['request_id'] is not None or old['status']!='NOT_RUN':raise ValueError('REFUSE_RETIRE_ACTUAL_MEASUREMENT')
                retired[key]=ep.pop(key)
        for key in ('ACTION_1_TYPE','ACTION_1_TARGET','ACTION_1_AMOUNT','ACTION_2_TYPE','ACTION_2_TARGET','ACTION_2_AMOUNT','INTERMEDIATE'):
            if key not in ep:raise ValueError('MISSING_REPLACEMENT_MEASUREMENT')
        r['endpoints']=ep;r['superseded_historical_placeholders']=retired
        for field in ('final_wrong_given_initial_action','step2_wrong_given_step1'):
            r[field]=None if r[field]=='' else r[field]=='True'
        for k,name in [('BASE','base_wrong_given_target'),('PROTECTED','protected_wrong_given_target')]:
            target=ep['TARGET']['correct'];value=ep[k]['correct']
            r[name]=(not value) if target is True and value is not None else None
        r['status_reconciliation']='HISTORICAL_EMPTY_PLACEHOLDERS_SUPERSEDED_NOT_DELETED_FROM_ORIGINAL'
        result.append(r);groups[r['sequence']].append(r)
    dest=out/'updated_analysis_v2/e5_measurement_v1'/a.model;csvsave(dest/'world_diagnostics.csv',result)
    import numpy as np
    stats=[]
    for group,rs in sorted(groups.items()):
        statuses=status_counts(e for r in rs for e in r['endpoints'].values())
        for field in ('final_wrong_given_initial_action','step2_wrong_given_step1','base_wrong_given_target','protected_wrong_given_target'):
            ww=defaultdict(list)
            for r in rs:
                if r[field] is not None:ww[r['world_cluster_id']].append(float(r[field]))
            num=sum(map(sum,ww.values()));den=sum(map(len,ww.values()));estimate=lo=hi=wlo=whi=None;warning=''
            if den:
                xx=np.array([[sum(v),len(v)] for _,v in sorted(ww.items())]);rng=np.random.default_rng(c['seed'])
                samples=xx[rng.integers(0,len(xx),size=(5000,len(xx)))].sum(axis=1);values=samples[:,0]/samples[:,1]
                estimate=num/den;lo,hi=map(float,np.quantile(values,[.025,.975]))
                if lo==hi:warning='DEGENERATE_EMPIRICAL_BOOTSTRAP_DOES_NOT_ESTABLISH_ZERO_POPULATION_UNCERTAINTY'
                if den==len(ww):
                    z=1.959963984540054;d=1+z*z/den;center=(estimate+z*z/(2*den))/d
                    margin=z*sqrt(estimate*(1-estimate)/den+z*z/(4*den*den))/d
                    wlo=max(0.,center-margin);whi=min(1.,center+margin)
            stats.append(dict(model=a.model,sequence=group,metric=field,numerator=num,denominator=den,worlds=len(ww),
                planned_worlds=len({r['world_cluster_id'] for r in rs}),estimate=estimate,ci95_low=lo,ci95_high=hi,
                method='WORLD_CLUSTER_BOOTSTRAP_5000',uncertainty_warning=warning,wilson95_sensitivity_low=wlo,wilson95_sensitivity_high=whi,
                sensitivity_scope='ONLY_ONE_BINARY_OBSERVATION_PER_WORLD_IN_THIS_STRATUM',split='discovery',
                status='ESTIMATED' if den else 'NOT_MEASURED_OR_EMPTY_CONDITION',**statuses))
    csvsave(dest/'conditional_statistics.csv',stats)
    save(dest/'ACCEPTANCE.json',dict(status='RECONCILED_DERIVED_VIEW_COMPLETE',source=entry(src/'ACCEPTANCE.json'),
        matrix=entry(dest/'world_diagnostics.csv'),statistics=entry(dest/'conditional_statistics.csv'),code=entry(__file__),
        job_id=os.environ['SLURM_JOB_ID'],originals_unchanged=True,retired_only_uninstantiated_historical_placeholders=True,
        changed_predictions=False,changed_gold=False,changed_prompt=False,changed_primary_point_estimates=False,
        use_this_view_for_current_status_counts=True))

if __name__=='__main__':main()
