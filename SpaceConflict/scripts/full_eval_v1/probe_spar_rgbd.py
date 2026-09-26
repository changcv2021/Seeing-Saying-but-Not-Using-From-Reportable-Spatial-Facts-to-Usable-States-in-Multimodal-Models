"""Bounded official RGBD archive probe; not a complete dataset download."""
import argparse
import collections
import hashlib
import json
import tarfile
from pathlib import Path
import requests
from common import write

p=argparse.ArgumentParser()
p.add_argument('--output',type=Path,required=True)
p.add_argument('--run-id',required=True)
p.add_argument('--seed',type=int,default=20260905)
p.add_argument('--limit',type=int,default=1024*1024*1024)
p.add_argument('--dry-run',action='store_true')
p.add_argument('--resume',action='store_true')
a=p.parse_args()
revision='60ef8b2df6430524da86757dec86dcbc55708a41'
url=f'https://huggingface.co/datasets/jasonzhango/SPAR-7M-RGBD/resolve/{revision}/spar-rgbd-00.tar.gz'
if a.dry_run:
    print(json.dumps(dict(url=url,maximum_transfer_bytes=a.limit)))
    raise SystemExit()
a.output.mkdir(parents=True,exist_ok=True)
prefix=a.output/'spar-rgbd-00.prefix'
report=dict(run_id=a.run_id,seed=a.seed,source_revision=revision,url=url,limit=a.limit)
try:
    response=requests.get(url,headers={'Range':f'bytes=0-{a.limit-1}'},stream=True,timeout=(20,60))
    report['http_status']=response.status_code
    report['retry_after']=response.headers.get('Retry-After')
    response.raise_for_status()
    if response.status_code!=206 or not response.headers.get('Content-Range','').startswith(f'bytes 0-{a.limit-1}/'):
        response.close()
        raise ValueError('SERVER_DID_NOT_HONOR_BOUNDED_RANGE')
    digest=hashlib.sha256(); size=0
    with prefix.open('wb') as f:
        for data in response.iter_content(1024*1024):
            size+=len(data)
            if size>a.limit: raise ValueError('TRANSFER_LIMIT_EXCEEDED')
            f.write(data); digest.update(data)
    response.close()
    if size!=a.limit: raise ValueError('TRUNCATED_RANGE_RESPONSE')
    report.update(prefix_bytes=size,prefix_sha256=digest.hexdigest())
    counts=collections.Counter(); examples=collections.defaultdict(list)
    try:
        with tarfile.open(prefix,'r|gz') as t:
            for m in t:
                if not m.isfile(): continue
                category='qa_jsonl' if '/qa_jsonl/' in m.name else '/'.join(m.name.split('/')[-2:-1])
                counts[category]+=1
                if len(examples[category])<5: examples[category].append(m.name)
                if counts['image_color']>=5: break
    except (tarfile.TarError,EOFError,OSError) as e:
        report['bounded_prefix_end']=str(e)
    report.update(status='PROBE_COMPLETE_NOT_FULL_DOWNLOAD',counts=counts,examples=examples)
except Exception as e:
    report.update(status='PROBE_FAILED',error=str(e).split(' for url:')[0])
write(a.output/'report.json',report)
print(json.dumps(report),flush=True)
