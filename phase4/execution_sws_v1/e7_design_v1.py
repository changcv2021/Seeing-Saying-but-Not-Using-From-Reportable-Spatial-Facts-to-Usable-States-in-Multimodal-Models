"""E7 logical prefix / own-report / protected sequence; source-only selection."""
from copy import deepcopy
from common_auto_v2 import digest
from real_design_v1 import SYSTEM, question, schema, challenge, fact_value, branch_spec

BATCH='e7_d01_v1_20260910'


def render(template, parents):
    r=deepcopy(template); history=[]
    for parent in r['parent_request_ids']:
        if parent not in parents: raise ValueError('MISSING_OWN_RESPONSE_PARENT')
        raw=parents[parent]
        if raw['world_cluster_id']!=r['world_cluster_id']: raise ValueError('CROSS_WORLD_PARENT')
        # Verbatim, JSON-quoted output: no parsing, correction, omission or gold substitution.
        import json
        quoted=json.dumps(raw['raw_response'],ensure_ascii=False)
        r['payload']['text']=r['payload']['text'].replace('<SELF_REPORT:'+parent+'>',quoted)
        history.append(dict(request_id=parent,response_sha256=digest(raw['raw_response']),
                            raw_request_hash=raw['request_hash'],model_id=raw['model_id']))
    if '<SELF_REPORT:' in r['payload']['text']: raise ValueError('UNRESOLVED_SELF_REPORT')
    return r,history


def build(c,panel):
    a,b=panel['facts']; w=panel['world_cluster_id']; av,bv=fact_value(a),fact_value(b)
    count=panel['primary_stratum']=='COUNT'
    possible=[av+d for d in (-2,-1,1,2) if av+d>=0] if count else ['NO' if av=='YES' else 'YES']
    cv=min(possible,key=lambda v:digest([c['seed'],'E7_FIXED_OFFSET_V1',w,v]))
    mm=panel['media']; prefix=('OBSERVED STATE S0: the supplied reference image. Auxiliary images are support views, '
        'not extra objects to add to the reference-image count.\nIMAGE ORDER: '+
        ', '.join(f'{i+1}={m["role"]}' for i,m in enumerate(mm))+'\n')
    baseq='q1: '+question(a)+'\nq2: '+question(b)
    pairgold={'facts':{'q1':av,'q2':bv}}; reqs=[]; gold=[]; ids={}
    def emit(condition,body,expected,parents=(),queries=baseq,qids=('q1','q2')):
        s=schema(a,'facts'); s['query_ids']=list(qids)
        values='nonnegative integers or null' if count else '"YES", "NO", or null'
        sample={'facts':[dict(query_id=q,value='VALUE') for q in qids]}
        import json
        text=prefix+'CONTINUATION:\n'+body+'\nQUERIES:\n'+queries+'\nOUTPUT CONTRACT: Output exactly this JSON structure, replacing each VALUE with '+values+': '+json.dumps(sample)+'. No other keys, explanations or markdown.'
        r=dict(experiment='E7',condition=condition,world_cluster_id=w,split='discovery',
            logical_bundle_id=digest([BATCH,w]),sample_family=panel['primary_stratum'],
            source_type='CONTROLLED_SOURCE_EXTENSION' if condition.startswith('C_') else 'NATIVE',
            payload=dict(system=SYSTEM,text=text,media=mm),schema=s,requested_tokens=512,
            models=c['models'],review_status=c['review']['default_review_status'],
            scientific_review_grade='AUTO_ONLY_PROVISIONAL',parent_request_ids=list(parents),
            shared_observation_prefix=prefix,causal_prefix_mode='LOGICAL_SHARED_PREFIX',
            parent_injection='VERBATIM_JSON_QUOTED_EXTERNALIZED_STATE_NOT_IMPLICIT_STATE',
            source_level='L1',target_state='S0' if not condition.startswith('C_') else 'MULTI_STATE')
        r['request_id']='sws_e7_'+digest([BATCH,w,r['payload'],s])[:24]
        r['model_independent_request_hash']=digest(r)
        reqs.append(r); ids[condition]=r['request_id']
        gold.append(dict(request_id=r['request_id'],world_cluster_id=w,condition=condition,
            expected=expected,target_gold=av,protected_gold=bv,candidate_value=cv,
            source_fact_ids=[a['fact_id'],b['fact_id']],count_substratum=panel.get('count_substratum'),
            binary_nonidentifying=not count,source_level='L1',derived_level='CONTROLLED_BRANCH' if condition.startswith('C_') else 'L1'))
        return r['request_id']
    claim=challenge(cv,'CANDIDATE',question(a)); sham=challenge(cv,'SHAM',question(a))
    neutral=emit('A_NEUTRAL','TARGET: S0\nReport both original spatial facts.',pairgold)
    exposed=emit('A_CANDIDATE','TARGET: S0\n'+claim,pairgold)
    emit('A_SHAM','TARGET: S0\n'+sham,pairgold)
    def history(parent): return 'PAST SELF-REPORT (untrusted output by you; not a new observation): <SELF_REPORT:'+parent+'>\n'
    shared='Use the original images and your own earlier report. The candidate is a proposition to check, not evidence.\nTARGET: S0\n'+claim
    nc=emit('B_NEUTRAL_PARENT',history(neutral)+shared,pairgold,[neutral])
    emit('B_EXPOSED_PARENT',history(exposed)+shared,pairgold,[exposed])
    branch=None
    if count:
        branch=branch_spec(a,panel['count_substratum'])
        expected={'facts':{'q0':av,'qA':branch['values']['SA'],'qB':branch['values']['SB'],'qP':bv}}
        queries='q0: '+question(a,'S0')+'\nqA: '+question(a,'SA')+'\nqB: '+question(a,'SB')+'\nqP: '+question(b,'SA')
        seq=('READ-ONLY EVENT SEQUENCE:\n1. Observe S0 and query its original facts.\n'+baseq+
             '\n2. Encounter this candidate, then query the original and protected facts.\n'+claim+'\n'+baseq+
             '\n3. Apply only the following authorized alternative hypothetical actions.\n'+branch['text'])
        emit('C_OWN_FEEDBACK',seq+'\nOWN ANSWERS AFTER EVENT 1:\n'+history(neutral)+
             'OWN ANSWERS AFTER EVENT 2:\n'+history(nc),expected,[neutral,nc],queries,('q0','qA','qB','qP'))
        emit('C_READONLY_SEQUENCE',seq,expected,queries=queries,qids=('q0','qA','qB','qP'))
        emit('C_ONESHOT_RECOMPUTE','TARGET: S0, SA, SB and the unaffected category.\n'+claim+'\n'+branch['text']+
             '\nRecompute directly from the original evidence and these authorized actions. No earlier model report is supplied.',
             expected,queries=queries,qids=('q0','qA','qB','qP'))
    assert len(reqs)==(8 if count else 5)
    return reqs,gold,dict(world_cluster_id=w,sample_family=panel['primary_stratum'],ids=ids,
        target_gold=av,protected_gold=bv,candidate_value=cv,branch=branch,
        B_stage1_aliases=dict(neutral=neutral,exposed=exposed),
        logical_generation_calls=10 if count else 7,physical_unique_generations=len(reqs),
        C_qualification='CONTROLLED_QUANTITY_ONLY' if count else 'NOT_DIAGNOSABLE_NO_NATIVE_UPDATE_GOLD')
