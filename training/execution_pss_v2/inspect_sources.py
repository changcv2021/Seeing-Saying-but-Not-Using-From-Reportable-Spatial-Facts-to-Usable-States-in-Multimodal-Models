"""Inspect remaining training proof gaps without reading test labels or predictions."""
from collections import Counter,defaultdict
from common import *

def main():
    a=cli(__doc__).parse_args();out=a.run_root/'recovery_audit_v1'
    if a.dry_run:print(out);return
    compute()
    if (out/'SUMMARY.json').exists() and a.resume:return
    rejected={r['sample_id']:r for r in rows(a.run_root/'supervision_v2/rejects.jsonl')}
    gold={r['sample_id']:r for s in ('train','dev') for r in rows(a.run_root/'data'/s/'private_gold.jsonl')}
    needed={gold[k]['pair_id'] for k in rejected}
    pairs={r['pair_id']:r for r in rows(REPO/'l4/v3_3/release/pairs.l4_three_part_v3.jsonl') if r['pair_id'] in needed}
    types=Counter((p.get('native_subtype'),p['supported_claim']['graph']['predicate'],p.get('dependency_type')) for p in pairs.values())
    examples={}
    for pid,p in pairs.items():
        key=p['supported_claim']['graph']['predicate']
        if key not in examples:examples[key]=p
    write(out/'missing_pair_examples.json',examples)
    # Search all existing versions; existence of an artifact is not proof acceptance.
    candidates=[]
    for path in sorted((REPO/'transition_micrographs').glob('*/prestates*.jsonl')):
        found=[]
        wanted={(p.get('source',{}).get('scene_id'),p.get('source',{}).get('change_id'),p.get('source',{}).get('question_id')) for p in pairs.values()}
        for b in rows(path):
            key=(b.get('scene_id'),b.get('change_id'),b.get('question_id'))
            if key in wanted:found.append(b)
        if found:candidates.append(dict(path=str(path),sha256=sha(path),bundles=found))
    write(out/'matching_existing_bundles.jsonl',candidates,True)
    malformed=[]
    for split in ('train','dev'):
        for row in rows(a.run_root/'supervision_v2'/split/'cot.jsonl'):
            if 'Initially, .' in row['target']:malformed.append(dict(sample_id=row['sample_id'],split=split,reason='EMPTY_INITIAL_FACT_TEXT'))
    write(out/'rationale_quality_rejects.jsonl',malformed,True)
    result=dict(missing_pairs=len(pairs),missing_samples=len(rejected),categories={str(k):v for k,v in types.items()},
        existing_bundle_candidates=sum(len(c['bundles']) for c in candidates),candidate_files=len(candidates),
        empty_initial_rationales=len(malformed),test_opened=False,job_id=os.environ['SLURM_JOB_ID'])
    write(out/'SUMMARY.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
