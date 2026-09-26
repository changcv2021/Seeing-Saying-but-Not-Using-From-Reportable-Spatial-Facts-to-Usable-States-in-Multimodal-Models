"""Per-model new-measurement world-cluster CIs, retaining all statuses."""
from collections import defaultdict
from bc_common import *
from quality_audit import status_counts

def main():
    p=cli(__doc__);p.add_argument('--batch',required=True);p.add_argument('--model',required=True)
    a=p.parse_args();c,sws,out=context(a)
    if a.batch not in ('e5_measurement_v1','c1_count_v1') or a.model not in c['models']:raise ValueError('SCOPE')
    if a.dry_run:print('World cluster bootstrap 5000 on frozen conditional endpoints.');return
    import numpy as np
    src=out/'updated_analysis'/a.batch/a.model;ac=load(src/'ACCEPTANCE.json');check(ac['matrix']);rr=csvrows(ac['matrix']['path'])
    dest=src/'statistics_v1';groups=defaultdict(list);result=[]
    for r in rr:groups[r.get('sequence') or r.get('hypothesis')].append(r)
    fields={'e5_measurement_v1':['final_wrong_given_initial_action','step2_wrong_given_step1'],
        'c1_count_v1':['false_wrong','sham_wrong','false_minus_sham','candidate_attraction','post_wrong_given_pre_action',
            'base_wrong_given_post','protected_wrong_given_post','selection_wrong_given_joint']}
    for group,rs in sorted(groups.items()):
        statuses=status_counts(v for r in rs for v in json.loads(r['endpoints']).values())
        for field in fields[a.batch]:
            if field not in rs[0]:continue
            ww=defaultdict(list)
            for r in rs:
                raw=r.get(field,'')
                if raw!='':ww[r['world_cluster_id']].append(1.0 if raw=='True' else 0.0 if raw=='False' else float(raw))
            num=sum(map(sum,ww.values()));den=sum(map(len,ww.values()));est=lo=hi=None
            if den:
                xx=np.array([[sum(v),len(v)] for _,v in sorted(ww.items())]);rng=np.random.default_rng(c['seed'])
                ii=rng.integers(0,len(xx),size=(5000,len(xx)));bb=xx[ii].sum(axis=1);bb=bb[:,0]/bb[:,1]
                est=num/den;lo,hi=map(float,np.quantile(bb,[.025,.975]))
            result.append(dict(model=a.model,batch=a.batch,group=group,metric=field,numerator=num,denominator=den,
                worlds=len(ww),planned_worlds=len({r['world_cluster_id'] for r in rs}),estimate=est,ci95_low=lo,ci95_high=hi,
                status='ESTIMATED' if den else 'NOT_MEASURED_OR_EMPTY_CONDITION',split=rs[0]['split'],
                method='MATCHED_RECORD_ESTIMATE_WITH_WORLD_CLUSTER_BOOTSTRAP_5000',seed=c['seed'],
                excluded_or_unmeasured_rows=len(rs)-den,**statuses))
    csvsave(dest/'conditional_statistics.csv',result)
    save(dest/'ACCEPTANCE.json',dict(status='AVAILABLE_MEASUREMENTS_ANALYZED_NOT_FINAL_REPORT',rows=len(result),
        source=entry(src/'ACCEPTANCE.json'),matrix=entry(ac['matrix']['path']),code=entry(__file__),
        status_code=entry(HERE/'quality_audit.py'),job_id=os.environ['SLURM_JOB_ID'],
        interpretation='Behavioral matched requests; neither hidden execution traces nor proof of a unique causal mechanism.'))
    print(json.dumps(dict(model=a.model,batch=a.batch,rows=len(result))),flush=True)

if __name__=='__main__':main()
