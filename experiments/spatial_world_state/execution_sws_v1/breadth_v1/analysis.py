"""Per-world functional diagnostics; never infer hidden mechanisms from accuracy gaps."""
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from common_auto_v2 import *

def analyze(c,root,batch,model,snapshot):
    folder=root/'batches'/batch;out=snapshot/'functional_diagnostics'
    with (snapshot/'normalized/all_physical_request_scores.csv').open() as f:rr={r['request_id']:r for r in csv.DictReader(f)}
    matched=list(rows(folder/'private_gold/matched_structure.jsonl'));gaps=list(rows(folder/'reports/NOT_DIAGNOSABLE.jsonl'))
    panels=list(rows(folder/'private_gold/world_panel.jsonl'));matrix=[]
    def success(rid):
        r=rr.get(rid,{})
        if r.get('execution_status')!='RETURNED':return None
        return r.get('content_correct')=='True'
    for panel in panels:
        w=panel['world_cluster_id'];level=panel.get('source_level');mm=[m for m in matched if m['world_cluster_id']==w and m['experiment']=='E8' and m.get('level')==level]
        refs={k:v for m in mm for k,v in m.items() if isinstance(v,str) and v in rr}
        correct={k:success(rid) for k,rid in refs.items()};allreturned=bool(refs) and all(v is not None for v in correct.values())
        flags=[]
        if correct.get('PRE_VALUE') is False:flags.append('PRE_REPORT_FAILURE')
        if correct.get('ACTION_PARSE') is False:flags.append('ACTION_PARSE_FAILURE')
        if correct.get('POST_VALUE') is False:flags.append('POST_REPORT_FAILURE')
        if correct.get('PRE_VALUE') is True and correct.get('ACTION_PARSE') is True and correct.get('POST_VALUE') is False:flags.append('PRE_ACTION_CORRECT_POST_WRONG_FUNCTIONAL_BOUNDARY')
        prerequisites=[correct[k] for k in ('PREMISE_1','PREMISE_2') if k in correct]
        allpre=all(prerequisites) if len(prerequisites)==2 and all(x is not None for x in prerequisites) else None
        if allpre and correct.get('CONCLUSION') is False:flags.append('ALL_PREMISES_CORRECT_CONCLUSION_WRONG')
        neutral=correct.get('FACT_VALUE',correct.get('CONCLUSION',correct.get('POST_VALUE')))
        if neutral is True and any(correct.get(k) is False for k in ('SUPPORTED','CONTRADICTORY')):flags.append('SEPARATE_REQUEST_FACT_CORRECT_VERDICT_WRONG')
        invalid=[k for k,rid in refs.items() if rr[rid]['schema_status']=='INVALID']
        if invalid:flags.append('ANSWER_INTERFACE_REMAINS')
        localgaps=[g for g in gaps if g['world_cluster_id']==w and g['level']==level]
        matrix.append(dict(model_id=model,world_cluster_id=w,source_level=level,batch=batch,status='RETURNED' if allreturned else 'PARTIAL_OR_NOT_RUN',
            correctness=correct,all_prerequisites_correct=allpre,interface_invalid_conditions=invalid,functional_flags=flags,
            missing_diagnostics=localgaps,request_refs=refs,source_bundle=panel.get('bundle'),
            interpretation='NONEXCLUSIVE_FUNCTIONAL_BOUNDARIES_NOT_HIDDEN_CAUSAL_MECHANISMS',review_grade='AUTO_ONLY_PROVISIONAL'))
    csvsave(out/'world_failure_matrix.csv',matrix)
    save(out/'ANALYSIS_ACCEPTANCE.json',dict(status='COMPLETE_FOR_RETURNED_DATA',model=model,batch=batch,world_level_rows=len(matrix),
        source_scores=entry(snapshot/'normalized/all_physical_request_scores.csv'),matrix=entry(out/'world_failure_matrix.csv'),
        missing_diagnostics_retained=True,independent_worlds=len({r['world_cluster_id'] for r in matrix}),
        overall_study_complete=False,interpretation='DESCRIPTIVE_DISCOVERY_NOT_CONFIRMATORY'))
