"""Isolated partial E0 snapshot: existing predictions only, not a new test experiment."""
from collections import Counter,defaultdict
import importlib.util
import sys
from common import *
from world_identity_v2 import checked_overlay, repair_root
from snapshot_store_v2 import frozen_predictions

def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def stable_snapshot(path):
    size=path.stat().st_size
    with path.open('rb') as f: data=f.read(size)
    partial=b''
    if data and not data.endswith(b'\n'):
        cut=data.rfind(b'\n')+1; data,partial=data[:cut],data[cut:]
    return data,dict(path=str(path),captured_bytes=size,complete_bytes=len(data),incomplete_tail_bytes=len(partial),snapshot_sha256=hashlib.sha256(data).hexdigest())

def interval(values,seed,repetitions):
    import numpy as np
    if not values: return None,None
    # World resampling stratified by underlying source-family, paired endpoints preserved.
    groups=defaultdict(list)
    for w,num,den in values: groups[w.split(':',1)[0]].append((num,den))
    rng=np.random.default_rng(seed); nums=np.zeros(repetitions); dens=np.zeros(repetitions)
    for group in groups.values():
        ar=np.asarray(group,dtype=float)
        for start in range(0,repetitions,100):
            k=min(100,repetitions-start); ids=rng.integers(0,len(ar),size=(k,len(ar)))
            sums=ar[ids].sum(axis=1); nums[start:start+k]+=sums[:,0]; dens[start:start+k]+=sums[:,1]
    out=nums[dens>0]/dens[dens>0]
    return (float(np.quantile(out,.025)),float(np.quantile(out,.975))) if len(out) else (None,None)

def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('Read existing 3-model baseline snapshot, use frozen 512-prefix parser; no new test inference'); return
    overlay, identity = checked_overlay(c, root)
    identity_root = repair_root(root)
    root = identity_root / 'e0'
    project=Path(c['project']); base=Path(c['baseline']); old=project/'scripts/full_multimodel_20260908_v1'
    legacy=module(old/'common.py','sws_e0_legacy_common'); keep=sys.modules['common']; sys.modules['common']=legacy
    try: policy=module(old/'output_policy.py','sws_e0_output_policy')
    finally: sys.modules['common']=keep
    gold={r['sample_id']:r for r in rows(base/'private_gold.jsonl')}; requests={r['sample_id']:r for r in rows(base/'requests.jsonl')}
    if set(gold)!=set(requests): raise ValueError('BASELINE_INPUT_GOLD_ID_MISMATCH')
    if set(gold) != set(overlay): raise ValueError('REPAIRED_METADATA_GOLD_ID_MISMATCH')
    snapshot_lock = frozen_predictions(root, base, c['models'])
    statistics=[]; coverage=[]; index=[]; allscored=[]; modelrows={}; files=[]
    for m in c['models']:
        predictions={}; duplicates=[]
        for meta in snapshot_lock['files']:
            if meta['model_id'] != m: continue
            snapshot = Path(meta['snapshot_path']); data = snapshot.read_bytes(); files.append(meta)
            for line in data.splitlines():
                r=json.loads(line); sid=r['sample_id']
                if sid in predictions: duplicates.append(sid)
                else: predictions[sid]=r
        if duplicates: raise ValueError('DUPLICATE_BASELINE_PREDICTIONS:'+m+':'+str(duplicates[:5]))
        if set(predictions)-set(requests): raise ValueError('UNEXPECTED_BASELINE_IDS')
        scored=[]
        for sid,r in predictions.items():
            parsed=policy.parse_prediction(r); label=None if r.get('error') else parsed['label']; g=gold[sid]
            item=dict(sample_id=sid,model_id=m,model_revision=r.get('model_revision'),world_cluster_id=overlay[sid]['world_cluster_id'],
                world_identity_resolution=overlay[sid]['resolution'],
                pair_id=g.get('pair_id'),level=g['level'],dataset=g['dataset'],source_split=g['split'],track=g.get('track') or 'NOT_ANNOTATED',
                gold=g['gold'],label=label,correct=label==g['gold'],component=g['component'],schema_valid=parsed['schema_valid'],
                truncated=r.get('finish_reason')=='length',runtime_error=r.get('error'))
            scored.append(item); index.append(dict(model_id=m,request_id=sid,experiment='E0_EXISTING_BASELINE_SNAPSHOT',
                raw_record_sha256=digest(r),public_request_sha256=digest(requests[sid]),original_run=str(base),
                never_reused_as_SWS_mechanism_request=True))
        allscored.extend(scored); modelrows[m]={r['sample_id']:r for r in scored}
        cells=defaultdict(list)
        for r in scored:
            for key in [('OVERALL','ALL'),('LEVEL',r['level']),('SOURCE',r['dataset']),('TRACK',r['track']),('SOURCE_SPLIT',r['source_split'])]: cells[key].append(r)
        # Explicitly report even a completely unreturned stratum (zero != nonexistent).
        for g in gold.values():
            for key in [('OVERALL','ALL'),('LEVEL',g['level']),('SOURCE',g['dataset']),('TRACK',g.get('track') or 'NOT_ANNOTATED'),('SOURCE_SPLIT',g['split'])]: cells.setdefault(key, [])
        for cell,rs in sorted(cells.items()):
            expectations=[g for g in gold.values() if cell[0]=='OVERALL' or (g.get('track') or 'NOT_ANNOTATED' if cell[0]=='TRACK' else g[{'LEVEL':'level','SOURCE':'dataset','SOURCE_SPLIT':'split'}[cell[0]]])==cell[1]]
            coverage.append(dict(model_id=m,dimension=cell[0],stratum=cell[1],planned=len(expectations),returned=len(rs),worlds=len({r['world_cluster_id'] for r in rs}),status='COMPLETE' if len(expectations)==len(rs) else 'PARTIAL_NOT_FULL_ACCURACY'))
            endpoints={}
            for metric in ('ClaimAcc','BinaryClaimAcc','ContradictoryRecall','UnknownRecall','WorldMacroAcc','PairAcc'):
                selected=rs if metric in ('ClaimAcc','WorldMacroAcc','PairAcc') else [r for r in rs if r['component']=='binary'] if metric=='BinaryClaimAcc' else [r for r in rs if r['gold']==('CONTRADICTORY' if metric=='ContradictoryRecall' else 'UNKNOWN')]
                byworld=defaultdict(list)
                if metric=='PairAcc':
                    pairs=defaultdict(list)
                    for r in selected:
                        if r['component']=='binary': pairs[r['pair_id']].append(r)
                    for prs in pairs.values():
                        if len({r['world_cluster_id'] for r in prs}) != 1: raise ValueError('PAIR_CROSSES_WORLD_ID')
                        if len(prs)==2 and {r['gold'] for r in prs}=={'SUPPORTED','CONTRADICTORY'}: byworld[prs[0]['world_cluster_id']].append(int(all(r['correct'] for r in prs)))
                else:
                    for r in selected: byworld[r['world_cluster_id']].append(int(r['correct']))
                values=[(w,sum(v)/len(v),1) if metric=='WorldMacroAcc' else (w,sum(v),len(v)) for w,v in sorted(byworld.items())]
                num=sum(v[1] for v in values); den=sum(v[2] for v in values); lo,hi=interval(values,c['seed'],5000)
                statistics.append(dict(hypothesis_id='E0_DESCRIPTIVE_NO_HYPOTHESIS_SELECTION',experiment='E0',model_id=m,source_type='EXISTING_FROZEN_BASELINE',split='SOURCE_SPLITS_AS_RECORDED',
                    dimension=cell[0],stratum=cell[1],metric=metric,numerator=num,denominator=den,worlds=len(values),estimate=num/den if den else None,
                    ci95_low=lo,ci95_high=hi,p_adjustment='NOT_CONFIRMATORY',interpretation_limit='IN_PROGRESS_AVAILABLE_RESPONSE_SNAPSHOT; MISSING_NOT_SCORED_AS_WRONG; NOT_FINAL_BENCHMARK'))
    # Three models compared only on the same returned sample IDs, never unmatched counts.
    common=set.intersection(*(set(x) for x in modelrows.values())); transitions=Counter()
    for sid in common:
        key=tuple(int(modelrows[m][sid]['correct']) for m in c['models']); level=gold[sid]['level']; transitions[(level,key)]+=1
    csvsave(root/'tables/E0_primary_statistics_snapshot.csv',statistics)
    csvsave(root/'tables/E0_prediction_coverage_snapshot.csv',coverage)
    csvsave(root/'tables/E0_common_scale_patterns.csv',[dict(level=l,models=c['models'],correctness_pattern=pat,claims=n,common_response_subset=True) for (l,pat),n in sorted(transitions.items())])
    save(root/'scores/E0_existing_snapshot.jsonl',allscored,'jsonl'); save(root/'manifest/E0_raw_index.jsonl',index,'jsonl')
    save(root/'reports/E0_snapshot_acceptance.json',dict(status='PARTIAL_EXISTING_BASELINE_ANALYZED_NOT_NEW_SWS_INFERENCE',created_at=now(),job_id=os.environ['SLURM_JOB_ID'],
        identity_acceptance=entry(identity_root/'identity_acceptance.json'),recovered_world_id_records=identity['recovered_records'],
        snapshot_lock=entry(root/'raw/E0_existing_snapshot/SNAPSHOT_LOCK.json'),
        original_run=str(base),original_gold=entry(base/'private_gold.jsonl'),original_requests=entry(base/'requests.jsonl'),
        parser_files=[entry(old/'common.py'),entry(old/'output_policy.py')],snapshots=files,common_returned_claims=len(common),
        existing_test_evaluation_authority='USER_PRIOR_FULL_BENCHMARK_REQUEST; NO_NEW_TEST_CALLS',
        new_model_calls=0,source_world_selection_dependency=False,read_only_old_results=True,
        missing_not_treated_as_model_errors_in_partial_snapshot=True,bootstrap_repetitions=5000))
    print(json.dumps(dict(status='E0_SNAPSHOT_ANALYZED',planned_per_model=len(requests),returned_by_model={k:len(v) for k,v in modelrows.items()},common_returned_claims=len(common))),flush=True)

if __name__=='__main__': main()

