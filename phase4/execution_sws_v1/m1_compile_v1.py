"""Outcome-independent 9B structural readout manifest; no mechanism selection."""
from common_auto_v2 import *
from real_design_v1 import BATCH as SOURCE_BATCH
from real_processor_v1 import verify

BATCH='M1_structural_d01_v1'


def main():
    a=arguments(__doc__).parse_args();c,root=setup(a);source=root/'batches'/SOURCE_BATCH;dest=root/'whitebox'/BATCH
    old=load(source/'manifest/REQUEST_LOCK.json');verify(old['code']+old['public_inputs']+old['private_inputs'])
    m0=root/'whitebox/M0_v1/M0_ACCEPTANCE.json'
    if load(m0)['status']!='PASS':raise ValueError('M0_NOT_EQUIVALENT')
    reqs={r['request_id']:r for r in rows(source/'public_inputs/requests.jsonl')}
    gold={r['request_id']:r for r in rows(source/'private_gold/request_gold.jsonl')}
    matched=list(rows(source/'private_gold/matched_structure.jsonl'));worlds=sorted({m['world_cluster_id'] for m in matched})
    selected=set();pairs=[]
    for w in worlds:
        pool=[m for m in matched if m['world_cluster_id']==w and m['experiment']=='E2' and m['wording']=='W0']
        m=min(pool,key=lambda x:digest([c['seed'],'M1_STRUCTURAL_OFFSET_V1',w,x['candidate_value']]))
        selected.update(m[k] for k in ('neutral','false','sham'));pairs.append(m)
        for other in matched:
            if other['world_cluster_id']!=w:continue
            if other['experiment']=='E4':selected.update(other[k] for k in ('S0','SA','SB'))
            if other['experiment']=='E3':selected.update(other[k] for k in ('branch_value','branch_base','branch_protection'))
    picked=[r for r in reqs.values() if r['request_id'] in selected]
    if len(worlds)>96 or any(r['split']!='discovery' for r in picked):raise ValueError('STRUCTURAL_SCOPE')
    labels=[]
    for r in picked:
        g=gold[r['request_id']]
        if r['schema']['kind']!='value':raise ValueError('M1_VALUE_INPUTS_ONLY')
        labels.append(dict(request_id=r['request_id'],world_cluster_id=r['world_cluster_id'],family=r['sample_family'],
            true_value=g['expected']['value'],candidate_value=g['candidate_value'],target_identity=r['target_state'],
            information_role=r['information_role'],target_bound_value=g['target_gold'],protected_value=g['protected_gold'],
            source_fact_ids=g['facts'],semantic_selection='SOURCE_STRATIFIED_NOT_MODEL_ERROR',
            internal_group_fold=int(digest([c['seed'],'M1_INTERNAL_GROUP_FOLD',r['world_cluster_id']])[:8],16)%5))
    save(dest/'public_inputs/requests.jsonl',picked,'jsonl');save(dest/'private_gold/measurement_labels.jsonl',labels,'jsonl')
    save(dest/'private_gold/neutral_candidate_sham_pairs.jsonl',pairs,'jsonl')
    code={ref['path']:ref for ref in old['code']}
    for name in ('m1_compile_v1.py','m1_worker_v1.py','m1_collect_v1.py','continuation_job_v1.sh'):
        code[str(CODE/name)]=entry(CODE/name)
    plan=dict(model='qwen35_9b',worlds=len(worlds),requests=len(picked),selected_from_all_D01_worlds=True,
        semantic_positions=['observation_end','target_end','role_wrapper_end','candidate_end','query_end','answer_start'],
        max_positions_per_request=6,modules='LANGUAGE_BLOCK_OUTPUTS_ONLY',all_token_dump=False,
        noop_last_logit_abs_tolerance=1e-5,probe_min_train_worlds_per_class=10,probe_min_validation_worlds_per_class=5,
        probe_underpowered_policy='RETAIN_MEASUREMENTS_AND_LABELS_NO_IN_SAMPLE_MECHANISM_CLAIM',
        canonical_logprob_interventions='NOT_RUN_BY_M1_COLLECTION',m0=entry(m0),
        code=list(code.values()),public_inputs=[entry(dest/'public_inputs/requests.jsonl')],
        private_inputs=[entry(dest/'private_gold/measurement_labels.jsonl'),entry(dest/'private_gold/neutral_candidate_sham_pairs.jsonl')],
        source_lock=entry(source/'manifest/REQUEST_LOCK.json'),
        source_processor=entry(source/'review/qwen35_9b/PROCESSOR_ACCEPTANCE.json'),
        human_review_gate=False,predictions_read=False,scientific_review_grade='AUTO_ONLY_PROVISIONAL')
    save(dest/'manifest/M1_LOCK.json',plan)
    save(dest/'COMPILE_ACCEPTANCE.json',dict(status='PASS',worlds=len(worlds),requests=len(picked),job_id=os.environ['SLURM_JOB_ID']))
    print(json.dumps(dict(status='M1_STRUCTURAL_FROZEN',worlds=len(worlds),requests=len(picked))),flush=True)


if __name__=='__main__':main()
