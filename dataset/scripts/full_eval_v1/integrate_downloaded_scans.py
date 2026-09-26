"""Extract needed local frames; accept only explicit camera-metadata joins."""
import argparse
import collections
import concurrent.futures
import hashlib
import io
import json
import pickle
import tarfile
import zipfile
from pathlib import Path
import numpy as np
from PIL import Image
from common import load, sha, write
from spar_media import locator, view_plan

def matrix_key(matrix):
    matrix=np.asarray(matrix, dtype=float)
    if matrix.shape!=(4,4) or not np.isfinite(matrix).all():
        return None
    return tuple(np.round(matrix,6).ravel())

def save_asset(root, row, payload, proof):
    with Image.open(io.BytesIO(payload)) as im:
        im.load()
        size=im.size
        if im.format!='JPEG':
            raise ValueError('EXPECTED_JPEG_IMAGE')
    digest=hashlib.sha256(payload).hexdigest()
    target=root/'images'/f'{digest}.jpg'
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if sha(target)!=digest:
            raise ValueError('EXISTING_EXTRACTED_IMAGE_HASH_MISMATCH')
    else:
        target.write_bytes(payload)
    return dict(locator=row, status='PASS', identity_status='VERIFIED', materialized_jpg=str(target),
                materialized_sha256=digest, bytes=len(payload), dimensions=size, provenance=proof)

def process_pp(job):
    scene, wanted, archive, expected_size, expected_hash, output, resume = job
    result_path=output/'scenes'/f'scannetpp_{scene}.json'
    if resume and result_path.exists():
        previous=json.loads(result_path.read_text())
        if previous['requested']==sorted(wanted) and all(Path(r['materialized_jpg']).is_file() and sha(r['materialized_jpg'])==r['materialized_sha256'] for r in previous['completed']):
            return previous
    completed=[]; failures=[]
    if not archive.exists():
        return dict(requested=sorted(wanted),completed=[],failed=[dict(locator=x,reject_code='SCANNETPP_ARCHIVE_NOT_DOWNLOADED') for x in wanted])
    if archive.stat().st_size!=expected_size or sha(archive)!=expected_hash:
        raise ValueError(f'SCANNETPP_ARCHIVE_HASH_MISMATCH:{scene}')
    by_member={f'{scene}/images/frame_{int(Path(x).stem):06d}.jpg':x for x in wanted}
    images={}; metadata=None; metadata_sha=None
    with tarfile.open(archive,'r|gz') as t:
        for member in t:
            name=member.name.removeprefix('./')
            if member.isfile() and name in by_member:
                if name in images:
                    raise ValueError('DUPLICATE_ARCHIVE_MEMBER')
                images[name]=t.extractfile(member).read()
            elif member.isfile() and name==f'{scene}/scene_iphone_metadata.npz':
                payload=t.extractfile(member).read()
                metadata_sha=hashlib.sha256(payload).hexdigest()
                with np.load(io.BytesIO(payload),allow_pickle=False) as meta:
                    names=meta['images'].tolist()
                    if len(set(names))!=len(names) or len(names)!=len(meta['trajectories']) or len(names)!=len(meta['intrinsics']):
                        raise ValueError('SCANNETPP_CAMERA_METADATA_LENGTH_OR_ID_CONFLICT')
                    metadata={n:dict(index=i,pose=meta['trajectories'][i],intrinsic=meta['intrinsics'][i]) for i,n in enumerate(names)}
    for member,row in by_member.items():
        try:
            if member not in images:
                raise ValueError('SCANNETPP_EXACT_FRAME_ABSENT_FROM_ARCHIVE')
            if metadata is None or Path(member).name not in metadata:
                raise ValueError('SCANNETPP_EXACT_FRAME_ABSENT_FROM_CAMERA_METADATA')
            camera=metadata[Path(member).name]
            if matrix_key(camera['pose']) is None or not np.isfinite(camera['intrinsic']).all():
                raise ValueError('SCANNETPP_CAMERA_METADATA_INVALID')
            proof=dict(method='OFFICIAL_NATIVE_FRAME_ID_JOIN_CAMERA_METADATA', archive=str(archive), archive_sha256=expected_hash,
                       member=member, metadata_member=f'{scene}/scene_iphone_metadata.npz', metadata_sha256=metadata_sha,
                       native_frame_id=int(Path(row).stem), camera_record_index=camera['index'],
                       mapping='SPAR image_color/N.jpg -> native iphone/rgb/frame_NNNNNN.jpg; never enumerate sparse mirror frames',
                       source_revision='9a719c1c43ba95595e7eb85d0e9c12cf73d73d75')
            completed.append(save_asset(output,row,images[member],proof))
        except ValueError as e:
            failures.append(dict(locator=row,reject_code=str(e)))
    result=dict(requested=sorted(wanted),completed=completed,failed=failures)
    write(result_path,result)
    print(json.dumps(dict(dataset='scannetpp',scene=scene,passed=len(completed),failed=len(failures))),flush=True)
    return result

def process_scannet(wanted, raw, annotations, output, input_hashes):
    # A mirror can renumber or filter frames differently in every scene.
    # Match the released reference camera matrix, not a guessed stride/nearest frame.
    refs={}; reference_files={}
    scenes={x.split('/')[3] for x in wanted}
    for split in ('train','val','test'):
        path=annotations/f'embodiedscan_infos_{split}.pkl'
        expected=path.with_suffix('.pkl.sha256').read_text().split()[0]
        digest=sha(path)
        if digest!=expected:
            raise ValueError('EMBODIEDSCAN_ANNOTATION_HASH_MISMATCH')
        input_hashes[str(path)]=digest
        with path.open('rb') as f:
            records=pickle.load(f)['data_list']
        for scene in records:
            world=scene['sample_idx']
            if not world.startswith('scannet/') or world.split('/')[-1] not in scenes:
                continue
            sid=world.split('/')[-1]
            for im in scene['images']:
                loc=f'spar/scannet/images/{sid}/image_color/{int(Path(im["img_path"]).stem)}.jpg'
                if loc in wanted:
                    refs[loc]=matrix_key(im['cam2global'])
                    reference_files[loc]=dict(annotation=str(path), annotation_sha256=digest, image_path=im['img_path'])
        del records
    archive=raw/'scannet/archives/scannet-frames.zip'
    expected='fe61e7f728b75af10b8fdb8ac203bdfa7f27f6e205fa2f416ad36f6ca063fb13'
    if sha(archive)!=expected:
        raise ValueError('SCANNET_ARCHIVE_HASH_MISMATCH')
    input_hashes[str(archive)]=expected
    targets=collections.defaultdict(lambda:collections.defaultdict(list))
    for loc,key in refs.items():
        if key is not None:
            targets[loc.split('/')[3]][key].append(loc)
    matches=collections.defaultdict(list)
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            parts=member.filename.split('/')
            if len(parts)!=3 or parts[0]!='scannet-frames' or parts[1] not in targets or not parts[2].endswith('.txt'):
                continue
            payload=z.read(member)
            key=matrix_key(np.loadtxt(io.BytesIO(payload)))
            for loc in targets[parts[1]].get(key,[]):
                matches[loc].append((member.filename,hashlib.sha256(payload).hexdigest()))
        completed=[]; failures=[]
        for loc in sorted(wanted):
            candidates=matches.get(loc,[])
            if len(candidates)!=1:
                code='SCANNET_REFERENCE_FRAME_POSE_NOT_RELEASED' if loc not in refs else ('SCANNET_EXACT_POSE_NOT_IN_DOWNLOADED_MIRROR' if not candidates else 'SCANNET_AMBIGUOUS_EXACT_POSE')
                failures.append(dict(locator=loc,reject_code=code,exact_matches=len(candidates)))
                continue
            member, pose_sha=candidates[0]
            jpg=member[:-4]+'.jpg'
            proof=dict(method='UNIQUE_EXACT_CAMERA_MATRIX_6_DECIMALS',archive=str(archive),archive_sha256=expected,
                       member=jpg,pose_member=member,pose_sha256=pose_sha,**reference_files[loc])
            completed.append(save_asset(output,loc,z.read(jpg),proof))
    result=dict(requested=sorted(wanted),completed=completed,failed=failures)
    write(output/'scannet.json',result)
    print(json.dumps(dict(dataset='scannet',passed=len(completed),failed=len(failures))),flush=True)
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--project',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--run-id',required=True)
    p.add_argument('--seed',type=int,default=20260905)
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--limit',type=int)
    p.add_argument('--resume',action='store_true')
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    if a.dry_run:
        print(json.dumps(dict(status='PLANNED',**{k:str(v) for k,v in vars(a).items()})))
        return
    a.output.mkdir(parents=True,exist_ok=True)
    input_hashes={}
    def read(path):
        input_hashes[str(path)]=sha(path)
        return load(path)
    index=a.project/'data/media_index/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/qualitative_relation_media.v2.jsonl'
    manifests={r['media_id']:r for r in read(index)}
    wanted=set()
    for name,component in [('claims.jsonl','binary'),('unknown_challenge.jsonl','unknown')]:
        for row in read(a.bundle/'benchmark/l1_l3/release'/name):
            refs=row['media'].get('source_references') or []
            if not refs or not str(locator(refs[0])).startswith(('spar/scannet/','spar/scannetpp/')):
                continue
            for item in view_plan(row,component,manifests):
                wanted.add(item['locator'])
    if a.limit is not None:
        wanted=set(sorted(wanted)[:a.limit])
    write(a.output/'required_locators.json',sorted(wanted))
    raw=a.bundle/'upstream_media/spar7m_raw'
    acq=a.bundle/'upstream_media/spar7m_acquisition'
    manifest_path=acq/'alternative_sources/manifests/scannetpp_required_526.tsv'
    input_hashes[str(manifest_path)]=sha(manifest_path)
    available={}
    for line in manifest_path.read_text().splitlines():
        scene,filename,size,digest=line.split('\t')
        available[scene]=(filename,int(size),digest)
    jobs=[]; missing=[]
    groups=collections.defaultdict(set)
    for loc in wanted:
        if loc.startswith('spar/scannetpp/'):
            groups[loc.split('/')[3]].add(loc)
    for scene,locs in sorted(groups.items()):
        if scene not in available:
            missing.extend(dict(locator=x,reject_code='SCANNETPP_SCENE_NOT_DOWNLOADED') for x in sorted(locs))
            continue
        filename,size,digest=available[scene]
        jobs.append((scene,locs,raw/'scannetpp/archives'/filename,size,digest,a.output,a.resume))
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        for r in pool.map(process_pp,jobs):
            results.append(r)
    annotations=Path('external/upstream/data/full_media_incoming/hypo3d/official/embodiedscan_v1/annotations')
    results.append(process_scannet({x for x in wanted if x.startswith('spar/scannet/')},raw,annotations,a.output,input_hashes))
    completed=sorted([r for group in results for r in group['completed']],key=lambda r:r['locator'])
    failures=sorted(missing+[r for group in results for r in group['failed']],key=lambda r:r['locator'])
    if len(completed)+len(failures)!=len(wanted):
        raise ValueError('INTEGRATION_LOCATOR_ACCOUNTING_MISMATCH')
    write(a.output/'assets.jsonl',completed,jsonl=True)
    write(a.output/'unresolved.jsonl',failures,jsonl=True)
    report=dict(status='COMPLETE_WITH_EXPLICIT_REJECTS' if failures else 'PASS',run_id=a.run_id,seed=a.seed,
                required=len(wanted),passed=len(completed),unresolved=len(failures),
                by_dataset=dict(collections.Counter(r['locator'].split('/')[1] for r in completed)),
                reject_codes=dict(collections.Counter(r['reject_code'] for r in failures)),
                input_hashes=input_hashes,output_hashes={str(a.output/n):sha(a.output/n) for n in ['assets.jsonl','unresolved.jsonl','required_locators.json']},
                code_sha256=sha(__file__),config={k:str(v) for k,v in vars(a).items()},code_commit='NO_GIT_REPOSITORY_AVAILABLE')
    write(a.output/'report.json',report)
    print(json.dumps(report),flush=True)

if __name__=='__main__':
    main()
