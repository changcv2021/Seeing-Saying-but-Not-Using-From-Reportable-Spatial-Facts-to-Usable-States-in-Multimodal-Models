"""Small shared contracts. No model or private data loaded at import time."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

LABELS = ('SUPPORTED', 'CONTRADICTORY', 'UNKNOWN')
OUTCOMES = LABELS + ('INVALID',)

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()

def load(path):
    with Path(path).open() as f: return json.load(f)

def rows(path):
    with Path(path).open() as f:
        for line in f:
            if line.strip(): yield json.loads(line)

def unique(items, key):
    result = {}
    for row in items:
        if row[key] in result: raise ValueError('DUPLICATE_ID:' + str(row[key]))
        result[row[key]] = row
    return result

def write(path, obj, kind='json'):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.part')
    with tmp.open('w') as f:
        if kind == 'text': f.write(obj)
        elif kind == 'jsonl':
            for item in obj: f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + '\n')
        else: json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=2); f.write('\n')
    os.replace(tmp, path)

def csvwrite(path, data, fields=None):
    data = list(data); path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(data[0]) if data else ['status'])
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(data)

def args(description):
    p = argparse.ArgumentParser(description=description)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--limit', type=int)
    return p

def setup(a):
    cfg = load(a.config)
    if (cfg['run_id'], cfg['seed']) != (a.run_id, a.seed): raise ValueError('RUN_ID_SEED_MISMATCH')
    return cfg, Path(cfg['root']), Path(cfg['project'])

def reject_dupes(pairs):
    result = {}
    for k, v in pairs:
        if k in result: raise ValueError('DUPLICATE_JSON_FIELD')
        result[k] = v
    return result

def clean_json(raw, truncated=False):
    import re
    value = raw.strip()
    m = re.fullmatch(r'```(?:json)?\s*\n([\s\S]*?)\n```\s*', value, re.I)
    if m: value = m.group(1).strip()
    elif truncated:
        value = re.sub(r'^```(?:json)?[ \t]*\n', '', value, flags=re.I)
    return value

def parse_label(raw, truncated=False, mapping=None, field='label'):
    """Only a top-level explicit field, never a label mentioned in an explanation."""
    value = clean_json(raw, truncated)
    try:
        obj = json.loads(value, object_pairs_hook=reject_dupes)
        if not isinstance(obj, dict): return 'INVALID'
        lab = obj.get(field)
        if mapping is not None: return mapping.get(lab, 'INVALID')
        return lab if lab in LABELS else 'INVALID'
    except (ValueError, TypeError):
        if not truncated: return 'INVALID'
    # Walk emitted top-level key/value pairs; do not find label with a regex.
    decoder = json.JSONDecoder(object_pairs_hook=reject_dupes)
    if not value.startswith('{'): return 'INVALID'
    i = 1; observed = {}
    try:
        while i < len(value):
            while i < len(value) and value[i].isspace(): i += 1
            if i == len(value): break
            key, end = decoder.raw_decode(value, i)
            if not isinstance(key, str) or key in observed: return 'INVALID'
            i = end
            while i < len(value) and value[i].isspace(): i += 1
            if i == len(value): break
            if value[i] != ':': return 'INVALID'
            i += 1
            while i < len(value) and value[i].isspace(): i += 1
            try: val, end = decoder.raw_decode(value, i)
            except ValueError: break
            observed[key] = val; i = end
            while i < len(value) and value[i].isspace(): i += 1
            if i == len(value): break
            if value[i] == '}':
                if value[i+1:].strip(): return 'INVALID'
                break
            if value[i] != ',': return 'INVALID'
            i += 1
    except (ValueError, TypeError): pass
    lab = observed.get(field)
    if mapping is not None: return mapping.get(lab, 'INVALID')
    return lab if lab in LABELS else 'INVALID'

def pair_metrics(records):
    """Records already include missing/failed predictions as INVALID."""
    unique(records, 'sample_id')
    from collections import defaultdict
    pairs = defaultdict(list)
    for r in records:
        if r['gold'] in LABELS[:2]: pairs[r['pair_id']].append(r)
    for pid, pp in pairs.items():
        if len(pp) != 2 or {r['gold'] for r in pp} != set(LABELS[:2]): raise ValueError('INCOMPLETE_PAIR:' + pid)
    n = len(records); n_pair = len(pairs)
    acc = sum(r['gold'] == r['pred'] for r in records)/n if n else None
    recalls = {k: sum(r['gold'] == k and r['pred'] == k for r in records)/sum(r['gold'] == k for r in records) if any(r['gold'] == k for r in records) else None for k in LABELS}
    pa = sum(all(r['gold'] == r['pred'] for r in pp) for pp in pairs.values())/n_pair if n_pair else None
    if pa is not None and pa > min(recalls[k] for k in LABELS[:2]) + 1e-12: raise ValueError('PAIR_BOUND_VIOLATION')
    return dict(n=n, pairs=n_pair, claim_accuracy=acc, pair_accuracy=pa, recalls=recalls,
                binary_claim_accuracy=sum(r['gold'] == r['pred'] for r in records if r['gold'] in LABELS[:2])/(2*n_pair) if n_pair else None,
                valid_output_rate=sum(r['pred'] != 'INVALID' for r in records)/n if n else None)

def all_premises(values):
    return all(values) if values else None
