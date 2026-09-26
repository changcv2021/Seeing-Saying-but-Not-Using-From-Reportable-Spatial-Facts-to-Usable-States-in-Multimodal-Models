"""Fixed missing-measurement completion for source-recovered native L4 anchors."""
from bc_common import *
from compile_behavior import Builder
from data_continuation_v1.prepare import source_guard
BATCH='native_e8_measurement_v1'

def main():
    a=cli(__doc__).parse_args();c,sws,out=context(a)
    if a.dry_run:print('Freeze every recovered ADD/REMOVE native E8 anchor, eight calls each.');return
    guard=source_guard();source=out/'preparation/native_source_recovery_v2';ac=load(source/'ACCEPTANCE.json')
    if ac['status']!='SOURCE_REPLAY_COMPLETE_NOT_INFERENCE':raise ValueError('SOURCE_NOT_READY')
    rr=list(rows(source/'recovered_evidence.jsonl'));b=Builder(c,out,BATCH,'discovery');exclusions=[]
    schema=dict(kind='value',domain='count',nullable=True)
    for r in rr:
        native=load(check(r['source_bundle']));pair=native['source']['pair'];pre=r['pre_value'];post=r['post_value'];tr=r['transition']
        action={'REMOVAL_DECREMENTS_CLASS_COUNT':'REMOVE','ADDITION_INCREMENTS_CLASS_COUNT':'ADD'}.get(tr['rule_id'])
        if not action:
            exclusions.append(dict(world_cluster_id=r['world_cluster_id'],pair_id=r['pair_id'],reason='NON_SINGLE_ADD_REMOVE_ACTION_REQUIRES_SEPARATE_CONTRACT'));continue
        delta=tr['delta']
        if type(delta) is not int or delta<=0 or (pre-delta if action=='REMOVE' else pre+delta)!=post:raise ValueError('SOURCE_TRANSITION_ROUNDTRIP')
        inp=native['original_requests'][0];media=inp['media'];noun=r['pre_fact']['subject'].replace('_',' ')
        # Public text includes only original media/intervention and neutral queries; no source count or certificates.
        text=('The images show the same scene before a hypothetical change. Multiple views do not add duplicate objects to the scene count.\n'+
            'IMAGE ORDER: '+', '.join(f'{i+1}={m["role"]}' for i,m in enumerate(media))+'.\n'+
            'PRE is the observed scene before the change; POST is the hypothetical scene after the change.\n'+
            'HYPOTHETICAL CHANGE: '+inp['intervention_text']+'\n')
        p=dict(world_cluster_id=r['world_cluster_id'],facts=[r['pre_fact']],source_graphs=[r['source_bundle']],media=media,
            primary_stratum='NATIVE_COUNT',source_level='L4',source_recovery=r,split='discovery')
        b.panels.append(p);ids={}
        def emit(label,sch,gold,q):
            return b.emit(p,label,sch,gold,text+q,target=label,experiment='E8_NATIVE_COMPLETION',role='AUTHORIZED_INTERVENTION')
        ids['PRE_VALUE']=emit('PRE_VALUE',schema,pre,f'TARGET: PRE\nQUERY: How many {noun} are in the whole scene in the target state?')
        ids['POST_VALUE']=emit('POST_VALUE',schema,post,f'TARGET: POST\nQUERY: How many {noun} are in the whole scene in the target state?')
        ids['ACTION_TYPE']=emit('ACTION_TYPE',dict(kind='value',domain='enum',nullable=True,values=['ADD','REMOVE','NOOP']),action,
            'QUERY: What operation does the hypothetical change specify?')
        ids['ACTION_AMOUNT']=emit('ACTION_AMOUNT',schema,delta,'QUERY: How many individual objects does the specified operation add or remove?')
        ids['ACTION_TARGET']=emit('ACTION_TARGET',dict(kind='value',domain='enum',nullable=True,values=[noun,'NONE']),noun,
            'QUERY: Which counted object category does the hypothetical operation change? Return NONE if it changes no objects.')
        ids['JOINT_STATE']=emit('JOINT_STATE',dict(kind='facts',domain='count',nullable=True,query_ids=['pre','post']),
            dict(facts=dict(pre=pre,post=post)),f'QUERIES: pre: How many {noun} are in PRE? post: How many {noun} are in POST?')
        for key,label in [('SUPPORTED','supported_claim'),('CONTRADICTORY','contradictory_claim')]:
            ids[key]=emit(key,dict(kind='value',domain='enum',nullable=True,values=['SUPPORTED','CONTRADICTORY']),key,
                'TARGET: POST\nCANDIDATE CLAIM: '+pair[label]['text']+'\nQUERY: Is this claim supported or contradictory in the target state?')
        # Same physical queries are target-selection endpoints; do not count identical calls twice.
        ids['TARGET_PRE']=ids['PRE_VALUE'];ids['TARGET_POST']=ids['POST_VALUE']
        b.matches.append(dict(world_cluster_id=r['world_cluster_id'],level='L4',pair_id=r['pair_id'],ids=ids,
            source_recovery=r,selection_identifiable=pre!=post,scope='NATIVE_E8_SOURCE_RECOVERY_NOT_NEW_WORLDS'))
    save(out/'preparation/native_completion_exclusions.jsonl',exclusions,'jsonl')
    if not b.req:
        save(out/'preparation/NATIVE_COMPLETION_NOT_RUN.json',dict(reason='NO_QUALIFIED_SOURCE_RECOVERY'));return
    for request in b.req:
        request['sample_family']='NATIVE_L4_COUNT';request['source_type']='SOURCE_NATIVE_WITH_RECOVERED_PRE';request['source_level']='L4'
        request.pop('model_independent_request_hash');request['model_independent_request_hash']=digest(request)
    for gold in b.gold:gold['source_type']='SOURCE_NATIVE_WITH_RECOVERED_PRE'
    dest=b.publish([entry(source/'RECOVERY_LOCK.json'),entry(source/'recovered_evidence.jsonl'),entry(__file__)])
    save(dest/'manifest/NATIVE_EXTENSION_LOCK.json',dict(request_lock=entry(dest/'manifest/REQUEST_LOCK.json'),
        code=[entry(HERE/n) for n in ('native_compile.py','native_runtime.py','native_score.py','native_join.py','native_launch.py','job_native_score.sh','quality_audit.py')],
        requests_per_world=8,all_models_same_requests=True,selection='ALL_SOURCE_REPLAY_QUALIFIED_FROZEN_ANCHORS_NO_PREDICTIONS',
        joint_target_selection_aliases=True,interpretation='SEPARATE_CALL_BEHAVIORAL_CONDITIONALS_NOT_INTERNAL_TRACE',
        status='FROZEN_BEFORE_NEW_NATIVE_COMPLETION_PREDICTIONS'))
    save(dest/'manifest/SOURCE_GUARD.json',guard)

if __name__=='__main__':main()
