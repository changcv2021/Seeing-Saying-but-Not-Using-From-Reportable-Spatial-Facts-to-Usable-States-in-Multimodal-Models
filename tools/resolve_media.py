"""Relocate media in requests; never load gold or change claim/intervention text."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--requests',type=Path,required=True)
    p.add_argument('--media-map',type=Path,required=True,help='JSON mapping exported media path to your legally obtained local file')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();mapping=json.loads(a.media_map.read_text());cache={};out=[]
    for line in a.requests.read_text().splitlines():
        if not line.strip():continue
        r=json.loads(line)
        for m in r.get('media',[]):
            if 'paths' in m:
                m['paths']=[mapping.get(v,v) for v in m['paths']]
                if not all(Path(v).is_file() for v in m['paths']):raise FileNotFoundError('MISSING_VIDEO_FRAME')
            if 'path' not in m:continue
            old=m['path'];new=Path(mapping.get(old,old))
            if not new.is_file():raise FileNotFoundError('UNRESOLVED_MEDIA:' + old)
            if old not in cache:
                value=digest(new);expected=m.get('sha256','').removeprefix('sha256:')
                if expected and value!=expected:raise ValueError('MEDIA_HASH_MISMATCH:' + old)
                cache[old]=value
            m['path']=str(new.resolve())
        out.append(r)
    with a.output.open('x') as f:
        for r in out:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    print(json.dumps(dict(status='PASS',requests=len(out),checked_media=len(cache))))

if __name__=='__main__':main()
