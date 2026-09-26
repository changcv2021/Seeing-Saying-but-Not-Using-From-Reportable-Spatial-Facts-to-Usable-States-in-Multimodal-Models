"""Predefined E9 controls; symbolic values are NOT new real-world gold."""
from common import *
from contracts import count_label

SYSTEM='You are evaluating explicitly specified records. A candidate statement is a proposition to test, not new evidence. Return only the requested JSON. Use null if an exact value is not determined. Do not exceed 512 output tokens.'

def compile_requests(c):
    requests=[]; gold=[]; matched=[]
    # Twenty-four fully specified symbolic worlds, fixed before any output.
    for i in range(24):
        w='symbolic_sws_'+digest([c['seed'],'E9',i])[:20]
        a=2+i%5; b=a+2; d=a+4; target='SB' if i%2 else 'SA'; value={'SA':b,'SB':d}[target]
        topic='chairs in an explicitly specified symbolic room' if i<12 else 'tickets in an explicitly specified ledger'
        source_type='SYNTHETIC_SYMBOLIC'; spatial=i<12
        for presentation in ('TABLE','PROSE'):
            for missing in (False,True):
                states={'S0':a,'SA':b,'SB':d}
                if missing: states.pop(target)
                if presentation=='TABLE': observation=json.dumps(states,separators=(',',':'))
                else: observation=' '.join(f'{state} contains exactly {v} {topic}.' for state,v in states.items())
                scope='The target state count is not provided; only a lower bound of 1 is known.' if missing else 'Each supplied state count is exact.'
                base=f'RECORDS ({topic}): {observation}\n{scope}\nTARGET: {target}\n'
                for condition,claim in [('NEUTRAL',None),('TRUE_OR_POSSIBLE',value),('FALSE_OR_POSSIBLE',value+1),('SAME_VALUE_SHAM',value+1),('BELOW_BOUND',0)]:
                    material='' if claim is None else f'IRRELEVANT REGISTER: the unrelated register R has value {claim}.\n' if condition=='SAME_VALUE_SHAM' else f'CANDIDATE: the target state contains exactly {claim} {topic}.\n'
                    schema=dict(kind='value',domain='count',nullable=True)
                    prompt=base+material+'QUERY: report the exact count in TARGET. OUTPUT: {"value": integer or null}.'
                    rid='sws_'+digest([w,presentation,missing,condition,'VALUE'])[:28]
                    r=dict(request_id=rid,world_cluster_id=w,experiment='E9',logical_bundle_id=w+f':{presentation}:{missing}',
                        split='symbolic_control',sample_family=source_type,spatial_symbolic=spatial,condition=condition,
                        presentation=presentation,target_missing=missing,information_role='CANDIDATE' if claim is not None and condition!='SAME_VALUE_SHAM' else 'SHAM' if condition=='SAME_VALUE_SHAM' else 'NONE',
                        target_state=target,queried_fact_id='q_target',models=c['models'],schema=schema,
                        requested_tokens=512,payload=dict(system=SYSTEM,text=prompt,media=[]),review_status='SYMBOLIC_NO_REAL_MEDIA',ordinary_payload_gold_fields=[])
                    r['model_independent_request_hash']=digest(r); requests.append(r)
                    gold.append(dict(request_id=rid,value=None if missing else value,source_type=source_type,proof=dict(rule='EXPLICIT_SYMBOLIC_LOOKUP',states=states,target=target,lower=1 if missing else value,upper=None if missing else value)))
                    if condition in ('TRUE_OR_POSSIBLE','FALSE_OR_POSSIBLE','BELOW_BOUND'):
                        vr=dict(r); vr['request_id']='sws_'+digest([w,presentation,missing,condition,'VERDICT'])[:28]
                        vr['schema']=dict(kind='verdict',domain='count',nullable=True)
                        vr['payload']=dict(system=SYSTEM,text=base+material+'QUERY: evaluate CANDIDATE against the records. OUTPUT: {"verdict":"SUPPORTED|CONTRADICTORY|UNKNOWN"}.',media=[])
                        vr.pop('model_independent_request_hash'); vr['model_independent_request_hash']=digest(vr); requests.append(vr)
                        gold.append(dict(request_id=vr['request_id'],verdict=count_label(1 if missing else value,None if missing else value,claim),source_type=source_type,
                            proof=dict(rule='EXACT_COUNT_INTERVAL_ENTAILMENT',lower=1 if missing else value,upper=None if missing else value,claim=claim)))
                        matched.append(dict(fact_request_id=rid,verdict_request_id=vr['request_id'],world_cluster_id=w,condition=condition,presentation=presentation,target_missing=missing))
    assert len(requests)==768 and len({r['request_id'] for r in requests})==len(requests)
    return requests,gold,matched

def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('768 E9 symbolic requests/model; no real media and no inference'); return
    requests,gold,matched=compile_requests(c)
    save(root/'public_inputs/E9/requests.jsonl',requests,'jsonl')
    save(root/'private_gold/E9.jsonl',gold,'jsonl'); save(root/'matched/E9_structure.jsonl',matched,'jsonl')
    save(root/'manifest/E9_request_lock.json',dict(status='REQUESTS_FROZEN_NOT_EXECUTED',run_id=c['run_id'],created_at=now(),
        requests_per_model=len(requests),worlds=24,models=c['models'],seed=c['seed'],
        source=entry(root/'public_inputs/E9/requests.jsonl'),gold=entry(root/'private_gold/E9.jsonl'),
        code=[entry(CODE/x) for x in ('common.py','contracts.py','compile_symbolic.py','config.json')],
        study_role='SECONDARY_SYMBOLIC_AND_NONSPATIAL_CONTROLS_NOT_REAL_WORLD_QUOTA',budget_status=c['resources']['authorization_status'],
        no_answer_based_prompt_selection=True,inference_status='NOT_RUN_RESOURCE_BUDGET_UNRESOLVED'))
    print(json.dumps(dict(status='E9_REQUESTS_FROZEN_NOT_EXECUTED',requests_per_model=len(requests),worlds=24)),flush=True)

if __name__=='__main__': main()
