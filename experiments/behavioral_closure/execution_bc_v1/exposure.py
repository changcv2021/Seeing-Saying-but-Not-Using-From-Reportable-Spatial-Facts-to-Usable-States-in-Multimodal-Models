"""Candidate-focused C1 exposure and byte/decoded/perceptual overlap audit."""
from collections import defaultdict,Counter
from bc_common import *
from data_continuation_v1.prepare import source_guard

def main():
    a=cli(__doc__).parse_args();c,sws,out=context(a)
    if a.dry_run:print('Registered historical inputs/reviews and candidate-source overlap; no prediction access.');return
    dest=out/'P4_C1';guard=source_guard()
    inv=sws/'repairs/world_identity_v2/inventory';old=sws/'preparation/global_assets_breadth_v1_20260910'
    fresh=sws/'preparation/holdout_val_rebuild_v1_20260910'
    candidate_pairs=list(rows(fresh/'private_gold/independent_pairs.jsonl'))
    candidates={r['world_cluster_id'] for r in candidate_pairs}
    membership={r['world_cluster_id']:r for r in rows(inv/'manifest/source_membership_audit.jsonl')}
    aliases={w:k for k,m in membership.items() for w in m['aliases']}
    canon=lambda w:aliases.get(cluster(w),cluster(w))
    signatures=list(rows(old/'asset_signatures.jsonl'));byhash=defaultdict(list);bypath={r['path']:r for r in signatures}
    for r in signatures:byhash[r['sha256']].append(r)
    pathworld=defaultdict(set)
    for r in signatures:pathworld[r['path']].update(r['worlds'])
    meta={r['sample_id']:canon(r['global_world_id']) for r in rows(sws/'repairs/world_identity_v2/baseline_world_metadata.jsonl')}
    parent=sws.parent.parent;studies=[]
    for name in ('state_binding_phase_a_v2','state_binding_phase_a1','spaceconflict_b0'):
        studies.extend(p for p in (parent/name).iterdir() if p.is_dir())
    manifests={Path(c['baseline'])/'requests.jsonl'}
    for study in studies:
        if (study/'inputs').exists():manifests.update((study/'inputs').rglob('*.jsonl'))
    manifests.update((sws/'batches').glob('*/public_inputs/requests.jsonl'))
    manifests.update((sws/'public_inputs').rglob('requests.jsonl'))
    for study in (parent/'qwen35_scale_512_20260906',parent/'qwen35_scale_20260906',parent/'qwen2_5_vl_7b'):
        for sub in ('inputs','public_inputs'):
            if (study/sub).exists():manifests.update((study/sub).rglob('*.jsonl'))
        if (study/'requests.jsonl').exists():manifests.add(study/'requests.jsonl')
    sources=[entry(p) for p in (fresh/'private_gold/independent_pairs.jsonl',old/'asset_signatures.jsonl',old/'cross_world_edges.jsonl',inv/'manifest/source_membership_audit.jsonl')]
    save(dest/'EXPOSURE_AUDIT_LOCK.json',dict(created_at=now(),code=entry(__file__),sources=sources,
        manifests=[entry(p) for p in sorted(manifests)],candidates=sorted(candidates),
        scope='REGISTERED_STUDY_INPUTS_PLUS_REVIEW_METADATA; UNSELECTED_SOURCE_LOCATORS_QUARANTINED',
        pretrained_exposure_certification=False,manual_unrecorded_browsing_certification=False,
        selection='ALL_SOURCE_READY_LOCAL_CANDIDATES_NO_PREDICTIONS',phash_hamming_threshold=4))
    exposed=defaultdict(set);media=defaultdict(lambda:dict(worlds=set(),hashes=set()));edges=[];unresolved=[]
    def media_items(obj):
        if isinstance(obj,dict):
            if obj.get('kind') in ('image','video') and isinstance(obj.get('path'),str):yield obj
            for k in ('payload','original_input','media','images','views'):
                if k in obj:yield from media_items(obj[k])
        elif isinstance(obj,list):
            for v in obj:yield from media_items(v)
    for path in sorted(manifests):
        for line,r in enumerate(rows(path),1):
            ids={canon(r[k]) for k in ('world_cluster_id','global_world_id','cluster_id','world_id') if isinstance(r.get(k),str) and ':' in r[k]}
            if r.get('sample_id') in meta:ids.add(meta[r['sample_id']])
            mm=list(media_items(r))
            for m in mm:ids.update(pathworld.get(m['path'],set()))
            if not ids and mm:unresolved.append(dict(manifest=str(path),line=line,request_id=r.get('request_id'),reason='INPUT_WORLD_ID_UNRESOLVED'))
            for w in ids:exposed[w].add(str(path))
            for m in mm:
                f=m['path'];media[f]['worlds'].update(ids)
                if m.get('sha256'):media[f]['hashes'].add(m['sha256'].removeprefix('sha256:'))
    # Old sealed partitions stay forbidden even if no inference was executed.
    for w,m in membership.items():
        if m['previously_exposed']:exposed[w].add('FROZEN_SOURCE_MEMBERSHIP_EXPOSURE')
    # Explicit review metadata, not source inventories or output tables.
    review_refs=[]
    for study in studies:
        review=study/'review'
        if not review.exists():continue
        for path in sorted(review.glob('*.jsonl')):
            review_refs.append(entry(path))
            for r in rows(path):
                for k in ('world_cluster_id','global_world_id','cluster_id','world_id'):
                    if isinstance(r.get(k),str) and ':' in r[k]:exposed[canon(r[k])].add(str(path))
    for w,why in sorted(exposed.items()):edges.append(dict(kind='REGISTERED_EXPOSURE',world_cluster_id=w,evidence=sorted(why)))
    from PIL import Image,ImageOps
    import numpy as np
    from scipy.fft import dctn
    def sign(f):
        h=sha(f)
        if f in bypath and bypath[f]['sha256']==h:return dict(bypath[f],path=f)
        # Hash equality authorizes reuse of decoded signatures, not inference of source IDs.
        if byhash.get(h):return dict(byhash[h][0],path=f,worlds=sorted(media[f]['worlds']))
        with Image.open(f) as im:
            im=ImageOps.exif_transpose(im).convert('RGB');dim=list(im.size)
            dec=digest([im.size,hashlib.sha256(im.tobytes()).hexdigest()])
            xx=dctn(np.asarray(ImageOps.grayscale(im).resize((32,32)),dtype=float),type=2,norm='ortho')[:8,:8]
            bits=xx.flatten()>np.median(xx.flatten()[1:]);bits[0]=False
        return dict(path=f,sha256=h,decoded_sha256=dec,phash=format(sum(int(v)<<i for i,v in enumerate(bits)),'016x'),dimensions=dim,modality='image')
    historical=[];failed=[]
    for f,m in sorted(media.items()):
        try:
            sig=sign(f)
            if m['hashes'] and sig['sha256'] not in m['hashes']:raise ValueError('DECLARED_MEDIA_HASH_MISMATCH')
            sig['worlds']=sorted(m['worlds']);historical.append(sig)
        except Exception as exc:failed.append(dict(path=f,reason=type(exc).__name__+': '+str(exc),worlds=sorted(m['worlds'])))
    allsigned=signatures+historical;candidate_sig=[r for r in signatures if candidates.intersection(r['worlds'])]
    overlaps=defaultdict(list)
    # Candidate-centric comparison is bounded: unrelated missing source assets are not read.
    for x in candidate_sig:
        cw=candidates.intersection(x['worlds'])
        for y in allsigned:
            other=set(y.get('worlds',[]))-set(x['worlds'])
            if not other:continue
            kind=None
            if x['sha256']==y['sha256']:kind='BYTE_IDENTICAL'
            elif x.get('decoded_sha256') and x['decoded_sha256']==y.get('decoded_sha256'):kind='DECODED_IDENTICAL'
            elif x.get('phash') and y.get('phash') and (int(x['phash'],16)^int(y['phash'],16)).bit_count()<=4:kind='PHASH_LE4'
            if kind:
                for w in cw:overlaps[w].append(dict(kind=kind,other_worlds=sorted(other),paths=[x['path'],y['path']]))
    cert=[]
    for w in sorted(candidates):
        reasons=list(membership[w]['reasons'])
        if w in exposed:reasons.append('HISTORICAL_EXPOSURE')
        if overlaps[w]:reasons.append('CROSS_WORLD_ASSET_LINK_REQUIRES_RESOLUTION')
        if failed:reasons.append('HISTORICAL_USED_MEDIA_SIGNATURE_INCOMPLETE')
        if unresolved:reasons.append('HISTORICAL_INPUT_WORLD_MAPPING_INCOMPLETE')
        if not any(w in r['worlds'] for r in candidate_sig):reasons.append('CANDIDATE_SIGNATURE_MISSING')
        cert.append(dict(world_cluster_id=w,status='QUALIFIED_WITHIN_REGISTERED_HISTORY' if not reasons else 'BLOCKED',
            reasons=reasons,source_family='COUNT',candidate_media=len([r for r in candidate_sig if w in r['worlds']]),
            overlaps=overlaps[w],exposure_sources=sorted(exposed.get(w,[])),
            review_grade='AUTO_ONLY_PROVISIONAL',manual_unrecorded_exposure='NOT_CERTIFIABLE_FROM_FILES'))
    csvsave(dest/'c1_candidate_worlds.csv',cert);save(dest/'candidate_qualification.jsonl',cert,'jsonl')
    csvsave(dest/'c1_exclusion_reasons.csv',[r for r in cert if r['reasons']]);save(dest/'c1_exposure_graph.jsonl',edges,'jsonl')
    save(dest/'historical_used_media_signatures.jsonl',historical,'jsonl');save(dest/'failed_historical_media.jsonl',failed,'jsonl')
    save(dest/'unresolved_historical_world_ids.jsonl',unresolved,'jsonl');save(dest/'review_metadata_sources.json',review_refs)
    acc=dict(status='CANDIDATE_AUDIT_COMPLETE',candidates=len(cert),qualified=sum(not r['reasons'] for r in cert),
        manifests=len(manifests),registered_exposed_worlds=len(exposed),historical_used_media=len(historical),
        failed_media=len(failed),unresolved_input_world_ids=len(unresolved),candidate_media=len(candidate_sig),
        source_unresolved_locators_not_required_to_all_resolve=True,worlds_frozen=False,job_id=os.environ['SLURM_JOB_ID'],
        prediction_guard=guard,manual_browsing_coverage='REGISTERED_RECORDS_ONLY',code=entry(__file__))
    save(dest/'ACCEPTANCE.json',acc);print(json.dumps(acc),flush=True)

if __name__=='__main__':main()
