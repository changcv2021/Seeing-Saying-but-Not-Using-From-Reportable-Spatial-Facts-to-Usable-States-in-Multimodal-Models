"""Recover omitted val QA gold with the existing deterministic adapter, not a model."""
import sys
from collections import Counter, defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from common_auto_v2 import *
from data_continuation_v1.prepare import source_guard,validate_fact_pairs
from real_compile_v1 import SOURCE_IMAGES,REV

def main():
    a=arguments(__doc__).parse_args();c,root=setup(a)
    if a.dry_run:print('Reconstruct source-certified facts for locally complete unexposed captures; preserve original release.');return
    dest=root/'preparation/holdout_val_rebuild_v1_20260910'
    if (dest/'ACCEPTANCE.json').exists():print('ALREADY_COMPLETE');return
    p=Path(c['project']);sys.path.insert(0,str(p/'src'))
    from spaceconflict.adapters.ca_vqa import adapt
    from spaceconflict.canonical import _canonical_fact,_media
    guard=source_guard()
    eligibility=root/'preparation/holdout_repair_v1_20260910/candidate_qualification.jsonl'
    worlds={r['world_cluster_id']:r for r in rows(eligibility)}
    stage=p/'data/staging/ca_vqa'/REV/'ca_vqa_val_metadata_v1'
    report=p/'reports/ca_vqa/metadata_extract.ca_vqa_val_metadata_v1.json';reference=load(report)
    inputs=[entry(stage/(task+'.jsonl')) for task in ('binary','cardinality','multichoice')]
    for ref in inputs:
        key=str(Path(ref['path']).relative_to(p))
        if reference['output_hashes'][key].removeprefix('sha256:')!=ref['sha256']:raise ValueError('IMMUTABLE_METADATA_HASH_MISMATCH')
    save(dest/'REBUILD_LOCK.json',dict(created_at=now(),code=entry(__file__),inputs=inputs,eligibility=entry(eligibility),
        adapter=entry(p/'src/spaceconflict/adapters/ca_vqa.py'),canonicalizer=entry(p/'src/spaceconflict/canonical.py'),
        selection='ALL_12_PREVIOUSLY_FROZEN_LOCAL_UNEXPOSED_CAPTURE_IDS',model_used=False,original_release_write=False))
    facts=defaultdict(dict);source_rows=[];rejects=[];seen=Counter();media_checks={}
    for ref in inputs:
        for line,row in enumerate(rows(ref['path']),1):
            w='arkitscenes:'+row['capture_id']
            if w not in worlds:continue
            seen[w]+=1
            result=adapt(row,line).to_dict()
            if not result['reconstruction_pass'] or result['reject_codes']:
                rejects.append(dict(world_cluster_id=w,source_id=row['id'],reasons=result['reject_codes'] or ['RECONSTRUCTION_FAILED']));continue
            missing=False
            for loc in row['media_roles'].values():
                file=SOURCE_IMAGES/'cavqa_val'/loc
                if str(file) not in media_checks:
                    media_checks[str(file)]=entry(file) if file.is_file() else dict(path=str(file),status='MISSING')
                if 'sha256' not in media_checks[str(file)]:missing=True
            if missing:
                rejects.append(dict(world_cluster_id=w,source_id=row['id'],reasons=['SOURCE_MEDIA_MISSING']));continue
            mm=_media('ca_vqa',dict(frame_roles=row['media_roles'],validation_scope='ACTUAL_BYTES_CHECKED_REBUILD_V1'),dict(source_revision=REV))
            for f in result['facts']:
                ff=_canonical_fact(f,result,mm);facts[w][ff['fact_id']]=ff
            source_rows.append(dict(world_cluster_id=w,source_file=ref,source_line=line,source_record=row,adapter_result=result))
    catalog=[]
    for w,ff in sorted(facts.items()):
        gp=dest/'private_gold/source_graphs'/(digest(w)[:24]+'.json')
        save(gp,dict(global_world_id=w,facts=list(ff.values()),source_revision=REV,derivation='EXISTING_ADAPTER_SOURCE_ANSWER_ROUNDTRIP'))
        for f in ff.values():catalog.append(dict(world_cluster_id=w,fact=f,source_graph=entry(gp)))
    cp=dest/'private_gold/source_fact_catalog.jsonl';save(cp,catalog,'jsonl')
    pairs=validate_fact_pairs(c,set(worlds),cp,rejects);summaries=[];chosen=[]
    for w in sorted(worlds):
        count={family:len(pairs.get((w,family),[])) for family in ('COUNT','NONCOUNT_RELATION')}
        summaries.append(dict(world_cluster_id=w,source_qa_rows=seen[w],canonical_facts=len(facts[w]),independent_pair_counts=count))
        for family in count:
            if count[family]:
                rank,aa,bb=pairs[w,family][0]
                chosen.append(dict(world_cluster_id=w,family=family,source_pair=[aa,bb],rank=rank,split='UNASSIGNED'))
    save(dest/'private_gold/source_reconstruction.jsonl',source_rows,'jsonl')
    save(dest/'private_gold/independent_pairs.jsonl',chosen,'jsonl')
    save(dest/'source_qa_coverage.jsonl',summaries,'jsonl')
    save(dest/'media_checks.jsonl',media_checks.values(),'jsonl')
    save(dest/'rejects.jsonl',rejects,'jsonl')
    acc=dict(status='SOURCE_REBUILD_COMPLETE_NOT_HOLDOUT_CERTIFICATION',created_at=now(),job_id=os.environ['SLURM_JOB_ID'],
        local_candidate_worlds=len(worlds),worlds_with_source_rows=len(seen),source_rows=sum(seen.values()),
        canonical_facts=len(catalog),pair_worlds=len({r['world_cluster_id'] for r in chosen}),
        family_worlds=dict(Counter(r['family'] for r in chosen)),rejects=len(rejects),prediction_guard=guard,
        global_holdout_frozen=False,remaining='Source-pool identity and actual-media duplication certificate before split and inference')
    save(dest/'ACCEPTANCE.json',acc);print(json.dumps(acc),flush=True)

if __name__=='__main__':main()
