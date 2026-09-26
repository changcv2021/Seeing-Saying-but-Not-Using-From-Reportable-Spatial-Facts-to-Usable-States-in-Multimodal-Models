"""Non-count E2/E6 matrix; don't interpret the E8-only matrix as run completion."""
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from common_auto_v2 import *
BATCH='noncount_breadth_v1_20260910'

def main():
    p=arguments(__doc__);p.add_argument('--model',required=True);p.add_argument('--score-job',required=True);a=p.parse_args();c,root=setup(a)
    if a.model not in c['models'] or not a.score_job.isdigit():raise ValueError('INVALID_SCORE_REFERENCE')
    source=root/'rescoring/breadth_interface_v2'/BATCH/BATCH/a.model/('snapshot_'+a.score_job)/'normalized'
    if a.dry_run:print(str(source));return
    out=root/'analysis/noncount_breadth_v2'/a.model/('snapshot_'+os.environ['SLURM_JOB_ID'])
    req=defaultdict(list);matches=defaultdict(list)
    with (source/'all_physical_request_scores.csv').open() as f:
        for r in csv.DictReader(f):req[r['world_cluster_id']].append(r)
    for m in rows(source/'matched_results.jsonl'):matches[m['world_cluster_id']].append(m)
    matrix=[]
    for panel in rows(root/'batches'/BATCH/'private_gold/world_panel.jsonl'):
        w=panel['world_cluster_id'];rr=req[w];mm=matches[w];returned=[r for r in rr if r['execution_status']=='RETURNED']
        complete=[m for m in mm if m['status']=='COMPLETE'];flags=[]
        e2=[m for m in complete if m['experiment']=='E2'];e6=[m for m in complete if m['experiment']=='E6']
        if any(m.get('correct_to_wrong_excess',0)>0 for m in e2):flags.append('CLAIM_MINUS_SHAM_BEHAVIORAL_SHIFT')
        if any(v.get('fact_correct_verdict_wrong') for m in e6 for v in m.get('joint_diagnostics',{}).values()):flags.append('SAME_RUN_FACT_CORRECT_VERDICT_WRONG')
        invalid=[r['request_id'] for r in returned if r['schema_status']=='INVALID']
        if invalid:flags.append('ANSWER_INTERFACE_REMAINS')
        matrix.append(dict(model_id=a.model,world_cluster_id=w,source_level=panel['source_level'],primary_stratum=panel['primary_stratum'],
            status='RETURNED' if rr and len(returned)==len(rr) else 'PARTIAL_OR_NOT_RUN',planned=len(rr),returned=len(returned),
            correct=sum(r['content_correct']=='True' for r in returned),invalid_request_ids=invalid,matched_blocks_planned=len(mm),matched_blocks_complete=len(complete),
            functional_flags=flags,e2_matched_results=e2,e6_matched_results=e6,
            request_ids=[r['request_id'] for r in rr],source_bundle=panel['bundle'],binary_nonidentifying=True,
            interpretation='NONEXCLUSIVE_BEHAVIORAL_BOUNDARIES_NOT_WRONG_STATE_SELECTION_PROOF',review_grade='AUTO_ONLY_PROVISIONAL'))
    csvsave(out/'world_failure_matrix.csv',matrix)
    save(out/'ANALYSIS_ACCEPTANCE.json',dict(status='COMPLETE_FOR_RETURNED_DATA',model=a.model,worlds=len(matrix),
        code=entry(__file__),matrix=entry(out/'world_failure_matrix.csv'),source_scores=entry(source/'all_physical_request_scores.csv'),
        source_matched=entry(source/'matched_results.jsonl'),source_statistics=entry(source/'primary_statistics.csv'),
        original_e8_only_matrix_is_not_a_noncount_completion_measure=True,no_rescoring_or_prediction_mutation=True,
        full_study_complete=False))

if __name__=='__main__':main()
