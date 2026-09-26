"""Locate missing native evidence/adapter coverage, including permitted train data."""
import sys
from collections import Counter, defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from common_auto_v2 import *
from data_continuation_v1.prepare import source_guard
from real_design_v1 import qualified_fact

def main():
    a=arguments(__doc__).parse_args();c,root=setup(a)
    if a.dry_run: print('Profile permitted unexposed source annotations; no model calls.');return
    dest=root/'preparation/holdout_source_profile_v1_20260910'
    if (dest/'ACCEPTANCE.json').exists():print('ALREADY_COMPLETE');return
    guard=source_guard();inv=root/'repairs/world_identity_v2/inventory'
    local={r['world_cluster_id'] for r in rows(root/'preparation/holdout_repair_v1_20260910/candidate_qualification.jsonl')}
    memberships={r['world_cluster_id']:r for r in rows(inv/'manifest/source_membership_audit.jsonl')}
    eligible={w for w,m in memberships.items() if not m['previously_exposed'] and not m['reasons']}
    counts=Counter(); examples={}; wc=Counter();cat=inv/'private_gold/source_fact_catalog.jsonl'
    for r in rows(cat):
        w=r['world_cluster_id']
        if w not in eligible:continue
        f=r['fact'];g=f.get('grounding',{});p=f.get('provenance',{});ctx=f.get('context',{})
        k=(w in local,p.get('source_dataset'),f['predicate'],ctx.get('scope'),ctx.get('state_id'),tuple(sorted(g)),qualified_fact(f))
        counts[k]+=1;wc[w]+=1
        if k not in examples:examples[k]=r
    csvsave(dest/'source_schema_counts.csv',[dict(local_candidate=k[0],source=k[1],predicate=k[2],scope=k[3],state=k[4],grounding_keys=k[5],old_design_qualified=k[6],facts=n) for k,n in sorted(counts.items(),key=lambda x:str(x[0]))])
    save(dest/'private_gold/schema_examples.jsonl',examples.values(),'jsonl')
    save(dest/'world_fact_counts.jsonl',[dict(world_cluster_id=w,facts=wc[w],local_candidate=w in local) for w in sorted(eligible)],'jsonl')
    missing=[r for r in rows(root/'preparation/holdout_repair_v1_20260910/historical_supplied_media.jsonl') if r['coverage']!='SIGNED_IMAGE']
    save(dest/'historical_media_to_reconcile.jsonl',missing,'jsonl')
    save(dest/'ACCEPTANCE.json',dict(status='SOURCE_PROFILE_COMPLETE',job_id=os.environ['SLURM_JOB_ID'],source=entry(cat),code=entry(__file__),
        local_worlds=len(local),local_with_catalog_facts=sum(wc[w]>0 for w in local),unexposed_permitted_worlds=len(eligible),
        unexposed_with_catalog_facts=len(wc),facts=sum(wc.values()),schemas=len(examples),prediction_guard=guard))
    print(json.dumps(load(dest/'ACCEPTANCE.json')),flush=True)

if __name__=='__main__':main()
