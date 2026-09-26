"""Seal prepared supervision and report coverage, without freezing unmeasured training budgets."""
from collections import Counter
from common import *
from state_schema import parse_state

def main():
    a=cli(__doc__).parse_args();root=a.run_root;out=root/'prepared_data_v1'
    if a.dry_run:print(out);return
    compute()
    if (out/'MANIFEST.json').exists() and a.resume:return
    if read(root/'partial_cot_approved_v1/MANIFEST.json')['status']!='PASS_USER_APPROVED_PARTIAL_COT_SAME_POOL':raise ValueError('COT_POLICY_GATE')
    groups={r['global_world_id']:r['underlying_world_id'] for r in rows(root/'data/world_groups.jsonl')}
    worlds={};summary={};hashes={}
    for split in ('train','dev'):
        originals=list(rows(root/'supervision_v3'/split/'answer.jsonl'));cot=list(rows(root/'partial_cot_approved_v1'/split/'cot.jsonl'))
        if [r['sample_id'] for r in originals]!=[r['sample_id'] for r in cot]:raise ValueError('ORDER_OR_POOL_MISMATCH')
        worlds[split]={r['underlying_world_id'] for r in originals}
        for x,y in zip(originals,cot):
            if x['request']!=y['request']:raise ValueError('COT_MEDIA_OR_INPUT_POOL_CHANGE')
        sources=[root/'supervision_v3'/split/'state.jsonl',root/'trajectory_aux_v1'/split/'state.jsonl']
        aux=[r for p in sources for r in rows(p)]
        for r in originals+cot+aux:
            if r['split']!=split or groups[r['global_world_id']]!=r['underlying_world_id'] or r['underlying_world_id'] not in worlds[split]:raise ValueError('AUX_SPLIT_INHERITANCE')
        for r in aux:
            if parse_state(r['target'])!=r['state']:raise ValueError('STATE_ROUNDTRIP')
        # Duplicated observed states across different frozen trajectories are reported,
        # not presented as distinct physical worlds or extra unique evidence.
        unique={digest([r['underlying_world_id'],r['request'].get('media'),r['task_prompt'],r['target']]) for r in aux}
        summary[split]=dict(original_answer_samples=len(originals),world_components=len(worlds[split]),
            levels=dict(Counter(r['level'] for r in originals)),cot=len(cot),cot_rationale=sum(r['rationale_available'] for r in cot),
            cot_answer_only=sum(not r['rationale_available'] for r in cot),state_records=len(aux),unique_state_input_targets=len(unique),
            state_by_level=dict(Counter(r['level'] for r in aux)),state_by_stage=dict(Counter(r['stage'] for r in aux)))
        for p in sources+[root/'supervision_v3'/split/'answer.jsonl',root/'partial_cot_approved_v1'/split/'cot.jsonl']:hashes[str(p)]=sha(p)
    if worlds['train']&worlds['dev']:raise ValueError('TRAIN_DEV_WORLD_OVERLAP')
    manifest=dict(status='PASS_PREPARED_SUPERVISION',counts=summary,input_hashes=hashes,
        split_audit_sha256=sha(root/'SPLIT_AUDIT.json'),cot_approval_sha256=sha(root/'partial_cot_approved_v1/USER_APPROVAL.json'),
        test_requests_unchanged=True,test_gold_opened=False,formal_training_started=False,
        engineering_gate='PENDING_GPU',budget_gate='NOT_FROZEN_REQUIRES_GPU_THROUGHPUT_AND_MATCHING_AUDIT',
        code_sha256=sha(__file__),job_id=os.environ['SLURM_JOB_ID'])
    write(out/'MANIFEST.json',manifest);print(json.dumps({k:v for k,v in manifest.items() if k!='input_hashes'}),flush=True)

if __name__=='__main__':main()
