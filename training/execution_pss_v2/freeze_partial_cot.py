"""Apply the researcher's explicit all-pool partial-CoT policy without changing gold."""
from collections import Counter
from common import *

def main():
    a=cli(__doc__).parse_args();root=a.run_root;out=root/'partial_cot_approved_v1'
    if a.dry_run:print(out);return
    compute()
    if (out/'MANIFEST.json').exists() and a.resume:return
    proof_root=root/'supervision_v3';rejects={r['sample_id']:r for r in rows(proof_root/'rejects.jsonl')}
    stats={};hashes={}
    for split in ('train','dev'):
        aa=list(rows(proof_root/split/'answer.jsonl'));cc={r['sample_id']:r for r in rows(proof_root/split/'cot.jsonl')};merged=[]
        for answer in aa:
            sid=answer['sample_id']
            if sid in cc:
                record=dict(cc[sid],supervision_mode='VERIFIED_RATIONALE_PLUS_ANSWER',rationale_available=True)
                if any(record[k]!=answer[k] for k in ('split','underlying_world_id','global_world_id','request')):raise ValueError('POOL_OR_INPUT_MISMATCH')
            else:
                reject=rejects[sid]
                record=dict(answer,supervision_mode='ANSWER_ONLY_FALLBACK_USER_APPROVED',rationale_available=False,
                    rationale_unavailable_reason=reject['reason'])
                if record.get('task_prompt') or record['end_turn']:raise ValueError('FALLBACK_INTERFACE_CHANGED')
            merged.append(record)
        if len(merged)!=len(aa) or len({r['sample_id'] for r in merged})!=len(aa):raise ValueError('SAMPLE_POOL_MISMATCH')
        if not set(cc)<=set(r['sample_id'] for r in aa):raise ValueError('EXTRA_COT_SAMPLE')
        target=out/split/'cot.jsonl';write(target,merged,True);hashes[str(target)]=sha(target)
        stats[split]=dict(total=len(merged),verified_cot=len(cc),answer_only_fallback=len(merged)-len(cc),
            modes=dict(Counter(r['supervision_mode'] for r in merged)),
            fallback_by_level=dict(Counter(r['level'] for r in merged if not r['rationale_available'])))
    if stats['train']!={'total':13476,'verified_cot':13188,'answer_only_fallback':288,
        'modes':{'VERIFIED_RATIONALE_PLUS_ANSWER':13188,'ANSWER_ONLY_FALLBACK_USER_APPROVED':288},'fallback_by_level':{'L4':288}}:raise ValueError('APPROVED_TRAIN_COUNTS_CHANGED')
    approval=dict(date='2026-09-22',source='explicit_user_async_reply',
        text='保持全部训练池：13,188 条用可验证 CoT，288 条仅监督答案；论文明确说明这是部分 CoT 监督',
        definition='PARTIAL_COT_SUPERVISION_ON_IDENTICAL_ORIGINAL_SAMPLE_POOL',
        dev_rule='Same deterministic availability/fallback policy; no model-performance filtering',
        prohibition='Do not call this 100% rationale coverage. No synthetic rationale or original-sample removal.')
    write(out/'USER_APPROVAL.json',approval)
    result=dict(status='PASS_USER_APPROVED_PARTIAL_COT_SAME_POOL',counts=stats,output_hashes=hashes,
        source_manifest_sha256=sha(proof_root/'MANIFEST.json'),test_opened=False,
        formal_training_started=False,job_id=os.environ['SLURM_JOB_ID'],code_sha256=sha(__file__))
    write(out/'MANIFEST.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
