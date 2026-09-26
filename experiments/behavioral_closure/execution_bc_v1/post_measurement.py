"""Join new behavioral measurements to frozen endpoints; not an internal trace."""
from collections import defaultdict
from bc_common import *

def main():
    p=cli(__doc__);p.add_argument('--batch',required=True);p.add_argument('--model',required=True);a=p.parse_args();c,sws,out=context(a)
    if a.batch not in ('c1_count_v1','e5_measurement_v1') or a.model not in c['models']:raise ValueError('SCOPE')
    if a.dry_run:print('Join frozen new response endpoints, keep invalid and missing.');return
    src=out/'batches'/a.batch;found=list((src/'scores'/a.model).glob('snapshot_*/SCORE_ACCEPTANCE.json'))
    if len(found)!=1:raise ValueError('AMBIGUOUS_SCORE_SNAPSHOT')
    ac=load(found[0]);check(ac['scores']);sc={r['request_id']:r for r in csvrows(ac['scores']['path'])}
    for r in sc.values():
        r['component_values']=json.loads(r['component_values']);r['expected']=json.loads(r['expected'])
        r['correct']=r['content_correct']=='True' if r['execution_status']=='RETURNED' else None
    matches=list(rows(src/'private_gold/matched_structure.jsonl'));matrix=[]
    if a.batch=='e5_measurement_v1':
        originals={(r['world_cluster_id'],r['sequence']):r for r in csvrows(out/'P2_E5/matrix.csv') if r['model']==a.model}
        for m in matches:
            old=originals[(m['world_cluster_id'],m['sequence'])];ep=json.loads(old['endpoints'])
            ep.update({k:endpoint(sc,rid) for k,rid in m['ids'].items()})
            action=[ep[f'ACTION_{step}_{field}']['correct'] for step in (1,2) for field in ('TYPE','AMOUNT','TARGET')]
            action_correct=all(v is True for v in action) if all(v is not None for v in action) else None
            initial=ep['initial_target']['correct'] is True and ep['initial_protected']['correct'] is True
            final=ep['TARGET']['correct'];mid=ep['INTERMEDIATE']['correct'];flags=[]
            if any(ep[k]['correct'] is False for k in ('initial_target','initial_protected')):flags.append('INITIAL_FACT_FAILURE')
            if any(v is False for v in action):flags.append('ACTION_UNDERSTANDING_OR_INTERFACE_FAILURE')
            if initial and action_correct is True and final is False:
                value=ep['TARGET']['prediction'].get('value');pre=m['source_proof']['pre']
                if ep['TARGET']['parser_status']!='VALID':flags.append('ANSWER_INTERFACE_REMAINS')
                else:flags.append('FAILED_UPDATE' if eq(value,pre) else 'WRONG_UPDATE')
            if final is True and ep['BASE']['correct'] is False:
                flags.append('STATE_OVERWRITE' if eq(ep['BASE']['prediction'].get('value'),ep['TARGET']['gold'].get('value')) else 'BASE_RETENTION_FAILURE_OTHER')
            if ep['initial_protected']['correct'] is True and ep['PROTECTED']['correct'] is False:flags.append('PROTECTED_FACT_DAMAGE')
            if mid is True and final is False:flags.append('MULTI_STEP_ACCUMULATION_OR_SELECTION_FAILURE')
            if all(ep[k]['correct'] is True for k in ('TARGET','BASE','PROTECTED')):flags.append('FULLY_CORRECT_FINAL_ENDPOINTS')
            matrix.append(dict(model=a.model,world_cluster_id=m['world_cluster_id'],sequence=m['sequence'],endpoints=ep,
                labels=flags,initial_facts_correct=initial,action_correct=action_correct,intermediate_correct=mid,
                final_target_correct=final,final_base_correct=ep['BASE']['correct'],final_protected_correct=ep['PROTECTED']['correct'],
                final_wrong_given_initial_action=(not final) if initial and action_correct is True and final is not None else None,
                step2_wrong_given_step1=(not final) if mid is True and final is not None else None,
                source_transition_proof=m['source_proof'],split='discovery',
                interpretation='SEPARATE_REQUEST_SAME_WORLD_SAME_SEQUENCE_CONDITIONAL_BEHAVIOR_NOT_INTERNAL_EXECUTION_TRACE'))
    else:
        for m in matches:
            if m['experiment']=='E2':
                names=('neutral','true','false','sham','protected_neutral','protected_false','protected_sham')
                ep={k:endpoint(sc,m[k]) for k in names};n,f,s=(ep[k]['correct'] for k in ('neutral','false','sham'))
                attraction=eq(ep['false']['prediction'].get('value'),m['candidate_value']) and 'value' in ep['false']['prediction']
                matrix.append(dict(model=a.model,world_cluster_id=m['world_cluster_id'],hypothesis='H1',endpoints=ep,
                    false_claim_value=m['candidate_value'],gold_fact=m['target_gold'],neutral_correct=n,
                    false_wrong=(not f) if n is True and f is not None else None,
                    sham_wrong=(not s) if n is True and s is not None else None,
                    false_minus_sham=(int(not f)-int(not s)) if n is True and f is not None and s is not None else None,
                    candidate_attraction=attraction if n is True and f is not None else None,split='confirmation'))
            else:
                ep={k:endpoint(sc,rid) for k,rid in m['ids'].items()};pre=ep['PRE_VALUE']['correct'];post=ep['TARGET_SA']['correct']
                action=all(ep[k]['correct'] is True for k in ('ACTION_TYPE','ACTION_TARGET','ACTION_AMOUNT'))
                joint=ep['JOINT_STATE']['correct'];target=[ep['TARGET_'+s]['correct'] for s in ('S0','SA','SB')]
                matrix.append(dict(model=a.model,world_cluster_id=m['world_cluster_id'],hypothesis='H2_H3_H4',endpoints=ep,
                    initial_correct=pre,action_correct=action,post_correct=post,
                    post_wrong_given_pre_action=(not post) if pre is True and action and post is not None else None,
                    base_wrong_given_post=(not ep['TARGET_S0']['correct']) if post is True and ep['TARGET_S0']['correct'] is not None else None,
                    protected_wrong_given_post=(not ep['PROTECTED_AFTER']['correct']) if post is True and ep['PROTECTED_AFTER']['correct'] is not None else None,
                    selection_wrong_given_joint=(not all(target)) if joint is True and all(v is not None for v in target) and m['selection_identifiable'] else None,
                    selection_identifiable=m['selection_identifiable'],split='confirmation',source_transition=m['transition']))
    dest=out/'updated_analysis'/a.batch/a.model;csvsave(dest/'world_diagnostics.csv',matrix)
    save(dest/'ACCEPTANCE.json',dict(status='JOINED_AVAILABLE_RESPONSES',rows=len(matrix),worlds=len({r['world_cluster_id'] for r in matrix}),
        model=a.model,batch=a.batch,score_acceptance=entry(found[0]),matrix=entry(dest/'world_diagnostics.csv'),
        code=entry(__file__),job_id=os.environ['SLURM_JOB_ID'],not_a_final_study_report=True))
    print(json.dumps(dict(status='JOIN_COMPLETE',batch=a.batch,model=a.model,rows=len(matrix))),flush=True)

if __name__=='__main__':main()
