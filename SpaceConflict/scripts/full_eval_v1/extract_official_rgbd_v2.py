"""Offline, format-aware recovery from hash-verified official SPAR RGBD parts."""
import argparse
import collections
import hashlib
import io
import json
import os
import re
import tarfile
import time
import warnings
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from common import load, sha, write
from recover_official_rgbd import ConcatenatedParts, REVISION


class MediaReject(ValueError):
    pass


def decode_rgb(payload):
    """Sniff actual encoding, never trust the source locator's .jpg suffix."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload)) as image:
                fmt, mode, size = image.format, image.mode, image.size
                if fmt not in ('JPEG', 'PNG', 'WEBP', 'BMP', 'TIFF'):
                    raise MediaReject(f'UNSUPPORTED_RASTER_FORMAT:{fmt}')
                if getattr(image, 'n_frames', 1) != 1:
                    raise MediaReject('MULTIFRAME_SOURCE_NOT_A_STILL_RGB_VIEW')
                image.load()
                if mode not in ('RGB', 'L', 'RGBA', 'LA', 'P', 'CMYK'):
                    raise MediaReject(f'NON_COLOR_OR_UNSUPPORTED_PIXEL_MODE:{mode}')
                if mode in ('RGBA', 'LA') or 'transparency' in image.info:
                    if image.convert('RGBA').getchannel('A').getextrema() != (255, 255):
                        raise MediaReject('NONOPAQUE_ALPHA_REQUIRES_EXPLICIT_PRESENTATION_POLICY')
                if mode == 'RGB':
                    rendered, rendered_format, policy = payload, fmt, 'ORIGINAL_ENCODED_BYTES'
                else:
                    buffer = io.BytesIO()
                    image.convert('RGB').save(buffer, format='PNG')
                    rendered, rendered_format, policy = buffer.getvalue(), 'PNG', 'DECODE_TO_RGB_PNG_NO_RESIZE'
        return dict(source_format=fmt, source_mode=mode, dimensions=size,
                    materialized_format=rendered_format, policy=policy), rendered
    except MediaReject:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise MediaReject(f'IMAGE_DECODE_FAILED:{type(exc).__name__}') from None


def save_exact(path, payload):
    expected = hashlib.sha256(payload).hexdigest()
    if path.exists():
        if sha(path) != expected: raise RuntimeError(f'EXISTING_RECOVERY_FILE_HASH_MISMATCH:{path}')
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix+'.part')
        with temporary.open('wb') as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    return expected


def recover_image(output, locator, payload, provenance):
    meta, rendered = decode_rgb(payload)
    suffixes = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp', 'BMP': '.bmp', 'TIFF': '.tif'}
    source_hash = hashlib.sha256(payload).hexdigest()
    source = output/'source_images'/(source_hash+suffixes[meta['source_format']])
    save_exact(source, payload)
    materialized = source
    if rendered != payload:
        digest = hashlib.sha256(rendered).hexdigest()
        materialized = output/'rgb_images'/(digest+'.png')
        save_exact(materialized, rendered)
    return dict(locator=locator, status='PASS', identity_status='VERIFIED',
        # Legacy manifest field is a path alias, not an encoding assertion.
        materialized_jpg=str(materialized), materialized_sha256=hashlib.sha256(rendered).hexdigest(),
        materialized_format=meta['materialized_format'], bytes=len(rendered), dimensions=meta['dimensions'],
        source_file=str(source), source_sha256=source_hash, source_format=meta['source_format'],
        source_mode=meta['source_mode'], provenance=dict(provenance, member=locator,
            materialization_policy=meta['policy'], source_sha256=source_hash))


def bounded_members(archive):
    """Streaming extraction must not retain millions of unused TarInfo records."""
    for member in archive:
        yield member
        archive.members.clear()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--archive-root', type=Path, required=True)
    p.add_argument('--checksum-manifest', type=Path, required=True)
    p.add_argument('--requirements', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--seed', type=int, default=20260905)
    p.add_argument('--limit', type=int, help='Pilot: stop after this many distinct required members; never publish as complete')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    a = p.parse_args()
    if a.dry_run:
        print(json.dumps(dict(status='PLANNED', network=False, archive_parts=18, source_revision=REVISION,
                              output=str(a.output), actual_encoding_detection=True)))
        return
    a.output.mkdir(parents=True, exist_ok=True)
    config = {k:str(v) if isinstance(v, Path) else v for k,v in vars(a).items()}
    inputs = {str(path):sha(path) for path in (a.requirements, a.checksum_manifest)}
    if (a.output/'report.json').exists():
        prior = json.loads((a.output/'report.json').read_text())
        if (a.resume and prior.get('status') == 'COMPLETE' and prior['input_hashes'] == inputs
                and all(sha(path) == digest for path,digest in prior['output_hashes'].items())
                and all(sha(row['materialized_jpg']) == row['materialized_sha256'] for row in load(a.output/'assets.jsonl'))):
            print(json.dumps(prior)); return
        raise FileExistsError('EXISTING_RESULT_NOT_RESUMABLE_USE_NEW_OUTPUT_VERSION')
    write(a.output/'config_snapshot.json', config)
    progress = dict(status='VERIFYING_LOCAL_ARCHIVES', run_id=a.run_id, seed=a.seed,
        job_id=os.environ.get('SLURM_JOB_ID'), source_revision=REVISION, code_sha256=sha(__file__),
        code_commit='NO_GIT_REPOSITORY_AVAILABLE', config=config, input_hashes=inputs,
        verified_parts=0, total_parts=18, recovered_frames=0, failed_frames=0,
        code_dependencies={str(Path(__file__).with_name(n)):sha(Path(__file__).with_name(n))
                           for n in ('common.py', 'recover_official_rgbd.py')})
    write(a.output/'progress.json', progress)
    assets = {}; rejected = {}; seen = set(); formats = collections.Counter()
    try:
        manifest = {}
        for line in a.checksum_manifest.read_text().splitlines():
            match = re.fullmatch(r'([0-9a-f]{64})\s+(spar-rgbd-\d{2}\.tar\.gz)', line)
            if not match: raise ValueError('INVALID_OFFICIAL_CHECKSUM_MANIFEST')
            digest, name = match.groups()
            if name in manifest: raise ValueError('DUPLICATE_CHECKSUM_PART')
            manifest[name] = digest
        if set(manifest) != {f'spar-rgbd-{i:02d}.tar.gz' for i in range(18)}:
            raise ValueError('EXPECTED_EXACTLY_18_PINNED_OFFICIAL_PARTS')
        verified = []
        for name, digest in sorted(manifest.items()):
            path = a.archive_root/name
            if sha(path) != digest: raise ValueError(f'LOCAL_ARCHIVE_SHA256_MISMATCH:{name}')
            verified.append(dict(name=name, path=str(path), sha256=digest, bytes=path.stat().st_size))
            progress.update(verified_parts=len(verified), verified_archive_bytes=sum(r['bytes'] for r in verified))
            write(a.output/'progress.json', progress)
            print(json.dumps(dict(event='LOCAL_ARCHIVE_VERIFIED', part=name)), flush=True)
        write(a.output/'verified_parts.json', verified)
        parts_hash = sha(a.output/'verified_parts.json')
        provenance = dict(method='EXACT_OFFICIAL_SPAR_RGBD_NATIVE_MEMBER', source_repo='jasonzhango/SPAR-7M-RGBD',
            source_revision=REVISION, checksum_manifest_sha256=inputs[str(a.checksum_manifest)],
            verified_parts=str(a.output/'verified_parts.json'), verified_parts_sha256=parts_hash,
            identity_policy='Exact released native locator only; no guessed frame ID or nearest neighbor')
        wanted = {r['locator'] for r in load(a.requirements)}
        progress.update(status='SELECTIVE_EXTRACTION', requested_frames=len(wanted))
        write(a.output/'progress.json', progress)
        last_checkpoint = time.monotonic(); member_count = 0
        with ConcatenatedParts([a.archive_root/n for n in sorted(manifest)]) as source:
            with tarfile.open(fileobj=source, mode='r|gz', bufsize=4*1024*1024) as archive:
                for member in bounded_members(archive):
                    member_count += 1
                    loc = member.name.removeprefix('./')
                    if loc in wanted:
                        seen.add(loc)
                        try:
                            if not member.isfile() or not 0 < member.size <= 20*1024*1024:
                                raise MediaReject('REQUIRED_MEMBER_NOT_REGULAR_OR_SIZE_UNSAFE')
                            payload = archive.extractfile(member).read()
                            row = recover_image(a.output, loc, payload, provenance)
                            if loc in assets and assets[loc]['source_sha256'] != row['source_sha256']:
                                raise MediaReject('CONFLICTING_DUPLICATE_NATIVE_LOCATOR')
                            if loc not in rejected: assets[loc] = row
                        except MediaReject as exc:
                            assets.pop(loc, None)
                            rejected[loc] = dict(locator=loc, reject_code=str(exc), source_member=member.name)
                            print(json.dumps(dict(event='EXPLICIT_IMAGE_REJECT', **rejected[loc])), flush=True)
                        if a.limit is not None and len(seen) >= a.limit: break
                    if time.monotonic()-last_checkpoint >= 20 or member_count % 10000 == 0:
                        formats = collections.Counter(r['source_format'] for r in assets.values())
                        progress.update(recovered_frames=len(assets), failed_frames=len(rejected),
                            archive_members_seen=member_count, compressed_bytes_read=source.total_read,
                            source_format_counts=dict(formats), by_dataset=dict(collections.Counter(r['locator'].split('/')[1] for r in assets.values())))
                        write(a.output/'assets_checkpoint.jsonl', sorted(assets.values(), key=lambda r:r['locator']), jsonl=True)
                        write(a.output/'progress.json', progress)
                        print(json.dumps({k:progress[k] for k in ('status','recovered_frames','failed_frames','compressed_bytes_read','source_format_counts')}), flush=True)
                        last_checkpoint = time.monotonic()
        rows = sorted(assets.values(), key=lambda r:r['locator'])
        for loc in sorted(wanted-seen):
            rejected[loc] = dict(locator=loc, reject_code='NOT_SCANNED_PILOT_LIMIT' if a.limit else 'EXACT_NATIVE_RGB_MEMBER_ABSENT')
        write(a.output/'assets.jsonl', rows, jsonl=True)
        write(a.output/'unresolved.jsonl', sorted(rejected.values(), key=lambda r:r['locator']), jsonl=True)
        if set(assets) & set(rejected) or set(assets) | set(rejected) != wanted:
            raise ValueError('RECOVERY_LOCATOR_ACCOUNTING_MISMATCH')
        report = dict(progress, status='PILOT_COMPLETE' if a.limit is not None else 'COMPLETE',
            recovered_frames=len(rows), missing_frames=len(rejected), failed_frames=len(rejected),
            archive_members_seen=member_count, source_format_counts=dict(collections.Counter(r['source_format'] for r in rows)),
            by_dataset=dict(collections.Counter(r['locator'].split('/')[1] for r in rows)),
            reject_codes=dict(collections.Counter(r['reject_code'] for r in rejected.values())),
            output_hashes={str(a.output/n):sha(a.output/n) for n in ('assets.jsonl','unresolved.jsonl','verified_parts.json','config_snapshot.json')})
        write(a.output/'report.json', report); write(a.output/'progress.json', report)
        print(json.dumps(report), flush=True)
    except Exception as exc:
        progress.update(status='FAILED', error_type=type(exc).__name__, error=str(exc), recovered_frames=len(assets))
        write(a.output/'progress.json', progress)
        raise


if __name__ == '__main__': main()
