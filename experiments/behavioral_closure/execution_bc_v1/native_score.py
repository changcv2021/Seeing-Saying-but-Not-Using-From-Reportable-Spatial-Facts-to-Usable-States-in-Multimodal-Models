"""Gold-blind normalization process, then separate deterministic content scoring."""
from collections import Counter
from bc_common import *
from interface_repair_v3.adapter import normalize

def main():
    p=cli(__doc__);p.add_argument('--batch',required=True);p.add_argument('--model',required=True)
    p.add_argument('--stage',choices=['normalize','score'],required=True);a=p.parse_args();c,sws,out=context(a)
    if a.batch not in ('native_e8_measurement_v1',) or a.model not in c['models']:raise ValueError('UNAUTHORIZED_BATCH_MODEL')
    if a.dry_run:print('Gold-blind normalize then deterministic score '+a.batch);return
    src=out/'batches'/a.batch;dest=src/'scores'/a.model/('snapshot_'+os.environ['SLURM_JOB_ID'])
    extra=load(src/'manifest/NATIVE_EXTENSION_LOCK.json')
    for ref in extra['code']+[extra['request_lock']]:check(ref)
    lock=load(src/'manifest/REQUEST_LOCK.json')
    for ref in lock['code']+lock['public_inputs']:check(ref)
    req={r['request_id']:r for r in rows(src/'public_inputs/requests.jsonl')}
    if a.stage=='normalize':
        sys.path.insert(0,str(Path(c['project'])/'research/state_binding_phase_a1/core_execution_v3'))
        from pipeline_v3 import install_gold_guard
        guard=install_gold_guard();result=[]
        for sh in load(src/'manifest/shards.json'):
            for r in rows(sh['request_file']['path']):
                path=src/'raw'/a.model/f'shard_{sh["shard"]:03}'/'records'/(r['request_id']+'.json')
                rec=dict(request_id=r['request_id'],world_cluster_id=r['world_cluster_id'],status='NOT_RUN')
                if path.exists():
                    raw=load(path)
                    if raw['request_hash']!=r['model_independent_request_hash']:raise ValueError('RAW_REQUEST_HASH_CHANGED')
                    rec.update(status='RETURNED',normalization=normalize(raw['raw_response'],r['schema']),raw=entry(path),
                        output_tokens=raw['output_tokens'],truncated=raw['truncated'],raw_response=raw['raw_response'])
                result.append(rec)
        save(dest/'canonical_views.jsonl',result,'jsonl');save(dest/'NORMALIZE_ACCEPTANCE.json',dict(gold_access_audit=guard,rows=len(result),code=entry(__file__)))
        return
    gold={r['request_id']:r for r in rows(src/'private_gold/request_gold.jsonl')};result=[];rawindex=[]
    for rec in rows(dest/'canonical_views.jsonl'):
        rid=rec['request_id'];r=req[rid];g=gold[rid]['expected'];parsed=rec.get('normalization',{}).get('normalized',{});got=parsed.get('component_values',{})
        returned=rec['status']=='RETURNED'
        # Strict JSON type identity, including nested fact values.
        correct=digest(got)==digest(g) and parsed.get('status')=='VALID' if returned else None
        row=dict(request_id=rid,world_cluster_id=r['world_cluster_id'],model_id=a.model,experiment=r['experiment'],condition=r['condition'],
            split=r['split'],sample_family=r['sample_family'],execution_status=rec['status'],schema_status=parsed.get('status','NOT_RUN'),
            strict_schema_status=rec.get('normalization',{}).get('strict',{}).get('status','NOT_RUN'),component_values=got,expected=g,content_correct=correct,
            raw_path=rec.get('raw',{}).get('path'),raw_sha256=rec.get('raw',{}).get('sha256'),truncated=rec.get('truncated'),
            output_tokens=rec.get('output_tokens'))
        result.append(row)
        if returned:rawindex.append(dict(request_id=rid,model=a.model,**rec['raw']))
    csvsave(dest/'all_physical_request_scores.csv',result);save(dest/'raw_response_index.jsonl',rawindex,'jsonl')
    acc=dict(status='COMPLETE' if len(rawindex)==len(req) else 'PARTIAL_NOT_RUN_RETAINED',batch=a.batch,model=a.model,
        planned=len(req),returned=len(rawindex),not_run=len(req)-len(rawindex),worlds=len({r['world_cluster_id'] for r in req.values()}),
        invalid=sum(r['schema_status']=='INVALID' for r in result),job_id=os.environ['SLURM_JOB_ID'],
        scorer='SWS_V3_GOLD_BLIND_NORMALIZATION_THEN_EXACT_TYPED_CONTENT',
        normalization=entry(dest/'canonical_views.jsonl'),scores=entry(dest/'all_physical_request_scores.csv'),raw_index=entry(dest/'raw_response_index.jsonl'))
    save(dest/'SCORE_ACCEPTANCE.json',acc);print(json.dumps(acc),flush=True)

if __name__=='__main__':main()

