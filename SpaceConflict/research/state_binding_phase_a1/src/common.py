"""A1 IO only. Never imports old scorers or opens old gold at import time."""
import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

def load(path):
    with Path(path).open() as f: return json.load(f)

def rows(path):
    with Path(path).open() as f:
        for line in f:
            if line.strip(): yield json.loads(line)

def save(path, obj, kind='json', frozen=False):
    path = Path(path)
    if kind == 'jsonl': text = ''.join(json.dumps(x, ensure_ascii=False, sort_keys=True)+'\n' for x in obj)
    elif kind == 'text': text = obj
    else: text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)+'\n'
    if frozen and path.exists():
        if path.read_text() != text: raise ValueError('FROZEN_FILE_CHANGED:'+str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.part')
    tmp.write_text(text); tmp.replace(path)

def csvsave(path, data, fields=None):
    data=list(data); path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w', newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(data[0])); w.writeheader()
        for row in data:
            w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})

def arguments(description):
    p=argparse.ArgumentParser(description=description)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--run-id',required=True)
    p.add_argument('--seed',type=int,required=True)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--limit',type=int)
    return p

def setup(a):
    cfg=load(a.config)
    if (cfg['run_id'],cfg['seed']) != (a.run_id,a.seed): raise ValueError('RUN_SEED_MISMATCH')
    if a.limit is not None: raise ValueError('NO_POSTHOC_LIMIT_USE_FROZEN_PANEL')
    root=Path(cfg['root'])
    if root==Path(cfg['phase_a_root']) or CODE==Path(cfg['phase_a_code']): raise ValueError('A1_NAMESPACE_REQUIRED')
    return cfg,root

def require_compute():
    if not os.environ.get('SLURM_JOB_ID'): raise RuntimeError('SLURM_COMPUTE_ALLOCATION_REQUIRED')

def entry(path):
    path=Path(path)
    return dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path))
