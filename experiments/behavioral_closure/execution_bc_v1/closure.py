"""P1/P2/P3 same-world evidence closure, with unmeasured boundaries retained."""
from collections import defaultdict,Counter
from bc_common import *

def e2(c,sws,out):
    matrix=[];sources=[]
    for case in ('D01','D02','D03','D04','NONCOUNT'):
        p,req,matched=batch(sws,case)
        aliases=list(rows(p/'private_gold/logical_aliases.jsonl'))
        sources += [entry(p/'private_gold'/n) for n in ('matched_structure.jsonl','logical_aliases.jsonl','world_panel.jsonl')]
        panels={r['world_cluster_id']:r for r in rows(p/'private_gold/world_panel.jsonl')}
        for model in c['models']:
            sc,refs=scores(sws,case,model);sources+=refs
            for m in matched:
                if m['experiment']!='E2':continue
                w=m['world_cluster_id'];r=req[m['neutral']];panel=panels[w];ep={k:endpoint(sc,m[k]) for k in ('neutral','false','sham')}
                target=m['target_gold'];cv=m['candidate_value'];wording=m.get('wording','W0')
                true=[a['request_id'] for a in aliases if 'TRUE' in a['condition'] and req[a['request_id']]['world_cluster_id']==w
                    and a.get('wording','W0')==wording and req[a['request_id']].get('queried_fact_id')==r.get('queried_fact_id')]
                ep['true']=endpoint(sc,true[0] if len(set(true))==1 else None)
                pm=[q for q in matched if q['world_cluster_id']==w and q['experiment']=='E2_PROTECTION'
                    and q.get('wording','W0')==wording and eq(q['candidate_value'],cv)]
                for label in ('neutral','false','sham'):ep['protected_'+label]=endpoint(sc,pm[0][label] if len(pm)==1 else None)
                n,f,s=(ep[k]['correct'] for k in ('neutral','false','sham'));flags=[]
                follows=eq(ep['false']['prediction'].get('value'),cv) and 'value' in ep['false']['prediction']
                if n is True and f is False and follows:flags.append('UNLICENSED_TARGET_CHANGE')
                if n is True and f is False and s is True:flags.append('FALSE_EXCESS_OVER_SHAM')
                if n is True and f is False and s is False:flags.append('GENERIC_INSTABILITY')
                if ep['protected_neutral']['correct'] is True and ep['protected_false']['correct'] is False:flags.append('PROTECTION_COLLATERAL_DAMAGE')
                if n is True and f is True and s is True:flags.append('STABLE_CORRECT')
                matrix.append(dict(case=case,model=model,world_cluster_id=w,source_family=r['sample_family'],
                    level=panel.get('source_level','L1'),spatial_variable=r['schema']['domain'],category=r.get('queried_fact_id'),wording=wording,
                    target=r['target_state'],gold_fact=target,false_claim_value=cv,sham_value=cv,endpoints=ep,labels=flags,
                    neutral_correct=n,false_correct=f,sham_correct=s,candidate_attraction=(n is True and f is False and follows),
                    false_sham_difference=(int(not f)-int(not s)) if n is True and f is not None and s is not None else None,
                    protected_match_status='EXACT_MATCH' if len(pm)==1 else 'NOT_DIAGNOSABLE_NO_EXACT_MATCH',
                    source_bundle=panel.get('bundle'),source_graphs=panel.get('source_graphs'),
                    interpretation='NONEXCLUSIVE_BEHAVIORAL_LABELS_NOT_INTERNAL_MECHANISM',split='discovery'))
    publish(out,'P1_E2',matrix,sources)

def e5(c,sws,out):
    matrix=[];sources=[];dest,pub,mm=batch(sws,'E5S')
    panels={r['world_cluster_id']:r for r in rows(dest/'private_gold/world_panel.jsonl')}
    gold={r['request_id']:r for r in rows(dest/'private_gold/request_gold.jsonl')}
    sources += [entry(dest/'private_gold'/n) for n in ('world_panel.jsonl','request_gold.jsonl','matched_structure.jsonl')]
    for model in c['models']:
        sc,refs=scores(sws,'E5S',model);sources+=refs
        originals={}
        for case in ('D01','D02','D03','D04'):
            pp,rr,matches=batch(sws,case);ss,ref=scores(sws,case,model);sources+=ref
            for alias in rows(pp/'private_gold/logical_aliases.jsonl'):
                r=rr[alias['request_id']];w=r['world_cluster_id']
                if alias['experiment']=='E1' and alias['condition']=='SINGLE_FACT':
                    originals[(w,r['queried_fact_id'])]=endpoint(ss,r['request_id'])
            for m in matches:
                if m['experiment']=='E3':originals[(m['world_cluster_id'],'separate_branch_step1')]=endpoint(ss,m['branch_value'])
        for m in mm:
            w=m['world_cluster_id'];ep={k:endpoint(sc,m[k]) for k in ('TARGET','BASE','PROTECTED')}
            proof=gold[m['TARGET']]['proof'];pre=proof['pre'];first=proof['first']
            initial_target=originals.get((w,'q1'),endpoint({},None));initial_protected=originals.get((w,'q2'),endpoint({},None))
            ep.update(initial_target=initial_target,initial_base=initial_target,initial_protected=initial_protected,
                action_1=endpoint({},None),action_2=endpoint({},None),intermediate_state=endpoint({},None),
                separate_context_step1=originals.get((w,'separate_branch_step1'),endpoint({},None)))
            flags=[]
            if any(x['correct'] is False for x in (initial_target,initial_protected)):flags.append('INITIAL_FACT_FAILURE')
            if ep['TARGET']['correct'] is True and ep['BASE']['correct'] is False:
                if eq(ep['BASE']['prediction'].get('value'),ep['TARGET']['gold'].get('value')):flags.append('STATE_OVERWRITE')
                else:flags.append('BASE_RETENTION_FAILURE_OTHER')
            if ep['PROTECTED']['correct'] is False:flags.append('PROTECTED_FACT_DAMAGE')
            if all(ep[k]['correct'] is True for k in ('TARGET','BASE','PROTECTED')):flags.append('FULLY_CORRECT_FINAL_ENDPOINTS')
            flags.append('UNRESOLVED_ACTION_AND_SAME_CONTEXT_INTERMEDIATE_NOT_MEASURED')
            matrix.append(dict(model=model,case='E5S',world_cluster_id=w,sequence=m['condition'],source_family='COUNT_CONTROLLED_SEQUENCE',
                endpoints=ep,labels=flags,source_transition_proof=proof,source_graphs=panels[w].get('source_graphs'),
                initial_facts_correct=all(x['correct'] is True for x in (initial_target,initial_protected)),
                action_correct=None,intermediate_correct=None,final_target_correct=ep['TARGET']['correct'],
                final_base_correct=ep['BASE']['correct'],final_protected_correct=ep['PROTECTED']['correct'],
                update_failure_given_initial_and_action=None,step2_failure_given_step1=None,
                diagnostic_status='PARTIAL_NOT_FULLY_DIAGNOSABLE',
                missing_measurements=['ACTION_1_PARSE','ACTION_2_PARSE','SAME_SEQUENCE_INTERMEDIATE'],
                source_truth_for_supplement='AVAILABLE_FROM_REPLAYABLE_TRANSITION_PROOF',split='discovery'))
    publish(out,'P2_E5',matrix,sources,dict(additional_measurement_required=True,missing_gold_inferred=False))

def e8(c,sws,out):
    matrix=[];sources=[];p,req,matched=batch(sws,'E8')
    gaps=list(rows(p/'reports/NOT_DIAGNOSABLE.jsonl'));panels=list(rows(p/'private_gold/world_panel.jsonl'))
    sources += [entry(p/'private_gold'/n) for n in ('world_panel.jsonl','request_gold.jsonl','matched_structure.jsonl')]+[entry(p/'reports/NOT_DIAGNOSABLE.jsonl')]
    required={'L1':['OBJECT','ARGUMENT','FACT_VALUE','SUPPORTED','CONTRADICTORY'],
        'L2':['PREMISE_1','PREMISE_2','JOINT_PREMISES','CONCLUSION','SUPPORTED','CONTRADICTORY'],
        'L3':['LOCAL_FACT','IDENTITY_ALIGNMENT','FRAME_MARKER','GLOBAL_FACT','SUPPORTED','CONTRADICTORY'],
        'L4':['PRE_VALUE','ACTION_PARSE','POST_VALUE','JOINT_STATE','TARGET_SELECT','SUPPORTED','CONTRADICTORY']}
    for model in c['models']:
        sc,refs=scores(sws,'E8',model);sources+=refs
        for panel in panels:
            w=panel['world_cluster_id'];level=panel['source_level']
            mm=[m for m in matched if m['world_cluster_id']==w and m['experiment']=='E8' and m.get('level')==level]
            ids={k:v for m in mm for k,v in m.items() if isinstance(v,str) and v in req}
            ep={k:endpoint(sc,rid) for k,rid in ids.items()}
            for k in required[level]:ep.setdefault(k,endpoint({},None))
            def conditional(prereq,target):
                values=[ep.get(k,{}).get('correct') for k in prereq];t=ep.get(target,{}).get('correct')
                return (not t) if all(v is True for v in values) and t is not None else None
            matrix.append(dict(model=model,world_cluster_id=w,level=level,source_family=panel['primary_stratum'],endpoints=ep,
                missing_conditions=[k for k in required[level] if ep[k]['status']=='NOT_RUN'],
                source_gaps=[g for g in gaps if g['world_cluster_id']==w and g['level']==level],
                status='NOT_DIAGNOSABLE' if any(ep[k]['status']=='NOT_RUN' for k in required[level]) else 'AVAILABLE',
                premise_correct_conclusion_wrong=conditional(['PREMISE_1','PREMISE_2'],'CONCLUSION') if level=='L2' else None,
                pre_action_correct_post_wrong=conditional(['PRE_VALUE','ACTION_PARSE'],'POST_VALUE') if level=='L4' else None,
                local_alignment_correct_global_wrong=conditional(['LOCAL_FACT','IDENTITY_ALIGNMENT'],'GLOBAL_FACT') if level=='L3' else None,
                object_correct_relation_wrong=conditional(['OBJECT'],'FACT_VALUE') if level=='L1' else None,
                source_bundle=panel.get('bundle'),split='discovery',interpretation='SAME_WORLD_FUNCTIONAL_BOUNDARIES_NOT_CAUSAL_MEDIATION'))
    publish(out,'P3_E8',matrix,sources)

def main():
    p=cli(__doc__);p.add_argument('--stage',choices=['P1','P2','P3'],required=True);a=p.parse_args();c,sws,out=context(a)
    if a.dry_run:print('Frozen existing-response same-world analysis '+a.stage);return
    {'P1':e2,'P2':e5,'P3':e8}[a.stage](c,sws,out)

if __name__=='__main__':main()
