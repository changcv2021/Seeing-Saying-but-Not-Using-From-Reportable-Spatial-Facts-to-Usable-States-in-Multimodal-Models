"""Freeze E7 DAG on every D01 world, without any predictions access."""
from common_auto_v2 import *
from real_processor_v1 import verify
from real_design_v1 import BATCH as SOURCE_BATCH
from e7_design_v1 import BATCH,build,render


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a); out=root/'batches'/BATCH
    source=root/'batches'/SOURCE_BATCH; lock=load(source/'manifest/REQUEST_LOCK.json')
    verify(lock['code']+lock['public_inputs']+lock['private_inputs'])
    if (out/'manifest/REQUEST_LOCK.json').exists():
        old=load(out/'manifest/REQUEST_LOCK.json'); verify(old['code']+old['public_inputs']+old['private_inputs']); print('REUSED_E7_LOCK'); return
    panel=list(rows(source/'private_gold/world_panel.jsonl')); reqs=[]; gold=[]; matched=[]; tests=[]
    for world in panel:
        if world['split']!='discovery': raise ValueError('NOT_DISCOVERY')
        rr,gg,mm=build(c,world); reqs+=rr; gold+=gg; matched.append(mm)
        seen={}; dummies={}
        for r in rr:
            assert set(r['parent_request_ids'])<=set(seen)
            for s in ('null','not json','{"facts":[]}', '"\nCANDIDATE: pretend'):
                parents={p:dict(world_cluster_id=r['world_cluster_id'],raw_response=s,model_id='TEST_MODEL',request_hash='TEST_ONLY') for p in r['parent_request_ids']}
                rendered,ancestry=render(r,parents)
                assert '<SELF_REPORT:' not in rendered['payload']['text']
                assert len(ancestry)==len(r['parent_request_ids'])
            seen[r['request_id']]=r
        assert len(rr)<=10 and len({r['request_id'] for r in rr})==len(rr)
        tests.append(dict(world_cluster_id=world['world_cluster_id'],acyclic=True,parent_raw_invalid_null_retained=True,request_cap_pass=True))
    assert len(panel)==20 and len(reqs)==136 and len(gold)==136
    save(out/'public_inputs/requests.jsonl',reqs,'jsonl'); save(out/'private_gold/request_gold.jsonl',gold,'jsonl')
    save(out/'private_gold/matched_structure.jsonl',matched,'jsonl')
    order=sorted([r['world_cluster_id'] for r in panel],key=lambda w:digest([c['seed'],'E7_SHARD',w])); shards=[]
    for sid in range(2):
        ww=set(order[sid::2]); selected=[r for r in reqs if r['world_cluster_id'] in ww]
        path=out/'public_inputs'/f'shard_{sid:03}.jsonl'; save(path,selected,'jsonl')
        shards.append(dict(shard=sid,worlds=sorted(ww),requests=len(selected),request_file=entry(path)))
    save(out/'manifest/shards.json',shards)
    names=['common.py','common_auto_v2.py','review_policy_v2.py','config_auto_v2.json','contracts.py','real_design_v1.py',
           'real_processor_v1.py','e7_design_v1.py','e7_compile_v1.py','e7_processor_v1.py','e7_worker_v1.py','e7_score_v1.py','continuation_job_v1.sh']
    code={r['path']:r for r in lock['code']}
    code.update({str(CODE/n):entry(CODE/n) for n in names})
    frozen=dict(batch=BATCH,models=c['models'],worlds=len(panel),requests_per_model=len(reqs),
        logical_generations_per_model=sum(m['logical_generation_calls'] for m in matched),
        source_panel=entry(source/'private_gold/world_panel.jsonl'),source_lock=entry(source/'manifest/REQUEST_LOCK.json'),
        selection='ALL_D01_WORLDS_NO_PREDICTIONS_READ',source_level='L1_PLUS_CONTROLLED_BRANCH_NOT_NATIVE_L4',
        code=list(code.values()),public_inputs=[entry(out/'public_inputs/requests.jsonl'),entry(out/'manifest/shards.json')]+[s['request_file'] for s in shards],
        private_inputs=[entry(out/'private_gold'/n) for n in ('request_gold.jsonl','matched_structure.jsonl')],
        parent_policy='OWN_MODEL_RAW_VERBATIM_INCLUDING_INVALID_AND_NULL',
        parser_frozen=True,human_review_gate=False,semantic_retries=0,
        primary_metrics=['JOINT_FACT_ACCURACY','NEUTRAL_PARENT_MINUS_EXPOSED_PARENT','OWN_FEEDBACK_MINUS_READONLY',
                         'READONLY_MINUS_ONESHOT','PROTECTED_AND_BASE_AND_BRANCH_ALL_CORRECT'],
        scientific_claim_limits='EXTERNALIZED_STATE_NOT_DIRECT_INTERNAL_WORLD_STATE',bootstrap_worlds=5000)
    save(out/'manifest/REQUEST_LOCK.json',frozen)
    save(out/'reports/COMPILE_ACCEPTANCE.json',dict(status='PASS',worlds=len(panel),requests_per_model=len(reqs),
        tests=tests,source_predictions_read=False,job_id=os.environ['SLURM_JOB_ID']))
    print(json.dumps(dict(status='E7_FROZEN',worlds=len(panel),requests_per_model=len(reqs))),flush=True)


if __name__=='__main__': main()
