"""SWS isolated, append-safe IO. No implicit historical writes or GPU submission."""
import argparse
import csv
import hashlib
import io
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

CODE = Path(__file__).resolve().parent

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def entry(path):
    p=Path(path)
    return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))

def load(path):
    return json.loads(Path(path).read_text())

def rows(path):
    with Path(path).open() as f:
        for n,line in enumerate(f,1):
            if not line.strip(): continue
            try: yield json.loads(line)
            except Exception as exc: raise ValueError(f'INVALID_SOURCE_JSON:{path}:{n}') from exc

def now(): return datetime.now(timezone.utc).isoformat()

def save(path,value,kind='json'):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    if kind=='json': data=json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+'\n'
    elif kind=='jsonl': data=''.join(json.dumps(r,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n' for r in value)
    else: data=value
    if p.exists():
        if p.read_text()!=data: raise ValueError('FROZEN_OUTPUT_DIFFERS:'+str(p))
        return
    temporary=p.with_name(p.name+f'.{os.getpid()}.tmp')
    with temporary.open('x') as f: f.write(data)
    # link provides no-overwrite publication even with a second writer.
    os.link(temporary,p); temporary.unlink()

def csvsave(path,values,fields=None):
    values=list(values); fields=fields or list(dict.fromkeys(k for r in values for k in r)) or ['status']
    out=io.StringIO(newline=''); w=csv.DictWriter(out,fieldnames=fields,lineterminator='\n'); w.writeheader()
    for r in values: w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})
    save(path,out.getvalue(),'text')

def cluster(w):
    if w.startswith('hypo3d:'):
        s=w.split(':',1)[1]
        if s.startswith('scene'): return 'scannet:'+s
        if len(s)==36 and s.count('-')==4: return '3rscan:'+s
    return w

def arguments(description):
    p=argparse.ArgumentParser(description=description)
    p.add_argument('--config',type=Path,default=CODE/'config.json')
    p.add_argument('--run-id',default='sws_20260909_v1'); p.add_argument('--seed',type=int,default=20260909)
    p.add_argument('--dry-run',action='store_true'); p.add_argument('--resume',action='store_true'); p.add_argument('--limit',type=int)
    return p

def setup(a):
    c=load(a.config); root=Path(c['root'])
    if (a.run_id,a.seed)!=(c['run_id'],c['seed']) or a.limit is not None: raise ValueError('FROZEN_RUN_SEED_SCOPE_MISMATCH')
    if root.parent.name!='spatial_world_state' or root.name!=c['run_id']: raise ValueError('NEW_NAMESPACE_REQUIRED')
    if not a.dry_run and (not os.environ.get('SLURM_JOB_ID') or socket.gethostname().startswith('login')): raise ValueError('COMPUTE_ALLOCATION_REQUIRED')
    return c,root
