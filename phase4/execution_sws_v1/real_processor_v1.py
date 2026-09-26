"""Actual processor records for every frozen request; waived human review."""
import sys
from common_auto_v2 import *
from real_design_v1 import BATCH


def verify(items):
    for ref in items:
        if sha(ref['path'])!=ref['sha256'].removeprefix('sha256:'): raise ValueError('LOCK_CHANGED:'+ref['path'])


def main():
    p=arguments(__doc__); p.add_argument('--model',required=True); a=p.parse_args(); c,root=setup(a)
    if a.model not in c['models']: raise ValueError('UNAUTHORIZED_MODEL')
    out=root/'batches'/BATCH; lock=load(out/'manifest/REQUEST_LOCK.json'); verify(lock['code']+lock['public_inputs'])
    if a.dry_run: print('Actual CPU processor, no human signature requirement'); return
    accepted=out/'review'/a.model/'PROCESSOR_ACCEPTANCE.json'
    if accepted.exists():
        old=load(accepted); verify([old['records']]); print('REUSED_PROCESSOR_ACCEPTANCE'); return
    sys.path.insert(0,str(Path(c['project'])/'src'))
    sys.path.insert(0,str(Path(c['project'])/'research/state_binding_phase_a1/core_execution_v3'))
    import pipeline_v3
    audit=pipeline_v3.install_gold_guard()
    pipe=pipeline_v3.Pipeline(dict(c,visual_hash_version='PURE_MEDIA_TENSORS_V3_SHARED_RUNTIME'),a.model)
    records=[]; presentations={}; media_images={}; world_media={}; previous_world=None
    for n,r in enumerate(rows(out/'public_inputs/requests.jsonl'),1):
        if r['world_cluster_id']!=previous_world: pipe.image_cache.clear(); previous_world=r['world_cluster_id']
        batch,pres,images=pipe.process(r)
        mh=digest(r['payload']['media']); ph=pres['presentation_hash']
        if mh in presentations and presentations[mh]!=ph: raise ValueError('SAME_MEDIA_DIFFERENT_VISUAL_HASH')
        presentations[mh]=ph
        if mh not in media_images:
            paths=[]
            for i,im in enumerate(images or []):
                dst=out/'review'/a.model/'processed'/(mh+f'_{i}.png'); dst.parent.mkdir(parents=True,exist_ok=True)
                if not dst.exists(): im.save(dst)
                paths.append(entry(dst))
            media_images[mh]=paths
        rec=dict(pres,model_id=a.model,model_revision=pipe.mc['revision'],request_hash=r['model_independent_request_hash'],
                 input_token_ids=batch['input_ids'][0].tolist(),attention_mask=batch['attention_mask'][0].tolist(),
                 processed_images=media_images[mh],review_status=c['review']['default_review_status'],
                 actual_media_automatically_processed=True,human_verified=False,raw_generation_status='NOT_RUN')
        records.append(rec)
        if n%100==0: print(json.dumps(dict(stage='PROCESSOR',model=a.model,processed=n)),flush=True)
    path=out/'review'/a.model/'processor_records.jsonl'; save(path,records,'jsonl')
    # Every paired condition using the same media is checked, without loading gold.
    save(accepted,dict(status='PASS',job_id=os.environ['SLURM_JOB_ID'],model_id=a.model,requests=len(records),
        records=entry(path),request_lock=entry(out/'manifest/REQUEST_LOCK.json'),
        distinct_media_presentations=len(presentations),same_media_visual_hash_check='PASS',
        input_tokens_max=max(r['input_tokens'] for r in records),gold_access_audit=dict(audit),
        human_review_required=False,review_status=c['review']['default_review_status'],scientific_review_grade='AUTO_ONLY_PROVISIONAL'))
    print(json.dumps(dict(status='PROCESSOR_PASS',model=a.model,requests=len(records))),flush=True)


if __name__=='__main__': main()
