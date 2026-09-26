"""Recompute 13 historical evaluations from separately supplied original predictions."""
import argparse
import json
from pathlib import Path
from score import ROOT, score

def reproduce(predictions_dir):
    source = json.loads((ROOT / 'results/sft/summary_v3.json').read_text())
    gold = ROOT / 'artifacts/model_results/pss_20260922_v1/approved_v2/data/test/private_gold.jsonl'
    predictions_dir = Path(predictions_dir)
    missing = [key + '.jsonl' for key in source['models']
               if not (predictions_dir / (key + '.jsonl')).is_file()]
    if missing:
        raise FileNotFoundError('Original predictions must be supplied separately: ' + ', '.join(missing))
    runs = {}
    for key, historical in source['models'].items():
        measured = score(gold, predictions_dir / (key + '.jsonl'))
        for level, values in measured['by_level'].items():
            expected = historical['by_level'][level]['v3']
            for metric in ('n','complete_pairs','claim_accuracy','pair_accuracy','macro_f1','unknown_f1'):
                a,b = values[metric], expected[metric]
                if a is None or b is None:
                    if a != b: raise ValueError('NULL_METRIC_CHANGED')
                elif abs(a-b)>1e-12: raise ValueError('RESULT_MISMATCH:' + key + ':' + level + ':' + metric)
            if values['per_label'] != expected['per_label']: raise ValueError('LABEL_COUNTS_CHANGED:' + key)
        runs[key] = measured
    return dict(status='PASS_EXACT_METRIC_REPRODUCTION', models=len(runs), inputs_per_model=5608,
                parser='observed_first_label_v3', runs=runs)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--predictions-dir', type=Path, required=True,
                        help='Directory containing the original 13 JSONL runs; not bundled')
    parser.add_argument('--output', type=Path, default=ROOT / 'reproduced_sft_metrics.json',
                        help='New output file; the delivered verification report is never overwritten')
    args = parser.parse_args()
    result = reproduce(args.predictions_dir)
    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x') as f: json.dump(result, f, indent=2)
    print(json.dumps(dict(status=result['status'], models=result['models'], inputs_per_model=5608)))
