"""Deterministic scientific-contract checks, separate from model accuracy."""
from collections import Counter,defaultdict
from v2_common import *
from state_contracts import Program,Action
from interface_repair_v3.adapter import normalize
def main():
    a=cli(__doc__).parse_args();context(a);checks=[]
    for batch in ['W1_TARGET','NONCOUNT']:
        out=ROOT/'batches'/batch;lk=load(out/'manifest/REQUEST_LOCK.json')
        for ref in lk['code']+lk['public_inputs']+lk['private_inputs']:check(ref)
        reqs=list(rows(out/'public_inputs/requests.jsonl'));gold={g['request_id']:g for g in rows(out/'private_gold/request_gold.jsonl')}
        byworld=defaultdict(list)
        for r in reqs:
            assert r['models']==MODELS and r['requested_tokens']==512
            assert set(r['payload'])=={'system','text','media'}
            assert digest({k:v for k,v in r.items() if k!='model_independent_request_hash'})==r['model_independent_request_hash']
            assert not any(t in r['payload']['text'] for t in ['expected_counterfactual','source_record_hash','gold_label','score_only','fact:'])
            g=gold[r['request_id']];canonical=normalize(json.dumps(g['expected']),r['schema'])['normalized']
            assert canonical['status']=='VALID' and canonical['component_values']==g['expected']
            byworld[r['world_cluster_id']].append(r)
        assert len(byworld)==(96 if batch=='W1_TARGET' else 47)
        assert {len(v) for v in byworld.values()}=={12 if batch=='W1_TARGET' else 4}
        if batch=='W1_TARGET':
            for rr in byworld.values():
                assert {r['condition'] for r in rr}=={f'T{i}_S{s}' for i in range(1,5) for s in range(3)}
                for r in rr:
                    g=gold[r['request_id']];p=g['proof']['program'];prog=Program(p['s0'],Action(**p['a1']),Action(**p['a2']),p['source_type'])
                    assert g['expected']=={'value':{'S0':prog.s0,'S1':prog.s1,'S2':prog.s2}[r['target_state']]}
        checks.append(dict(test=batch+'_FROZEN_PAYLOAD_GOLD_PROGRAM_SCHEMA',status='PASS',worlds=len(byworld),requests=len(reqs)))
    i1=ROOT/'I1';lk=load(i1/'manifest/INPUT_LOCK.json')
    for ref in lk['public_inputs']+lk['private_inputs']+lk['historical_inputs']:check(ref)
    for ref in load(i1/'manifest/RUNTIME_LOCK.json')['code']:check(ref)
    panels=list(rows(i1/'public_inputs/panel.jsonl'));byid={p['case_id']:p for p in panels};splits=defaultdict(set)
    for p in panels:
        splits[p['world_cluster_id']].add(p['split']);did=p['success_donor_case']
        if did:
            d=byid[did];assert d['cohort']=='C' and d['split']==p['split'] and d['world_cluster_id']!=p['world_cluster_id']
            assert d['sequence_id']==p['sequence_id'] and d['program']['a1']['kind']==p['program']['a1']['kind'] and d['program']['a2']['kind']==p['program']['a2']['kind']
    assert all(len(s)==1 for s in splits.values())
    checks.append(dict(test='I1_WORLD_SPLIT_DONOR_MATCHING_LOCKS',status='PASS',cases=len(panels),worlds=len(splits)))
    # Logical specificity test: B cohort and other queries may not affect Type-A candidate ranking.
    from i1_analyze import specificity
    sample=[]
    for kind,value in [('INFORMATIVE_S0',3.),('SAME_VALUE_SHAM',1.)]:
        sample.append(dict(split='LOCALIZE',cohort='A',query='S2',status='RETURNED',eligibility='HISTORICAL_VALID_COHORT',case_id='c1',depth=0,anchor='P_QUERY',donor_kind=kind,world_cluster_id='w1',delta_correct_lp=value,raw={'path':'TEST_ONLY'}))
    sample.append(dict(sample[0],cohort='B',case_id='c2',delta_correct_lp=999.))
    pairs,summary=specificity(sample,'LOCALIZE');assert len(pairs)==len(summary)==1 and pairs[0]['value']==2. and summary[0]['mean']==2.
    checks.append(dict(test='TYPE_A_MATCHED_SPECIFICITY_EXCLUDES_B_AND_OTHER_QUERY',status='PASS'))
    dest=ROOT/'validation'/('snapshot_'+os.environ['SLURM_JOB_ID']);save(dest/'ACCEPTANCE.json',dict(status='PASS',tests=checks,script=entry(__file__),
        not_a_model_accuracy_gate=True,original_files_unchanged=True));print(json.dumps(checks),flush=True)
if __name__=='__main__':main()
