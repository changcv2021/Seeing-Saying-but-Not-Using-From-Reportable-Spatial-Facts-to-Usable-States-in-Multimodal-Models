"""Validate IDs, public-input separation, and frozen world-disjoint SFT splits."""
import collections
import json
from pathlib import Path
from score import ROOT, load

DATA = ROOT / 'artifacts/model_results/pss_20260922_v1/approved_v2/data'
FORBIDDEN = {'gold', 'gold_label', 'label', 'reference_proposition', 'certificate', 'proof', 'answer'}

def forbidden_keys(obj):
    if isinstance(obj, dict):
        return (set(obj) & FORBIDDEN) | set().union(*(forbidden_keys(v) for v in obj.values()))
    if isinstance(obj, list): return set().union(*(forbidden_keys(v) for v in obj)) if obj else set()
    return set()

def validate():
    result = {}; worlds = {}; sample_sets = {}
    for split in ('train','dev','test'):
        requests, gold = load(DATA / split / 'requests.jsonl'), load(DATA / split / 'private_gold.jsonl')
        if set(requests) != set(gold): raise ValueError('REQUEST_GOLD_ID_MISMATCH:' + split)
        for sid, request in requests.items():
            if forbidden_keys(request): raise ValueError('GOLD_FIELD_IN_PUBLIC_REQUEST')
            if request['split'] != split or gold[sid]['split'] != split: raise ValueError('SPLIT_FIELD_MISMATCH')
        worlds[split] = {r['underlying_world_id'] for r in gold.values()}
        sample_sets[split] = set(gold)
        result[split] = dict(inputs=len(gold), worlds=len(worlds[split]),
            levels=dict(collections.Counter(r['level'] for r in gold.values())),
            labels=dict(collections.Counter(r['gold'] for r in gold.values())))
    for a,b in (('train','dev'),('train','test'),('dev','test')):
        if worlds[a] & worlds[b] or sample_sets[a] & sample_sets[b]: raise ValueError('SPLIT_LEAKAGE')
    if result['train']['inputs'] != 13476 or result['test']['inputs'] != 5608:
        raise ValueError('FROZEN_DENOMINATOR_CHANGED')
    full = ROOT / 'artifacts/model_results/full_multimodel_20260908_v1'
    req, gold = load(full / 'requests.jsonl'), load(full / 'private_gold.jsonl')
    if len(req) != 24196 or set(req) != set(gold): raise ValueError('FULL_RELEASE_MISMATCH')
    for r in req.values():
        if forbidden_keys(r): raise ValueError('GOLD_FIELD_IN_FULL_REQUEST')
    result['full_benchmark'] = dict(inputs=len(req))
    return dict(status='PASS', splits=result, world_disjoint=True, public_requests_gold_free=True,
                note='The historical alias-map audit is preserved separately; no new world grouping was inferred.')

if __name__ == '__main__': print(json.dumps(validate(), indent=2))
