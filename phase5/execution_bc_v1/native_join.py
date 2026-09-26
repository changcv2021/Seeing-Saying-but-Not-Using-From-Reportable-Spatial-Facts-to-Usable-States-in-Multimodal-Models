"""Native L4 measured conditional failure map with world-cluster uncertainty."""
from collections import defaultdict
from bc_common import *
from quality_audit import status_counts
BATCH='native_e8_measurement_v1'

def main():
    p=cli(__doc__);p.add_argument('--batch',choices=[BATCH],required=True);p.add_argument('--model',required=True)
    a=p.parse_args();c,sws,out=context(a)
    if a.model not in c['models']:raise ValueError('SCOPE')
    if a.dry_run:print('Native same-world PRE/action/POST/joint/selection/verdict conditional map.');return
    src=out/'batches'/BATCH;extra=load(src/'manifest/NATIVE_EXTENSION_LOCK.json')
    for ref in extra['code']+[extra['request_lock']]:check(ref)
    files=list((src/'scores'/a.model).glob('snapshot_*/SCORE_ACCEPTANCE.json'))
    if len(files)!=1:raise ValueError('AMBIGUOUS_SCORE_SNAPSHOT')
    ac=load(files[0]);check(ac['scores']);sc={r['request_id']:r for r in csvrows(ac['scores']['path'])}
    for r in sc.values():
        r['component_values']=json.loads(r['component_values']);r['expected']=json.loads(r['expected'])
        r['correct']=r['content_correct']=='True' if r['execution_status']=='RETURNED' else None
    result=[]
    for m in rows(src/'private_gold/matched_structure.jsonl'):
        ep={k:endpoint(sc,rid) for k,rid in m['ids'].items()};pre=ep['PRE_VALUE']['correct'];post=ep['POST_VALUE']['correct'];joint=ep['JOINT_STATE']['correct']
        acts=[ep[k]['correct'] for k in ('ACTION_TYPE','ACTION_AMOUNT','ACTION_TARGET')]
        action=all(acts) if all(v is not None for v in acts) else None
        verdicts=[ep[k]['correct'] for k in ('SUPPORTED','CONTRADICTORY')]
        sel=[ep[k]['correct'] for k in ('TARGET_PRE','TARGET_POST')];labels=[]
        if any(v['parser_status']=='INVALID' for v in ep.values()):labels.append('ANSWER_INTERFACE_REMAINS')
        if pre is False:labels.append('PRE_FACT_OR_INTERFACE_FAILURE')
        if action is False:labels.append('ACTION_UNDERSTANDING_OR_INTERFACE_FAILURE')
        if pre is True and action is True and post is False:labels.append('POST_UPDATE_OR_TARGET_SELECTION_FAILURE')
        if joint is True and all(v is not None for v in sel) and not all(sel):labels.append('STATE_SELECTION_OR_INTERFACE_FAILURE')
        if post is True and all(v is not None for v in verdicts) and not all(verdicts):labels.append('CLAIM_COMPARISON_ACCEPTANCE_OR_VERDICT_INTERFACE_FAILURE')
        result.append(dict(model=a.model,world_cluster_id=m['world_cluster_id'],pair_id=m['pair_id'],level='L4',split='discovery',
            endpoints=ep,labels=labels,source_recovery=m['source_recovery'],
            post_wrong_given_pre_action=(not post) if pre is True and action is True and post is not None else None,
            select_wrong_given_joint=(not all(sel)) if joint is True and all(v is not None for v in sel) and m['selection_identifiable'] else None,
            verdict_wrong_given_post=(not all(verdicts)) if post is True and all(v is not None for v in verdicts) else None,
            scope='RECOVERED_NATIVE_L4_COUNT_ONLY; NOT_ENTIRE_BENCHMARK',interpretation='SEPARATE_CALL_BEHAVIOR_NOT_UNIQUE_CAUSAL_MECHANISM'))
    dest=out/'updated_analysis'/BATCH/a.model;csvsave(dest/'world_diagnostics.csv',result)
    import numpy as np
    stats=[];statuses=status_counts(e for r in result for e in r['endpoints'].values())
    for field in ('post_wrong_given_pre_action','select_wrong_given_joint','verdict_wrong_given_post'):
        ww=defaultdict(list)
        for r in result:
            if r[field] is not None:ww[r['world_cluster_id']].append(float(r[field]))
        num=sum(map(sum,ww.values()));den=sum(map(len,ww.values()));value=lo=hi=None
        if den:
            xx=np.array([[sum(v),len(v)] for _,v in sorted(ww.items())]);rng=np.random.default_rng(c['seed'])
            samples=xx[rng.integers(0,len(xx),size=(5000,len(xx)))].sum(axis=1);values=samples[:,0]/samples[:,1]
            value=num/den;lo,hi=map(float,np.quantile(values,[.025,.975]))
        stats.append(dict(model=a.model,metric=field,numerator=num,denominator=den,worlds=len(ww),
            planned_worlds=len(result),estimate=value,ci95_low=lo,ci95_high=hi,split='discovery',
            status='ESTIMATED' if den else 'EMPTY_CONDITION_OR_NOT_MEASURED',bootstrap_repetitions=5000,**statuses))
    csvsave(dest/'conditional_statistics.csv',stats)
    save(dest/'ACCEPTANCE.json',dict(status='NATIVE_AVAILABLE_MEASUREMENTS_ANALYZED',rows=len(result),
        score_acceptance=entry(files[0]),matrix=entry(dest/'world_diagnostics.csv'),statistics=entry(dest/'conditional_statistics.csv'),
        code=entry(__file__),job_id=os.environ['SLURM_JOB_ID'],grade='AUTO_ONLY_PROVISIONAL',not_final_report=True))

if __name__=='__main__':main()
