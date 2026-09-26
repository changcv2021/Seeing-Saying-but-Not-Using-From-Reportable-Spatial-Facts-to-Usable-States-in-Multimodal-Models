"""Register the entire frozen release, verify available media, build blind requests."""
import argparse
import collections
import json
import os
import time
import hashlib
import io
from functools import lru_cache
from pathlib import Path
from PIL import Image
from common import LABELS, RUBRIC, load, unique, sha, write
from spar_media import view_plan, present

def media_audit_records(cache):
    """Checkpoint records may already include path; emit it exactly once."""
    return [dict(value, path=path) for path, value in cache.items()]

def merge_splits(tables):
    merged = {}
    for table in tables:
        for row in table:
            world, split = row['global_world_id'], row['split']
            if split not in ('train', 'dev', 'test'):
                raise ValueError(f'INVALID_WORLD_SPLIT:{world}:{split}')
            if world in merged and merged[world] != split:
                raise ValueError(f'CONFLICTING_WORLD_SPLIT:{world}')
            merged[world] = split
    return merged

def unknown_metadata(row, candidate, certificate, pair, splits=None):
    """Independent Unknown exports need not have a selected binary parent."""
    sid = row['sample_id']
    if (candidate.get('unknown_id') != sid or candidate.get('parent_pair_id') != row['pair_id']
            or candidate.get('label') != 'UNKNOWN' or candidate.get('status') != 'AUTO_ACCEPTED_UNKNOWN'
            or candidate['claim']['natural_text'] != row['claim'] or candidate['media'] != row['media']
            or certificate.get('parent_pair_id') != row['pair_id'] or certificate.get('label') != 'UNKNOWN'):
        raise ValueError(f'UNKNOWN_PROVENANCE_MISMATCH:{sid}')
    level = certificate['would_be_level_if_resolved']
    if level not in ('L1', 'L2', 'L3'):
        raise ValueError(f'UNKNOWN_LEVEL_INVALID:{sid}')
    split = candidate['split']
    if split not in ('train', 'dev', 'test') or (splits is not None and split != splits.get(candidate['global_world_id'])):
        raise ValueError(f'UNKNOWN_WORLD_SPLIT_MISMATCH:{sid}')
    task = (pair or {}).get('task') or {}
    return dict(level=level, dataset=candidate['source_dataset'], split=split,
                track=task.get('primary_diagnostic_tag', 'Not annotated in released pair'),
                operator=task.get('operator_id'), metadata_origin='HASH_VERIFIED_UNKNOWN_SOURCE_AND_CERTIFICATE',
                global_world_id=candidate['global_world_id'], parent_in_binary_release=pair is not None)

class MediaVerifier:
    """Persist hash/decode checks; cache path resolution and repeated media references."""
    def __init__(self, bundle, checkpoint, resume):
        self.bundle = bundle.resolve()
        self.cache, self.previous = {}, {}
        self.checkpoint = checkpoint
        self.new_checks = self.reused_checks = 0
        if resume and checkpoint.exists():
            for line in checkpoint.read_text().splitlines():
                try:
                    item = json.loads(line)
                    self.previous[item['path']] = item
                except (ValueError, KeyError):
                    # A killed process may leave a truncated final line. Never reuse it.
                    continue
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        self.stream = checkpoint.open('a')
        self.stream.write('\n')

    @lru_cache(maxsize=None)
    def absolute(self, value):
        path = Path(value)
        resolved = (path if path.is_absolute() else self.bundle/path).resolve()
        if self.bundle not in resolved.parents:
            raise ValueError(f'MEDIA_OUTSIDE_PERSISTENT_BUNDLE:{path}')
        return str(resolved)

    def verify(self, value, decode=True, expected=''):
        path = self.absolute(value)
        if path not in self.cache or (decode and not self.cache[path].get('decoded')):
            try:
                stat = Path(path).stat()
                signature = [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_dev, stat.st_ino]
                previous = self.previous.get(path, {})
                if (previous.get('status') == 'PASS' and previous.get('signature') == signature
                        and (not decode or previous.get('decoded'))):
                    result = previous
                    self.reused_checks += 1
                else:
                    if decode:
                        payload = Path(path).read_bytes()
                        digest = hashlib.sha256(payload).hexdigest()
                        with Image.open(io.BytesIO(payload)) as image:
                            image.load()
                    else:
                        digest = sha(path)
                    result = dict(status='PASS', sha256=digest, bytes=stat.st_size, signature=signature, decoded=decode)
                    self.new_checks += 1
                self.cache[path] = result
            except Exception as exc:
                self.cache[path] = dict(status='FAIL', error=repr(exc))
            self.stream.write(json.dumps(dict(self.cache[path], path=path), sort_keys=True)+'\n')
            self.stream.flush()
            if len(self.cache) % 25 == 0:
                os.fsync(self.stream.fileno())
            if len(self.cache) % 250 == 0:
                print(f'[media] unique={len(self.cache)} new={self.new_checks} reused={self.reused_checks}', flush=True)
        result = self.cache[path]
        if result['status'] != 'PASS':
            raise ValueError(f'MEDIA_READ_OR_DECODE_FAILED:{path}')
        if expected and result['sha256'] != expected.removeprefix('sha256:'):
            raise ValueError(f'MEDIA_HASH_MISMATCH:{path}')
        return path

    def checked(self, media):
        for item in media:
            kind = item.get('kind', 'image')
            if kind not in ('image','video','video_frames'):
                raise ValueError(f'UNSUPPORTED_MEDIA_KIND:{kind}')
            paths = item.get('paths') if kind == 'video_frames' else [item.get('path')]
            if not paths or not all(isinstance(path, str) for path in paths):
                raise ValueError('INVALID_MEDIA_SCHEMA')
            resolved = [self.verify(path, kind != 'video', item.get('sha256','') if kind == 'image' else '') for path in paths]
            if kind == 'video_frames':
                item['paths'] = resolved
            else:
                item['path'] = resolved[0]
        return media

    def close(self):
        self.stream.flush(); os.fsync(self.stream.fileno()); self.stream.close()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--seed', type=int, default=20260904)
    p.add_argument('--limit', type=int)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--metadata-only', action='store_true', help='Validate every source/gold join before any media I/O')
    p.add_argument('--spar-assets', type=Path, help='Verified extracted ScanNet/ScanNet++ asset manifest')
    p.add_argument('--checkpoint-source', type=Path, help='Reuse prior media checks without changing that run')
    args = p.parse_args()
    b, out = args.bundle, args.run_root
    if args.dry_run:
        print(json.dumps(dict(status='PLANNED', total_expected=24196, run_id=args.run_id)))
        return
    if (out/'inventory.json').exists():
        if not args.resume:
            raise FileExistsError(out/'inventory.json')
        report = json.loads((out/'inventory.json').read_text())
        for path, expected in report['output_hashes'].items():
            if sha(path) != expected:
                raise ValueError('PREPARATION_RESUME_HASH_MISMATCH')
        print(json.dumps(report)); return
    inputs = {}
    def read(path):
        inputs[str(path)] = sha(path)
        return load(path)
    r13, r4 = b/'benchmark/l1_l3/release', b/'benchmark/l4/release'
    pairs = unique(read(r13/'pairs.jsonl'), 'pair_id')
    claims = read(r13/'claims.jsonl')
    unknown = read(r13/'unknown_challenge.jsonl')
    old = unique(read(b/'benchmark/l1_l3/evaluation/requested_samples.available.portable.jsonl'))
    s3d_path = b/'upstream_media/spar7m_acquisition/alternative_sources/validation/structured3d/full_extract_report.json'
    inputs[str(s3d_path)] = sha(s3d_path)
    s3d = {r['locator']: r for r in json.loads(s3d_path.read_text())['completed'] if not r['withheld']}
    spar_manifests = {}
    if args.spar_assets:
        for asset in read(args.spar_assets):
            if asset.get('identity_status') != 'VERIFIED' or asset.get('status') != 'PASS' or not asset.get('provenance'):
                raise ValueError('UNVERIFIED_SPAR_ASSET_IN_MANIFEST')
            if asset['locator'] in s3d:
                raise ValueError('DUPLICATE_SPAR_ASSET_LOCATOR')
            s3d[asset['locator']] = asset
        index = args.project/'data/media_index/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/qualitative_relation_media.v2.jsonl'
        spar_manifests = {r['media_id']: r for r in read(index)}
    release_manifest_path = r13/'manifest.json'
    inputs[str(release_manifest_path)] = sha(release_manifest_path)
    release_manifest = json.loads(release_manifest_path.read_text())
    # Use the actual, hash-pinned export inputs, not an arbitrary union of
    # historical split tables from experiments that may not enter this release.
    sampled_inputs = [(rel,digest) for rel,digest in release_manifest['input_hashes'].items()
                      if rel.startswith('sampled/pairs.')]
    if len(sampled_inputs) != 1:
        raise ValueError('EXPECTED_ONE_FROZEN_SAMPLED_INPUT')
    sampled_rel, sampled_digest = sampled_inputs[0]
    sampled_path = args.project/sampled_rel
    sampled = unique(read(sampled_path), 'pair_id')
    if inputs[str(sampled_path)] != sampled_digest.removeprefix('sha256:') or set(sampled) != set(pairs):
        raise ValueError('SAMPLED_SOURCE_HASH_OR_IDS_MISMATCH')
    unknown_sources = {}
    for rel, expected_hash in release_manifest['input_hashes'].items():
        if not rel.startswith('candidates/unknown/'):
            continue
        path = args.project/rel
        source_rows = read(path)
        if inputs[str(path)] != expected_hash.removeprefix('sha256:'):
            raise ValueError(f'UNKNOWN_SOURCE_HASH_MISMATCH:{rel}')
        for row in source_rows:
            if row['unknown_id'] in unknown_sources:
                raise ValueError(f'DUPLICATE_UNKNOWN_SOURCE:{row["unknown_id"]}')
            unknown_sources[row['unknown_id']] = row
    requests, gold, rejects, drafts = [], [], [], []
    def add(request, expected, meta, reference=None, unavailable=None):
        sid = request['sample_id']
        if expected not in LABELS or not isinstance(request['claim_text'], str) or not request['claim_text'].strip():
            raise ValueError(f'INVALID_GOLD_OR_CLAIM:{sid}')
        record = dict(sample_id=sid, gold=expected, pair_id=request.get('pair_id'), component=request['component'], **meta)
        record['reference_proposition'] = None if expected == 'UNKNOWN' else reference
        gold.append(record)
        # Metadata needed for stratified selection is never rendered in the model prompt.
        request.update({k: meta[k] for k in ('level', 'dataset', 'split', 'track')})
        drafts.append((request, meta, unavailable))
    for component, records in [('binary', claims), ('unknown', unknown)]:
        for row in records:
            pair = pairs.get(row['pair_id'])
            candidate = None
            if component == 'unknown':
                candidate = unknown_sources[row['sample_id']]
                cert_path = args.project/candidate['certificate_path']
                inputs[str(cert_path)] = sha(cert_path)
                if inputs[str(cert_path)] != candidate['certificate_sha256'].removeprefix('sha256:'):
                    raise ValueError(f'UNKNOWN_CERTIFICATE_HASH_MISMATCH:{row["sample_id"]}')
                meta = unknown_metadata(row, candidate, json.loads(cert_path.read_text()), pair)
                reference = None
            else:
                if pair is None:
                    raise ValueError(f'BINARY_PARENT_MISSING:{row["sample_id"]}')
                task, source = pair['task'], pair['source']
                frozen = sampled[row['pair_id']]
                if (frozen['global_world_id'] != source['global_world_id'] or frozen['level'] != task['level']
                        or frozen['source_dataset'] != source['source_dataset'] or frozen['primary_track'] != task['primary_diagnostic_tag']):
                    raise ValueError(f'SAMPLED_SOURCE_METADATA_MISMATCH:{row["pair_id"]}')
                meta = dict(level=task['level'], track=task['primary_diagnostic_tag'], dataset=source['source_dataset'],
                            split=frozen['split'], operator=task['operator_id'], global_world_id=source['global_world_id'],
                            metadata_origin='HASH_VERIFIED_FROZEN_SAMPLED_SOURCE')
                reference = pair['supported_claim']['natural_text']
            sid, unavailable = row['sample_id'], None
            if sid in old:
                request = old[sid]
                if request['claim_text'] != row['claim'] or request.get('pair_id') != row['pair_id']:
                    raise ValueError(f'OLD_REQUEST_CLAIM_MISMATCH:{sid}')
            else:
                media = []
                refs = row['media'].get('source_references') or []
                try:
                    planned = view_plan(row,component,spar_manifests,candidate) if args.spar_assets else [
                        dict(locator=ref.get('archive_member') or ref.get('relative_path'),role=ref.get('role','primary'),boxes=[]) for ref in refs]
                    for item in planned:
                        asset = s3d.get(item['locator'])
                        if asset is None:
                            raise ValueError(f'UPSTREAM_MEDIA_MISSING_OR_FRAME_IDENTITY_UNVERIFIED:{item["locator"]}')
                        media.append(present(asset,item,b/'media/spar_presentation_v1'))
                except ValueError as exc:
                    unavailable = str(exc)
                if not refs:
                    unavailable = 'UPSTREAM_ACCESSIBLE_REFERENCES_EMPTY'
                # Only source_references are used; withheld_evidence is never added.
                request = dict(sample_id=sid, pair_id=row['pair_id'], component=component, claim_text=row['claim'], media=media)
                if args.spar_assets:
                    request['media_context'] = 'Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.'
                    request['source_base_dataset'] = str(refs[0].get('archive_member') or refs[0].get('relative_path')).split('/')[1] if refs else 'unresolved'
            add(request, row['label'], meta, reference, unavailable)
    p4 = unique(read(b/'benchmark/l4/derived_annotations/track_annotations_v1/pairs.l4_three_part_v3.track_annotated_v1.jsonl'), 'pair_id')
    binary4 = read(r4/'model_inputs.l4_three_part_v3.jsonl')
    unknown4 = read(r4/'model_inputs.l4_unknown_v3.jsonl')
    g4 = {r['example_id']: r['label'] for r in read(r4/'gold.l4_three_part_v3.jsonl')}
    g4.update({r['sample_id']: r['label'] for r in read(r4/'gold.l4_unknown_v3.jsonl')})
    supported4 = {r['pair_id']: r['claim_text'] for r in binary4 if g4[r['example_id']] == 'SUPPORTED'}
    for component, records in [('binary', binary4), ('unknown', unknown4)]:
        for row in records:
            sid = row.get('example_id') or row['sample_id']
            pair = p4.get(row.get('pair_id'), {})
            task = pair.get('task') or {}
            meta = dict(level='L4', track=task.get('primary_track', 'Not annotated in released pair'),
                        dataset='hypo3d', split=row['split'], operator=task.get('operator_id'),
                        origin=row.get('l4_origin', 'UNKNOWN_CHALLENGE'), dependency_type=pair.get('dependency_type'),
                        global_world_id=pair.get('global_world_id'))
            media = [dict(kind='image', role=role, path=str(b/'media/l4'/ref['path']), sha256=ref['sha256'])
                     for role, ref in (row.get('media') or {}).items()]
            request = dict(sample_id=sid, pair_id=row.get('pair_id'), component=component, level='L4',
                           claim_text=row['claim_text'], intervention_text=row['intervention_text'], media=media)
            add(request, g4[sid], meta, supported4.get(row.get('pair_id')))
    unique(gold); unique([row[0] for row in drafts])
    if any(row['split'] not in ('train', 'dev', 'test') for row in gold):
        missing = [row['sample_id'] for row in gold if row['split'] not in ('train', 'dev', 'test')]
        raise ValueError(f'UNRESOLVED_SPLITS:{len(missing)}:{missing[:5]}')
    if len(gold) != 24196 or len(gold) != len(drafts):
        raise ValueError(f'FULL_RELEASE_COVERAGE_MISMATCH:{len(gold)}')
    metadata_report = dict(status='METADATA_PASS_MEDIA_NOT_YET_CHECKED', release_total=len(gold),
                           unknown_parent_absent=sum(r.get('parent_in_binary_release') is False for r in gold),
                           run_id=args.run_id, input_hashes=inputs)
    world_splits = collections.defaultdict(set)
    for record in gold:
        if record.get('global_world_id'):
            world_splits[record['global_world_id']].add(record['split'])
    conflicts = {world:sorted(values) for world,values in world_splits.items() if len(values)>1}
    write(out/'split_audit.json', dict(status='PASS' if not conflicts else 'SOURCE_DECLARED_SPLIT_CONFLICTS',
          conflicts=conflicts, policy='Preserve frozen source splits; never silently reassign. All-split evaluation remains available.'))
    metadata_report['actual_release_split_conflicts'] = len(conflicts)
    write(out/'metadata_preflight.json', metadata_report)
    print(json.dumps({k:v for k,v in metadata_report.items() if k!='input_hashes'}), flush=True)
    if args.metadata_only:
        return
    if args.checkpoint_source and not (out/'media_checkpoint.jsonl').exists():
        import shutil
        shutil.copyfile(args.checkpoint_source,out/'media_checkpoint.jsonl')
    verifier = MediaVerifier(b, out/'media_checkpoint.jsonl', args.resume)
    started = time.monotonic()
    try:
        for index, (request, meta, unavailable) in enumerate(drafts, 1):
            try:
                if unavailable:
                    raise ValueError(unavailable)
                request['media'] = verifier.checked(request.get('media') or [])
                requests.append(request)
            except ValueError as exc:
                rejects.append(dict(sample_id=request['sample_id'], pair_id=request.get('pair_id'), **meta, reject_code=str(exc)))
            if index % 500 == 0:
                progress = dict(processed=index, total=len(drafts), eligible=len(requests), unavailable=len(rejects),
                                media_checked=len(verifier.cache), seconds=round(time.monotonic()-started,1))
                write(out/'preparation_progress.json', progress)
                print(json.dumps(progress), flush=True)
    finally:
        verifier.close()
    write(out/'preparation_progress.json', dict(processed=len(drafts), total=len(drafts),
          eligible=len(requests), unavailable=len(rejects), media_checked=len(verifier.cache),
          seconds=round(time.monotonic()-started,1), phase='MEDIA_VALIDATED_EXPORT_PENDING'))
    media_cache = verifier.cache
    # Freeze all eligible rows; a small per-stratum smoke slice retains complete pairs.
    requests.sort(key=lambda r:r['sample_id'])
    buckets = collections.defaultdict(list)
    for row in requests:
        key = (row['level'], row['dataset'], row['component'], row['split'],
               row.get('source_base_dataset','existing_bundle'),
               tuple(sorted({m.get('kind','image') for m in row['media']})))
        buckets[key].append(row)
    chosen = {bucket[0]['sample_id'] for bucket in buckets.values()}
    chosen_pairs = {r['pair_id'] for r in requests if r['sample_id'] in chosen and r['component']=='binary'}
    smoke = [r for r in requests if r['sample_id'] in chosen or (r['component']=='binary' and r['pair_id'] in chosen_pairs)]
    if args.limit is not None:
        raise ValueError('FULL_RELEASE_PREPARATION_DOES_NOT_ALLOW_LIMIT_USE_SMOKE_FILE')
    outputs = {'requests.jsonl': requests, 'smoke.jsonl': smoke, 'private_gold.jsonl': gold, 'unavailable.jsonl': rejects,
               'media_audit.jsonl': media_audit_records(media_cache)}
    for name, rows in outputs.items():
        write(out/name, rows, jsonl=True)
    write(out/'rubric.json', RUBRIC)
    report = dict(status='PASS', run_id=args.run_id, seed=args.seed, release_total=len(gold),
                  eligible=len(requests), unavailable=len(rejects), smoke=len(smoke),
                  by_level=dict(collections.Counter(r['level'] for r in requests)),
                  recovered_spar_by_base_dataset=dict(collections.Counter(r['source_base_dataset'] for r in requests if r.get('source_base_dataset'))),
                  unavailable_by_source=dict(collections.Counter(r['dataset'] for r in rejects)),
                  scope='all release splits; test metrics separately; source-identity-unverified media excluded explicitly',
                  input_hashes=inputs, output_hashes={str(out/name): sha(out/name) for name in [*outputs, 'rubric.json']},
                  config=dict(bundle=str(b), project=str(args.project), run_id=args.run_id, seed=args.seed),
                  code_sha256=sha(__file__), code_commit='NO_GIT_REPOSITORY_AVAILABLE')
    write(out/'inventory.json', report)
    print(json.dumps(report, indent=2), flush=True)

if __name__ == '__main__':
    main()
