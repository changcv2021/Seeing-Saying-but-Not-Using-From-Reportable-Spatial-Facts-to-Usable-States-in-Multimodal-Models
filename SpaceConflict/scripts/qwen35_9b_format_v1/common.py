"""Frozen full-release evaluation v1: exact metrics and auxiliary rubric protocol."""
import hashlib
import json
import math
import os
from collections import defaultdict
from pathlib import Path

LABELS = ('SUPPORTED', 'CONTRADICTORY', 'UNKNOWN')
MODEL_ID = 'Qwen/Qwen2.5-VL-7B-Instruct'
MODEL_REVISION = 'cc594898137f460bfe9f0759e9844b3ce807cfb5'
JUDGE_ID = 'Qwen/Qwen3.5-4B'
JUDGE_REVISION = '851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a'
RUBRIC = {
    'version': 'spaceconflict_explanation_rubric_v1',
    'scale': '0-100; mean of two equally weighted binary criteria',
    'scope': 'Auxiliary text explanation assessment, not independent visual grounding or proof verification.',
    'criteria': {
        'R1': 'The explanation itself clearly argues for the expected three-valued verdict. A bare label, hedging that reverses the verdict, or a generic instruction is insufficient.',
        'R2': 'The explanation gives a claim-specific spatial reason consistent with the reference proposition (for binary claims), or identifies a claim-specific evidence gap (for UNKNOWN). Merely repeating the verdict or discussing unrelated entities is insufficient.',
    },
    'required_evidence': 'For met=true quote a contiguous verbatim substring of candidate_reason, 2-160 non-whitespace characters. For false use an empty string.',
    'fallback': 'Up to three deterministic attempts; invalid judgments fail closed as met=false and are logged.',
    'gold_policy': 'Gold and references are judge-only, never sent to the evaluated VLM. UNKNOWN never receives the withheld reference proposition.',
}

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def load(path):
    with Path(path).open() as stream:
        return [json.loads(line) for line in stream if line.strip()]

def unique(rows, key='sample_id'):
    result = {}
    for row in rows:
        if row[key] in result:
            raise ValueError(f'DUPLICATE_ID:{row[key]}')
        result[row[key]] = row
    return result

def write(path, obj, jsonl=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.part')
    with tmp.open('w') as stream:
        if jsonl:
            for row in obj:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
        else:
            json.dump(obj, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write('\n')
    os.replace(tmp, path)

def parse(raw):
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def bad_constant(value):
        raise ValueError('NONFINITE_JSON_NUMBER')
    try:
        obj = json.loads(raw, object_pairs_hook=no_duplicates, parse_constant=bad_constant)
        if not isinstance(obj, dict):
            raise ValueError('JSON_NOT_OBJECT')
    except (ValueError, TypeError):
        return dict(label=None, reason=None, confidence=None, strict_json_valid=False, schema_valid=False)
    label = obj.get('label') if obj.get('label') in LABELS else None
    confidence = obj.get('confidence')
    confidence_ok = type(confidence) in (int, float) and math.isfinite(confidence) and 0 <= confidence <= 1
    reason = obj.get('reason')
    return dict(label=label, reason=reason if isinstance(reason, str) else None,
                confidence=confidence if confidence_ok else None, strict_json_valid=True,
                schema_valid=label is not None and confidence_ok and isinstance(reason, str)
                and bool(reason.strip()) and set(obj) == {'label', 'reason', 'confidence'})

def metrics(rows):
    n = len(rows)
    if not n:
        return dict(n=0, claim_accuracy=None, balanced_accuracy=None, macro_f1=None,
                    pair_accuracy=None, unknown_f1=None, complete_pairs=0)
    per_label = {}
    for label in LABELS:
        tp = sum(r['gold'] == label and r['label'] == label for r in rows)
        fp = sum(r['gold'] != label and r['label'] == label for r in rows)
        fn = sum(r['gold'] == label and r['label'] != label for r in rows)
        support = tp + fn
        per_label[label] = dict(support=support, precision=tp/(tp+fp) if tp+fp else 0,
                               recall=tp/support if support else 0, f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0)
    supported = [r for r in per_label.values() if r['support']]
    pairs = defaultdict(list)
    for row in rows:
        if row['component'] == 'binary':
            pairs[row['pair_id']].append(row)
    complete = [p for p in pairs.values() if len(p) == 2 and {r['gold'] for r in p} == set(LABELS[:2])]
    return dict(n=n, claim_accuracy=sum(r['gold'] == r['label'] for r in rows)/n,
                balanced_accuracy=sum(r['recall'] for r in supported)/len(supported),
                macro_f1=sum(r['f1'] for r in supported)/len(supported),
                pair_accuracy=sum(all(r['gold'] == r['label'] for r in p) for p in complete)/len(complete) if complete else None,
                complete_pairs=len(complete), unknown_f1=per_label['UNKNOWN']['f1'] if per_label['UNKNOWN']['support'] else None,
                per_label=per_label)

def judgment_valid(obj, criterion, reason):
    if not isinstance(obj, dict) or set(obj) != {'criterion_id', 'met', 'evidence'}:
        return False
    if obj['criterion_id'] != criterion or type(obj['met']) is not bool or not isinstance(obj['evidence'], str):
        return False
    evidence = obj['evidence']
    return (evidence in reason and 2 <= len(''.join(evidence.split())) <= 160) if obj['met'] else evidence == ''
