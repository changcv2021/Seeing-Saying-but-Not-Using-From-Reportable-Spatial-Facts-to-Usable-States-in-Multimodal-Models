"""Score public predictions against separately supplied public gold. CPU only."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'evaluation/label_rescore_v3'))
from policy_v3 import parse_observed
from common import metrics

def load(path):
    out = {}
    with Path(path).open() as f:
        for line in f:
            if not line.strip(): continue
            r = json.loads(line)
            if r['sample_id'] in out: raise ValueError('DUPLICATE_SAMPLE_ID')
            out[r['sample_id']] = r
    return out

def score(gold_path, predictions_path):
    gold, predictions = load(gold_path), load(predictions_path)
    if set(predictions) - set(gold): raise ValueError('EXTRA_PREDICTION_IDS')
    records = []
    for sid, g in gold.items():
        p = predictions.get(sid, {'raw_response': '', 'error': 'MISSING_PREDICTION'})
        # Parser is gold-blind; only the observed response fields are passed in.
        evidence = {k: p[k] for k in ('raw_response','finish_reason','generated_tokens','error') if k in p}
        parsed = parse_observed(evidence)
        records.append(dict(g, **{k: v for k, v in parsed.items() if k not in g}))
    result = {level: metrics(records if level == 'Overall' else [r for r in records if r['level'] == level])
              for level in ('L1','L2','L3','L4','Overall')}
    for value in result.values():
        labels = value.get('per_label', {})
        known = sum(labels.get(l, {}).get('support', 0) for l in ('SUPPORTED','CONTRADICTORY'))
        correct = sum(round(labels.get(l, {}).get('support', 0) * labels.get(l, {}).get('recall', 0)) for l in ('SUPPORTED','CONTRADICTORY'))
        value['known_accuracy'] = correct / known if known else None
        u = labels.get('UNKNOWN', {})
        value['unknown_recall'] = u.get('recall') if u.get('support') else None
    return dict(n_gold=len(gold), n_predictions=len(predictions), missing=len(gold)-len(predictions),
                label_policy='observed_first_label_v3', by_level=result)

def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--gold', type=Path, required=True)
    p.add_argument('--predictions', type=Path, required=True)
    p.add_argument('--output', type=Path)
    a = p.parse_args(); result = score(a.gold, a.predictions)
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        with a.output.open('x') as f: f.write(text)
    else: print(text, end='')

if __name__ == '__main__': main()
