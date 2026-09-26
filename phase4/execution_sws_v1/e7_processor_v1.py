"""Preflight static E7 inputs and dynamic templates; never fabricate parent reports."""
import sys
from common_auto_v2 import *
from e7_design_v1 import BATCH
from real_processor_v1 import verify


def main():
    p=arguments(__doc__);p.add_argument('--model',required=True);a=p.parse_args();c,root=setup(a)
    if a.model not in c['models']: raise ValueError('UNAUTHORIZED_MODEL')
    out=root/'batches'/BATCH; lock=load(out/'manifest/REQUEST_LOCK.json'); verify(lock['code']+lock['public_inputs'])
    sys.path.insert(0,str(Path(c['project'])/'src'));sys.path.insert(0,str(Path(c['project'])/'research/state_binding_phase_a1/core_execution_v3'))
    import pipeline_v3
    audit=pipeline_v3.install_gold_guard();pipe=pipeline_v3.Pipeline(dict(c,visual_hash_version='PURE_MEDIA_TENSORS_V3_SHARED_RUNTIME'),a.model)
    records=[];previous=None;media={}
    for r in rows(out/'public_inputs/requests.jsonl'):
        if previous!=r['world_cluster_id']:pipe.image_cache.clear();previous=r['world_cluster_id']
        batch,pres,_=pipe.process(r); mh=digest(r['payload']['media'])
        if mh in media and media[mh]!=pres['presentation_hash']:raise ValueError('VISUAL_HASH_CHANGED')
        media[mh]=pres['presentation_hash']
        records.append(dict(pres,input_token_ids=batch['input_ids'][0].tolist(),request_id=r['request_id'],
            input_kind='DYNAMIC_TEMPLATE_NOT_ACTUAL_CHILD' if r['parent_request_ids'] else 'ACTUAL_STATIC_REQUEST',
            model=a.model,request_hash=r['model_independent_request_hash'],human_verified=False))
    dest=out/'review'/a.model;save(dest/'processor_records.jsonl',records,'jsonl')
    save(dest/'PROCESSOR_ACCEPTANCE.json',dict(status='PASS_STATIC_AND_MEDIA_TEMPLATES',model=a.model,requests=len(records),
        dynamic_actual_text_check='MUST_BE_RECORDED_ON_GPU_AFTER_OWN_PARENT_OUTPUT',records=entry(dest/'processor_records.jsonl'),
        request_lock=entry(out/'manifest/REQUEST_LOCK.json'),gold_access_audit=dict(audit),human_review_gate=False,job_id=os.environ['SLURM_JOB_ID']))
    print(json.dumps(dict(status='E7_PROCESSOR_READY',model=a.model,requests=len(records))),flush=True)


if __name__=='__main__': main()
