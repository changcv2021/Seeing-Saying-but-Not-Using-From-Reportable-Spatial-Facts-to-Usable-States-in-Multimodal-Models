"""World-cluster bootstrap of actual paired conditional measurements."""
from collections import defaultdict
from bc_common import *

def main():
    a=cli(__doc__).parse_args();c,sws,out=context(a)
    if a.dry_run:print('Paired world-cluster CIs; retain empty denominators and missing measurements.');return
    import numpy as np
    result=[];sources=[]
    def stat(group,metric,data,planned):
        # Each item is (world,event); None is unmeasured/ineligible, not False.
        ww=defaultdict(list)
        for w,v in data:
            if v is not None:ww[w].append(float(v))
        values=sorted(ww);num=sum(sum(ww[w]) for w in values);den=sum(len(ww[w]) for w in values)
        low=high=estimate=None
        if den:
            x=np.array([[sum(ww[w]),len(ww[w])] for w in values]);rng=np.random.default_rng(c['seed'])
            ii=rng.integers(0,len(values),size=(5000,len(values)));ss=x[ii].sum(axis=1);bb=ss[:,0]/ss[:,1]
            low,high=map(float,np.quantile(bb,[.025,.975]));estimate=num/den
        result.append(dict(**group,metric=metric,numerator=num,denominator=den,worlds=len(ww),planned_worlds=planned,
            estimate=estimate,ci95_low=low,ci95_high=high,status='ESTIMATED' if den else 'NOT_MEASURED_OR_EMPTY_CONDITION',
            method='MATCHED_RECORD_ESTIMATE_WITH_WORLD_CLUSTER_BOOTSTRAP_5000',split='discovery',
            interpretation='EXPLORATORY_NOT_CONFIRMATORY',seed=c['seed']))
    e2=csvrows(out/'P1_E2/matrix.csv');sources.append(entry(out/'P1_E2/matrix.csv'));groups=defaultdict(list)
    for r in e2:groups[(r['model'],r['case'],r['source_family'],r['wording'])].append(r)
    for (model,case,family,wording),rs in sorted(groups.items()):
        group=dict(module='E2',model=model,case=case,family=family,wording=wording);ws=len({r['world_cluster_id'] for r in rs})
        for metric,name in [('FALSE_WRONG_GIVEN_NEUTRAL_CORRECT','false'),('SHAM_WRONG_GIVEN_NEUTRAL_CORRECT','sham')]:
            vals=[]
            for r in rs:
                ep=json.loads(r['endpoints']);ok=ep['neutral']['correct'] is True and ep[name]['correct'] is not None
                vals.append((r['world_cluster_id'],not ep[name]['correct'] if ok else None))
            stat(group,metric,vals,ws)
        for metric,field in [('FALSE_MINUS_SHAM_GIVEN_NEUTRAL_CORRECT','false_sham_difference'),('CANDIDATE_ATTRACTION_GIVEN_NEUTRAL_CORRECT','candidate_attraction')]:
            vals=[]
            for r in rs:
                value=None
                if r['neutral_correct']=='True' and r[field]!='':value=(r[field]=='True') if field=='candidate_attraction' else float(r[field])
                vals.append((r['world_cluster_id'],value))
            stat(group,metric,vals,ws)
        vals=[]
        for r in rs:
            ep=json.loads(r['endpoints']);n=ep['protected_neutral']['correct'];f=ep['protected_false']['correct']
            vals.append((r['world_cluster_id'],not f if n is True and f is not None else None))
        stat(group,'PROTECTED_DAMAGE_GIVEN_PROTECTED_NEUTRAL_CORRECT',vals,ws)
    e5=csvrows(out/'P2_E5/matrix.csv');sources.append(entry(out/'P2_E5/matrix.csv'));groups=defaultdict(list)
    for r in e5:groups[(r['model'],r['sequence'])].append(r)
    for (model,sequence),rs in sorted(groups.items()):
        group=dict(module='E5',model=model,case=sequence,family='COUNT_CONTROLLED_SEQUENCE',wording='FIXED_V1');ws=len({r['world_cluster_id'] for r in rs})
        for metric,field in [('BASE_WRONG_GIVEN_TARGET_CORRECT','BASE'),('PROTECTED_WRONG_GIVEN_TARGET_CORRECT','PROTECTED')]:
            vals=[]
            for r in rs:
                ep=json.loads(r['endpoints']);t=ep['TARGET']['correct'];v=ep[field]['correct']
                vals.append((r['world_cluster_id'],not v if t is True and v is not None else None))
            stat(group,metric,vals,ws)
        for metric in ('FINAL_WRONG_GIVEN_INITIAL_AND_ACTION_CORRECT','STEP2_WRONG_GIVEN_STEP1_CORRECT'):
            stat(group,metric,[(r['world_cluster_id'],None) for r in rs],ws)
    e8=csvrows(out/'P3_E8/matrix.csv');sources.append(entry(out/'P3_E8/matrix.csv'));groups=defaultdict(list)
    for r in e8:groups[(r['model'],r['level'],r['source_family'])].append(r)
    mapping={'L1':'object_correct_relation_wrong','L2':'premise_correct_conclusion_wrong','L3':'local_alignment_correct_global_wrong','L4':'pre_action_correct_post_wrong'}
    for (model,level,family),rs in sorted(groups.items()):
        field=mapping[level];vals=[(r['world_cluster_id'],None if r[field]=='' else r[field]=='True') for r in rs]
        stat(dict(module='E8',model=model,case=level,family=family,wording='FROZEN_EXISTING'),field.upper(),vals,len({r['world_cluster_id'] for r in rs}))
    csvsave(out/'P8/primary_statistics.csv',result)
    save(out/'P8/ACCEPTANCE.json',dict(status='DISCOVERY_STATISTICS_COMPLETE_PENDING_SUPPLEMENT_AND_C1',rows=len(result),sources=sources,
        code=entry(__file__),job_id=os.environ['SLURM_JOB_ID'],bootstrap_repetitions=5000,empty_denominators_retained=True,confirmation_complete=False))
    print(json.dumps(dict(rows=len(result),estimated=sum(r['status']=='ESTIMATED' for r in result))),flush=True)

if __name__=='__main__':main()
