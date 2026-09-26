"""Matched E1 differences, retaining null, invalid, missing and secondary scope."""
import json
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from common_auto_v2 import *
from e0_snapshot import interval

def analyze(c,root,batch,model,snapshot):
    folder=root/'batches'/batch;out=snapshot/'multiview_diagnostics'
    with (snapshot/'normalized/all_physical_request_scores.csv').open() as f:rr={r['request_id']:r for r in csv.DictReader(f)}
    matrix=[];events=defaultdict(list)
    def returned(rid):return rr.get(rid,{}).get('execution_status')=='RETURNED'
    def correct(rid):return rr[rid]['content_correct']=='True' if returned(rid) else None
    def value(rid):return json.loads(rr[rid]['component_values']).get('value') if returned(rid) else None
    for m in rows(folder/'private_gold/matched_structure.jsonl'):
        refs={k:v for k,v in m.items() if isinstance(v,str) and v in rr};w=m['world_cluster_id']
        ok={k:correct(v) for k,v in refs.items()};facts=[correct(rid) for rid in m['local_fact_requests']]
        localall=all(facts) if facts and all(v is not None for v in facts) else None
        transforms={}
        for variant in ('REVERSED','ROTATED','REDUNDANT'):
            a,b=refs.get('FULL'),refs.get(variant)
            if a and b and returned(a) and returned(b):
                # Null/invalid cannot qualify semantic preservation.
                av,bv=value(a),value(b);valid=rr[a]['schema_status']=='VALID' and rr[b]['schema_status']=='VALID' and av is not None and bv is not None
                transforms[variant]=dict(full_correct=correct(a),variant_correct=correct(b),both_valid_nonnull=valid,
                    same_value=(type(av) is type(bv) and av==bv) if valid else None,
                    correct_to_wrong=bool(correct(a) and not correct(b)))
                events[variant+'_CORRECT_TO_WRONG'].append((w,int(correct(a) and not correct(b)),1))
        matrix.append(dict(world_cluster_id=w,model_id=model,source_level='L3',status='RETURNED' if all(returned(rid) for rid in refs.values()) else 'PARTIAL',
            correctness=ok,all_source_local_axes_correct=localall,joint_correct=ok.get('JOINT'),matched_transforms=transforms,
            source_local_axis_count=m['source_local_axis_count'],protected_unrelated_fact_available=False,
            main_fusion_eligible=False,reference_ablation_scope='SECONDARY_SOURCE_REFERENCE_LOSS',
            request_refs=refs,local_fact_refs=m['local_fact_requests'],review_grade='AUTO_ONLY_PROVISIONAL'))
    stats=[]
    for metric,rs in events.items():
        lo,hi=interval(rs,c['seed'],5000)
        stats.append(dict(model_id=model,metric=metric,worlds=len(rs),estimate=sum(r[1] for r in rs)/len(rs),ci95_low=lo,ci95_high=hi,
            scope='DISCOVERY_FULL_EVIDENCE_TRANSFORMS_NOT_FUSION_CAUSALITY'))
    csvsave(out/'world_diagnostics.csv',matrix);csvsave(out/'matched_transform_statistics.csv',stats)
    save(out/'ANALYSIS_ACCEPTANCE.json',dict(status='COMPLETE_FOR_RETURNED_DATA',worlds=len(matrix),model=model,
        matrix=entry(out/'world_diagnostics.csv'),statistics=entry(out/'matched_transform_statistics.csv'),
        overall_study_complete=False,fully_certified_pixel_multiview_worlds=0))
