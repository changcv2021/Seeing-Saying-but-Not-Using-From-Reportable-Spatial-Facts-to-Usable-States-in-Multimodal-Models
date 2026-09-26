"""Recover unmarked raw views from downloaded official SPAR-Bench with unique annotation joins."""
import argparse
import collections
import hashlib
import io
import json
import tarfile
from pathlib import Path
import pyarrow.dataset as ds
from PIL import Image
from common import load, sha, write

TASKS={'obj_spatial_relation_oc_mv','obj_spatial_relation_oo_mv'}

def unmarked_indices(row):
    frames=row.get('image') or row.get('images') or []
    if len(frames)!=3: return []
    # Never reuse any source frame with a colored marker already baked in.
    if any(row.get(k) for k in ('red_point','green_point','blue_point','point_list','bbox_list')):
        return []
    active=sum(bool(row.get(c+'_bbox')) for c in ('red','green','blue','yellow'))
    indices=row.get('bbox_img_idx') or []
    if len(indices)==1 and isinstance(indices[0],list): indices=indices[0]
    if active==0 or len(indices)!=active or any(not isinstance(x,int) or x not in range(3) for x in indices):
        return []
    return [i for i in range(3) if i not in indices]

def canonical_path(dataset,path):
    if path.startswith('spar/'): return path
    if path.startswith(dataset+'/'): return 'spar/'+path
    return f'spar/{dataset}/images/{path}'

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--requirements',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--run-id',required=True)
    p.add_argument('--seed',type=int,default=20260905)
    p.add_argument('--limit',type=int)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--resume',action='store_true')
    a=p.parse_args()
    if a.dry_run:
        print('PLANNED: local official metadata joins and unmarked embedded views; no network')
        return
    a.output.mkdir(parents=True,exist_ok=True)
    if a.resume and (a.output/'report.json').exists():
        old=json.loads((a.output/'report.json').read_text())
        if old.get('status')=='COMPLETE' and all(sha(p)==h for p,h in old['output_hashes'].items()):
            print(json.dumps(old)); return
    inputs={str(a.requirements):sha(a.requirements)}
    wanted={r['locator'] for r in load(a.requirements)}
    if a.limit: wanted=set(sorted(wanted)[:a.limit])
    base=Path('external/upstream/data/full_media_incoming/spar')
    bench_root=base/'ee122877c25c8bb08539b07e06d872152c9968f1/SPAR-Bench/data'
    shards=sorted(bench_root.glob('*.parquet'))
    dataset=ds.dataset([str(p) for p in shards],format='parquet')
    benchmark=dataset.to_table(columns=['id','source','task','question','answer'],filter=ds.field('task').isin(sorted(TASKS))).to_pylist()
    target_keys={(str(r['source']).lower(),r['task'],r['question'],str(r['answer'])) for r in benchmark}
    matches={}; ambiguous=set(); seen=collections.Counter()
    for source in ('scannet','scannetpp','structured3d'):
        archive=base/'0fe664cbada1e7c1173fd743e0f781882eebf777/SPAR-7M'/f'{source}.tar.gz'
        inputs[str(archive)]=sha(archive)
        with tarfile.open(archive,'r|gz') as t:
            for member in t:
                if not member.isfile() or not member.name.endswith('.jsonl'): continue
                task=next((x for x in TASKS if '/'+x+'/' in member.name),None)
                if task is None: continue
                for line in t.extractfile(member):
                    r=json.loads(line)
                    question=r.get('question'); answer=r.get('answer')
                    if question is None and r.get('conversations'):
                        question=r['conversations'][0]['value']; answer=r['conversations'][1]['value']
                    key=(source,task,question,str(answer))
                    if key not in target_keys: continue
                    paths=[canonical_path(source,x) for x in r.get('image') or r.get('images') or []]
                    unmarked=unmarked_indices(r)
                    signature=(tuple(paths),tuple(unmarked))
                    if key in matches and matches[key]['signature']!=signature: ambiguous.add(key)
                    matches[key]=dict(signature=signature,paths=paths,unmarked=unmarked,
                                      annotation_archive=str(archive),annotation_member=member.name,
                                      annotation_record_sha256=hashlib.sha256(line).hexdigest())
        seen[source]=sum(k[0]==source and k not in ambiguous for k in matches)
        print(json.dumps(dict(source=source,unique_qa_matches=seen[source],ambiguous=len(ambiguous))),flush=True)
    selections={}; rejected=collections.Counter()
    for r in benchmark:
        key=(str(r['source']).lower(),r['task'],r['question'],str(r['answer']))
        match=matches.get(key)
        if not match or key in ambiguous:
            rejected['ANNOTATION_JOIN_ABSENT_OR_AMBIGUOUS']+=1; continue
        selected=[(i,match['paths'][i]) for i in match['unmarked'] if match['paths'][i] in wanted]
        if selected:
            if r['id'] in selections: raise ValueError('DUPLICATE_BENCHMARK_ID')
            selections[r['id']]=(selected,match)
    recovered=collections.defaultdict(list)
    if selections:
        for shard in shards:
            inputs[str(shard)]=sha(shard)
        for batch in dataset.scanner(columns=['id','image'],filter=ds.field('id').isin(list(selections)),batch_size=16).to_batches():
            for row in batch.to_pylist():
                selected,match=selections[row['id']]
                images=row['image']
                if len(images)!=len(match['paths']):
                    rejected['BENCH_IMAGE_COUNT_MISMATCH']+=1; continue
                for index,loc in selected:
                    value=images[index]
                    payload=value if isinstance(value,bytes) else value.get('bytes')
                    with Image.open(io.BytesIO(payload)) as im:
                        im.load()
                        if im.format!='JPEG':
                            rejected['NON_JPEG_SOURCE_VIEW']+=1; continue
                    digest=hashlib.sha256(payload).hexdigest()
                    path=a.output/'images'/f'{digest}.jpg'
                    path.parent.mkdir(exist_ok=True)
                    if path.exists() and sha(path)!=digest: raise ValueError('EXISTING_IMAGE_HASH_MISMATCH')
                    if not path.exists(): path.write_bytes(payload)
                    recovered[loc].append(dict(locator=loc,status='PASS',identity_status='VERIFIED',materialized_jpg=str(path),
                        materialized_sha256=digest,provenance=dict(method='UNIQUE_OFFICIAL_QA_JOIN_UNMARKED_VIEW_ONLY',
                        bench_revision='ee122877c25c8bb08539b07e06d872152c9968f1',benchmark_row_id=row['id'],view_index=index,
                        **{k:v for k,v in match.items() if k!='signature'})))
    assets=[]
    for loc,records in recovered.items():
        if len({r['materialized_sha256'] for r in records})!=1:
            rejected['CONFLICTING_SOURCE_PIXEL_PAYLOADS']+=1; continue
        assets.append(records[0])
    assets.sort(key=lambda r:r['locator'])
    write(a.output/'assets.jsonl',assets,jsonl=True)
    report=dict(status='COMPLETE',run_id=a.run_id,seed=a.seed,matched_qa_by_source=seen,
                recovered_unique_frames=len(assets),by_dataset=dict(collections.Counter(r['locator'].split('/')[1] for r in assets)),
                reject_counts=rejected,input_hashes=inputs,output_hashes={str(a.output/'assets.jsonl'):sha(a.output/'assets.jsonl')},code_sha256=sha(__file__))
    write(a.output/'report.json',report)
    print(json.dumps(report),flush=True)

if __name__=='__main__': main()
