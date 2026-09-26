"""Small atomic reporting snapshot; no inference, selection, or ranking by validity."""
import csv,fcntl,json,os
from campaign import ROOT,registry,args,write

def main():
    a=args()
    if a.dry_run:print('Read each model score; report missing or blocked explicitly.');return
    if not os.environ.get('SLURM_JOB_ID'):raise ValueError('SLURM_REQUIRED')
    with (ROOT/'summary.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        rows=[]
        for key,m in registry().items():
            score=ROOT/key/'full_score.json';value=json.loads(score.read_text()) if score.exists() else {}
            for scope in ['overall','test_only']:
                metric=value.get(scope,{})
                rows.append(dict(model=m['model_id'],scope=scope,status=value.get('status','BLOCKED' if not m['enabled'] else 'NOT_COMPLETE'),
                    n=metric.get('n'),claim_accuracy=metric.get('claim_accuracy'),balanced_accuracy=metric.get('balanced_accuracy'),
                    macro_f1=metric.get('macro_f1'),pair_accuracy=metric.get('pair_accuracy'),unknown_f1=metric.get('unknown_f1'),
                    explanation_rubric_score=value.get('explanation_rubric_score' if scope=='overall' else 'test_explanation_rubric_score'),
                    report=str(score),blocked_reason=m.get('blocked_reason') if not m['enabled'] else None))
        temp=ROOT/'model_comparison.csv.part'
        with temp.open('w') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        os.replace(temp,ROOT/'model_comparison.csv')
        write(ROOT/'model_comparison.json',dict(rows=rows,protocol='ordered_frames_bare_json_512_v1',
            overall_is_all_split_diagnostic=True,test_is_reported_separately=True,max_new_tokens=512,
            old_protocol_scores_not_mixed=True,judge_is_auxiliary_same_family_bias_disclosed=True))

if __name__=='__main__':main()
