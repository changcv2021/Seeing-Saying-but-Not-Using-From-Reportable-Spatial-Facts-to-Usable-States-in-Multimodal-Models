"""Audit actual new rank logs against every frozen exposure before admitting test."""
import argparse
import collections
import os
from plan import *
from audit import signature, summarize


def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--seed',type=int,choices=SEEDS,required=True)
    args=parser.parse_args();dest=seed_output(args.seed);key=f'{METHOD}__seed_{args.seed}'
    if not os.environ.get('SLURM_JOB_ID'):raise ValueError('SLURM_REQUIRED')
    from trainer import check_plan
    p=check_plan(dest);run=dest/'runs'/key
    complete=read(run/'TRAINING_COMPLETE.json')
    units=read(dest/'units.json');catalog=read(dest/'catalog.json');receipts=read(dest/'processor_receipts.json')
    expected={(i,k):(u['sample_id'],w,u['source_index'],u['stream']) for i,u in enumerate(units) for k,w in u['records']}
    seen=set();steps=set();hashes={};totals=collections.Counter()
    for path in sorted((run/'attempts').glob('*/updates_rank_*.jsonl')):
        hashes[str(path)]=sha(path);rank=int(path.stem.rsplit('_',1)[1])
        for update in rows(path):
            marker=(rank,update['step'])
            if marker in steps:raise ValueError('DUPLICATE_UPDATE_IN_ACTUAL_LOG')
            steps.add(marker)
            for r in update['receipts']:
                marker=(r['index'],r['key'])
                value=(r['sample_id'],r['weight'],r['source_index'],r['stream'])
                if marker in seen or expected.get(marker)!=value:raise ValueError('ACTUAL_EXPOSURE_NOT_FROZEN')
                if signature(r)!=receipts[r['key']]:raise ValueError('ACTUAL_PROCESSOR_CHANGED')
                if r['index']//16+1!=update['step'] or r['index']%2!=rank:raise ValueError('ACTUAL_STEP_RANK_MISMATCH')
                seen.add(marker)
                totals['input_tokens']+=r['prompt_tokens'];totals['target_tokens']+=r['target_tokens']
                totals['non_padding_tokens']+=r['prompt_tokens']+r['target_tokens'];totals['forward_records']+=1
    if seen!=set(expected) or len(steps)!=p['optimizer_updates']*2:raise ValueError('ACTUAL_TRAINING_INCOMPLETE')
    planned=read(OUTPUT/'audit/EXPOSURE_AUDIT.json')['audits'][key]['exposure']
    for field in totals:
        if totals[field]!=planned[field]:raise ValueError('TOKEN_OR_EXPOSURE_TOTAL_MISMATCH:'+field)
    if complete['progress']['step']!=p['optimizer_updates']:raise ValueError('FINAL_STEP')
    write(dest/'ACTUAL_EXPOSURE_CONFIRMED.json',dict(status='PASS_EXACT_FROZEN_EXPOSURES_AND_PROCESSOR_TOKENS',
        seed=args.seed,optimizer_updates=p['optimizer_updates'],totals=dict(totals),raw_log_hashes=hashes,
        l4_per_key_counts_and_weights='EXACTLY_EQUAL_TO_CORRESPONDING_OLD_PSS_L4',
        exposure_audit_sha256=sha(OUTPUT/'audit/EXPOSURE_AUDIT.json'),test_payload_unchanged=True))
    from evaluate import prepare
    prepare(args.seed)
    from control import submit_evaluation
    submit_evaluation(args.seed)


if __name__=='__main__':main()
