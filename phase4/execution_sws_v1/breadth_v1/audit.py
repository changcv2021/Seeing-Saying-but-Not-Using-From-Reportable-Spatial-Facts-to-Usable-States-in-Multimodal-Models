"""All registered source asset reconciliation; no inference or prediction reads."""
import sys
from collections import Counter, defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from common_auto_v2 import *
from data_continuation_v1.prepare import source_guard
from real_compile_v1 import SOURCE_IMAGES, BUNDLE

def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('Registered-source asset index, actual hashes, perceptual edges, heldout eligibility.'); return
    dest=root/'preparation/global_assets_breadth_v1_20260910'
    if (dest/'ACCEPTANCE.json').exists(): print('ALREADY_COMPLETE'); return
    guard=source_guard(); p=Path(c['project']); inv=root/'repairs/world_identity_v2/inventory'
    memberships=list(rows(inv/'manifest/source_membership_audit.jsonl'))
    alias={w:r['world_cluster_id'] for r in memberships for w in r['aliases']}
    member={r['world_cluster_id']:r for r in memberships}
    canon=lambda w:alias.get(cluster(w),cluster(w))
    refs=[]; owners=defaultdict(set); locpaths=defaultdict(set); midowners=defaultdict(set)
    declared_hashes=defaultdict(set)
    def add(w,loc,path=None,hh=None):
        if not loc:return
        owners[str(loc)].add(canon(w))
        if path:locpaths[str(loc)].add(str(path))
        if hh:declared_hashes[str(path or loc)].add(hh.removeprefix('sha256:'))
    for path in sorted((p/'world_index').glob('*.jsonl')):
        refs.append(entry(path))
        for r in rows(path):
            for mid in r.get('media_ids',[]):midowners[mid].add(canon(r['global_world_id']))
    metadata={r['sample_id']:canon(r['global_world_id']) for r in rows(root/'repairs/world_identity_v2/baseline_world_metadata.jsonl')}
    path=Path(c['baseline'])/'requests.jsonl';refs.append(entry(path))
    for r in rows(path):
        w=metadata[r['sample_id']]
        for m in r.get('media',[]):
            loc=m.get('source_locator') or m['path']; add(w,loc,m['path'],m.get('sha256'))
            # Rendered bounding boxes are not a new underlying source asset.
            if m.get('presentation',{}).get('source_sha256'):
                declared_hashes[loc].add(m['presentation']['source_sha256'])
    acq=BUNDLE/'upstream_media/spar7m_acquisition'
    for rel in ('integration_v1_20260905/assets.jsonl','rgbd_recovery_v2_20260905/assets.jsonl','repair_missing_v2_20260905/bench_unmarked/assets.jsonl'):
        path=acq/rel
        if not path.exists():continue
        refs.append(entry(path))
        for r in rows(path):
            if r.get('status')!='PASS':continue
            loc=r.get('locator');f=r.get('materialized_jpg') or r.get('source_file')
            if loc and f:locpaths[loc].add(f); declared_hashes[f].add(r.get('materialized_sha256',r.get('source_sha256','')).removeprefix('sha256:'))
    # Metadata only, including excluded worlds; never open sealed graph semantics.
    for path in sorted((p/'data/media_index').rglob('*.jsonl')):
        refs.append(entry(path))
        for r in rows(path):
            ws=set(midowners.get(r.get('media_id'),set()))
            if r.get('resolved_global_world_id'):ws.add(canon(r['resolved_global_world_id']))
            if r.get('base_dataset') and r.get('scene_id'):ws.add(canon(r['base_dataset']+':'+r['scene_id']))
            locs=list(r.get('ordered_frame_paths',[]))+list(r.get('support_archive_members',[]))
            if r.get('archive_member'):locs.append(r['archive_member'])
            locs+=list(r.get('frame_roles',{}).values())
            for loc in locs:
                if not isinstance(loc,str):continue
                if '/ca_vqa/' in str(path) and loc.startswith('images/'):loc='cavqa_val/'+loc
                for w in ws:add(w,loc)
    # The source catalog supplies train-frame paths absent from older media indexes.
    catalog=inv/'private_gold/source_fact_catalog.jsonl'; refs.append(entry(catalog))
    for r in rows(catalog):
        g=r['fact'].get('grounding',{}); locs=list(g.get('archive_members',[]))+list(g.get('frame_roles',{}).values())
        for loc in locs:
            if isinstance(loc,str):add(r['world_cluster_id'],loc)
    save(dest/'AUDIT_LOCK.json',dict(created_at=now(),code=entry(__file__),inputs=refs,seed=c['seed'],
        scope='ALL_REGISTERED_WORLD_INDEX_AND_MEDIA_INDEX_PLUS_PERMITTED_FACT_LOCATORS_AND_BASELINE_MEDIA',
        predictions_used=False,phash='DCT_32_TO_8_MEDIAN_64_BITS',hamming_threshold=4,
        dense_bucket_policy='UNRESOLVED_SIGNATURE_GROUP_EXCLUDED_NOT_TRUNCATED',split_assignment='ONLY_AFTER_COVERAGE_ACCEPTANCE'))
    for loc in owners:
        if loc.startswith('cavqa_val/'):locpaths[loc].add(str(SOURCE_IMAGES/loc))
        elif loc.startswith(('camera_view/','top_view_')):locpaths[loc].add(str(BUNDLE/'media/l4'/loc))
        elif Path(loc).is_absolute():locpaths[loc].add(loc)
        else:
            locpaths[loc].add(str(p/loc))
    actualpaths=defaultdict(set); unresolved=[]
    for loc,ws in owners.items():
        found=[f for f in locpaths[loc] if Path(f).is_file()]
        if not found:unresolved.append(dict(locator=loc,worlds=sorted(ws),reason='REGISTERED_ASSET_NOT_LOCALLY_RESOLVED'));continue
        for f in found:actualpaths[f].update(ws)
    from PIL import Image,ImageOps,UnidentifiedImageError
    import numpy as np
    from scipy.fft import dctn
    records=[];failed=[]
    for n,(f,ws) in enumerate(sorted(actualpaths.items()),1):
        try:
            h=sha(f); ext=Path(f).suffix.lower(); rec=dict(path=f,worlds=sorted(ws),sha256=h,bytes=Path(f).stat().st_size)
            expected=declared_hashes[f]-{''}
            if expected and h not in expected:raise ValueError('DECLARED_HASH_MISMATCH')
            try:
                with Image.open(f) as im:
                    im=ImageOps.exif_transpose(im).convert('RGB'); rec['dimensions']=list(im.size)
                    rec['decoded_sha256']=digest([im.size,__import__('hashlib').sha256(im.tobytes()).hexdigest()])
                    xx=np.asarray(ImageOps.grayscale(im).resize((32,32)),dtype=float)
                xx=dctn(xx,type=2,norm='ortho')[:8,:8];med=np.median(xx.flatten()[1:])
                bits=xx.flatten()>med; bits[0]=False
                rec['phash']=format(sum(int(b)<<i for i,b in enumerate(bits)),'016x');rec['modality']='image'
            except UnidentifiedImageError:
                rec['modality']='non_image';rec['near_duplicate_status']='NOT_CHECKED_NON_IMAGE'
            records.append(rec)
        except (OSError,ValueError) as exc:failed.append(dict(path=f,worlds=sorted(ws),reason=str(exc)))
        if n%500==0:print(json.dumps(dict(stage='GLOBAL_ASSETS',checked=n,total=len(actualpaths))),flush=True)
    save(dest/'asset_signatures.jsonl',records,'jsonl');save(dest/'unresolved_assets.jsonl',unresolved,'jsonl');save(dest/'failed_assets.jsonl',failed,'jsonl')
    edges=[];exact={};phashes=defaultdict(list)
    for rec in records:
        for k in ('sha256','decoded_sha256'):
            if k not in rec:continue
            key=(k,rec[k]); prev=exact.get(key)
            if prev and set(prev['worlds'])!=set(rec['worlds']):edges.append(dict(kind=k,left=prev['worlds'],right=rec['worlds'],paths=[prev['path'],rec['path']]))
            else:exact[key]=rec
        if 'phash' in rec:phashes[int(rec['phash'],16)].append(rec)
    # Five chunks guarantee at least one shared chunk for <=4 bit differences.
    buckets=defaultdict(list)
    for h in phashes:
        for k in range(5):buckets[(k,(h>>(13*k))&8191)].append(h)
    seen=set();dense=[]
    for key,hh in buckets.items():
        if len(hh)>200:
            dense.append(dict(chunk=key,worlds=sorted({w for h in hh for r in phashes[h] for w in r['worlds']}),hashes=len(hh)));continue
        for i,h in enumerate(hh):
            for g in hh[i+1:]:
                pair=tuple(sorted((h,g)))
                if pair in seen:continue
                seen.add(pair)
                if (h^g).bit_count()>4:continue
                aa=phashes[h][0];bb=phashes[g][0]
                wa=sorted({w for r in phashes[h] for w in r['worlds']});wb=sorted({w for r in phashes[g] for w in r['worlds']})
                if set(wa)!=set(wb):edges.append(dict(kind='PHASH_HAMMING_LE4',left=wa,right=wb,paths=[aa['path'],bb['path']],distance=(h^g).bit_count()))
    # Identical phashes are near matches even when JPEG bytes differ.
    for h,rr in phashes.items():
        ws=sorted({w for r in rr for w in r['worlds']})
        if len(ws)>1:edges.append(dict(kind='PHASH_EQUAL',left=ws[:1],right=ws[1:],phash=format(h,'016x')))
    save(dest/'cross_world_edges.jsonl',edges,'jsonl');save(dest/'dense_signature_groups.jsonl',dense,'jsonl')
    gaps=Counter(w for r in unresolved+failed for w in r['worlds'])
    for r in records:
        if r['modality']=='non_image':
            for w in r['worlds']:gaps[w]+=1
    for r in dense:
        for w in r['worlds']:gaps[w]+=1
    linked=set(w for e in edges for side in ('left','right') for w in e[side])
    candidates=[]
    for w,m in sorted(member.items()):
        reasons=list(m['reasons'])
        if m['previously_exposed']:reasons.append('HISTORICALLY_EXPOSED_DISCOVERY_ONLY')
        if gaps[w]:reasons.append('INCOMPLETE_ASSET_OR_SIGNATURE_COVERAGE')
        if w in linked:reasons.append('CROSS_WORLD_ASSET_COMPONENT_RECONCILIATION_REQUIRED')
        if not any(w in r['worlds'] for r in records):reasons.append('NO_DECODED_MEDIA')
        candidates.append(dict(world_cluster_id=w,reasons=reasons,local_coverage_pass=not reasons,
            global_holdout_qualified=False,split='UNASSIGNED',note='Unresolved external registered assets prevent global no-overlap certification.'))
    save(dest/'holdout_eligibility.jsonl',candidates,'jsonl')
    save(dest/'ACCEPTANCE.json',dict(status='GLOBAL_REGISTERED_ASSET_AUDIT_COMPLETE',created_at=now(),job_id=os.environ['SLURM_JOB_ID'],
        registered_locators=len(owners),resolved_files=len(records),unresolved_locators=len(unresolved),failed_files=len(failed),
        cross_world_edges=len(edges),dense_signature_groups=len(dense),local_coverage_unexposed_candidates=sum(r['local_coverage_pass'] for r in candidates),
        global_holdout_frozen=False,confirmation_inference=False,prediction_guard=guard,
        scope='REGISTERED_ASSETS_NOT_ALL_DOWNLOADED_FILES',remaining='RESOLVE_MISSING_LOCATORS_NONIMAGE_NEAR_DUPLICATES_AND_COMPONENTS_BEFORE_GLOBAL_SPLIT'))

if __name__=='__main__':main()
