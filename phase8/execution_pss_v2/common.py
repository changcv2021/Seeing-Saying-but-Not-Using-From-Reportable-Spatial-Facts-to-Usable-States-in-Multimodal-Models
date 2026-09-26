import argparse, hashlib, json, os
from pathlib import Path

SPACE=Path('.')
REPO=SPACE/'SpaceConflict'
BASE=Path('artifacts/model_results')
OLD=BASE/'pss_20260922_v1'
ROOT=OLD/'approved_v2'
FROZEN=BASE/'full_multimodel_20260908_v1'
MODEL=Path('models/Qwen3.5-9B')
PYTHON='python'
SEEDS=[20260922,20260923]

def rows(path):
    with Path(path).open() as f:
        for line in f:
            if line.strip(): yield json.loads(line)

def read(path): return json.loads(Path(path).read_text())
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()
def digest(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def write(path,obj,jsonl=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:
        if jsonl:
            for r in obj: f.write(json.dumps(r,sort_keys=True,ensure_ascii=False)+'\n')
        else: json.dump(obj,f,indent=2,sort_keys=True,ensure_ascii=False);f.write('\n')
def atomic(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(obj,indent=2,ensure_ascii=False,sort_keys=True)+'\n');os.replace(temp,path)
def cli(doc):
    p=argparse.ArgumentParser(doc);p.add_argument('--run-root',type=Path,default=ROOT)
    p.add_argument('--run-id',default='pss_20260922_approved_v2');p.add_argument('--seed',type=int,default=SEEDS[0])
    p.add_argument('--limit',type=int);p.add_argument('--resume',action='store_true');p.add_argument('--dry-run',action='store_true')
    return p
def compute():
    if not os.environ.get('SLURM_JOB_ID'): raise RuntimeError('SLURM_REQUIRED')

