"""Frozen world-paired supplemental contrasts; all responses and nulls retained."""
from collections import defaultdict
import csv
from pathlib import Path
from common_auto_v2 import *
from e0_snapshot import interval


def analyze(c,root,batch,model,dest):
    source=root/'batches'/batch
    if batch.startswith('e7_'):
        save(dest/'SUPPLEMENT_ANALYSIS_ACCEPTANCE.json',dict(status='SEE_RECOMPUTED_E7_MATCHED_STATISTICS',
            grouped=entry(dest/'normalized/grouped_statistics.csv'),new_prompt_version=True,
            old_E7_not_pooled=True,qualification='CONTROLLED_COUNT_PLUS_NATIVE_RELATION_NOT_NEW_NATIVE_L4'))
        return
    with (dest/'normalized/all_physical_request_scores.csv').open() as f:
        scores={r['request_id']:r for r in csv.DictReader(f)}
    matches=[];groups=defaultdict(list)
    for m in rows(source/'private_gold/matched_structure.jsonl'):
        keys=['TARGET','BASE','PROTECTED'] if m['experiment']=='E5_SUPPLEMENT' else ['short','long']
        rr=[scores[m[k]] for k in keys]
        complete=all(r['execution_status']=='RETURNED' for r in rr)
        got={k:scores[m[k]]['content_correct']=='True' for k in keys} if complete else None
        record=dict(m,model=model,status='COMPLETE' if complete else 'PARTIAL',correct=got,
                    raw_refs=[dict(request_id=r['request_id'],path=r.get('raw_path'),sha256=r.get('raw_sha256')) for r in rr])
        if complete:
            if m['experiment']=='E5_SUPPLEMENT':
                value=int(all(got.values()));key=('E5',m['condition'],'TARGET_BASE_PROTECTED_JOINT_ACCURACY')
            elif m['contrast']=='ROLE_SELECTIVE_JOINT':
                value=int(all(got.values()));key=('E9C',m['family'],m['contrast'])
            else:
                value=int(got['long'])-int(got['short']);key=('E9C',m['family'],m['contrast'],m['role'])
            record['metric_value']=value;groups[key].append((m['world_cluster_id'],value))
        matches.append(record)
    stats=[]
    for key,values in groups.items():
        ww=defaultdict(list)
        for w,v in values:ww[w].append(v)
        clustered=[(w,sum(v)/len(v),1) for w,v in ww.items()]
        lo,hi=interval(clustered,c['seed'],5000)
        stats.append(dict(group=list(key),model=model,estimate=sum(x[1] for x in clustered)/len(clustered),
                          ci95_low=lo,ci95_high=hi,worlds=len(ww),matched_blocks=len(values),
                          split='symbolic_control' if batch.startswith('e9c_') else 'discovery',
                          scientific_grade='AUTO_ONLY_PROVISIONAL',not_confirmatory=True))
    save(dest/'supplement_matched_results.jsonl',matches,'jsonl')
    csvsave(dest/'supplement_world_paired_statistics.csv',stats)
    save(dest/'SUPPLEMENT_ANALYSIS_ACCEPTANCE.json',dict(status='COMPLETE' if all(m['status']=='COMPLETE' for m in matches) else 'PARTIAL',
        matches=len(matches),groups=len(stats),model=model,batch=batch,raw_preserved=True,
        matched=entry(dest/'supplement_matched_results.jsonl'),statistics=entry(dest/'supplement_world_paired_statistics.csv'),
        substantive_errors_retained=True,claims='BOUNDED_BEHAVIORAL_DIAGNOSTICS_NOT_INTERNAL_CAUSAL_ATTRIBUTION'))
