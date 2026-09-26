"""Download pinned official RGBD parts, verify SHA256, extract only exact required RGB locators."""
import argparse
import collections
import concurrent.futures
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import time
from pathlib import Path
import requests
from PIL import Image
from common import load, sha, write

REVISION = '60ef8b2df6430524da86757dec86dcbc55708a41'
ROOT = 'https://huggingface.co/datasets/jasonzhango/SPAR-7M-RGBD'


def get_response(method, url, **kwargs):
    for attempt in range(4):
        response = requests.request(method, url, timeout=(20, 90), **kwargs)
        if response.status_code in (429, 500, 502, 503, 504):
            retry = response.headers.get('Retry-After', '')
            wait = int(retry) if retry.isdigit() else (300 if response.status_code == 429 else 10 * (attempt + 1))
            print(json.dumps(dict(event='HTTP_BACKOFF', status=response.status_code, seconds=wait)), flush=True)
            response.close()
            if attempt == 3: raise RuntimeError('REMOTE_HTTP_RETRIES_EXHAUSTED')
            time.sleep(wait)
            continue
        if response.status_code >= 400:
            status = response.status_code
            response.close()
            raise RuntimeError(f'REMOTE_HTTP_STATUS_{status}')
        return response


class ConcatenatedParts(io.RawIOBase):
    def __init__(self, paths):
        super().__init__()
        self.paths = iter(paths)
        self.current = None
        self.total_read = 0

    def readable(self): return True

    def read(self, size=-1):
        if size < 0: raise ValueError('UNBOUNDED_ARCHIVE_READ_FORBIDDEN')
        pieces = []
        remaining = size
        while remaining:
            if self.current is None:
                path = next(self.paths, None)
                if path is None: break
                self.current = path.open('rb')
            chunk = self.current.read(remaining)
            if not chunk:
                self.current.close()
                self.current = None
                continue
            pieces.append(chunk)
            remaining -= len(chunk)
            self.total_read += len(chunk)
        return b''.join(pieces)

    def close(self):
        if self.current is not None: self.current.close()
        super().close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--requirements', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--seed', type=int, default=20260905)
    p.add_argument('--limit', type=int)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--resume', action='store_true')
    a = p.parse_args()
    if a.dry_run:
        print(json.dumps(dict(status='PLANNED', source_revision=REVISION, workers=a.workers,
                              max_archive_bytes=18*10*1024**3, selective_extraction=True)))
        return
    a.output.mkdir(parents=True, exist_ok=True)
    progress = dict(status='STARTING', run_id=a.run_id, seed=a.seed, source_revision=REVISION,
                    job_id=os.environ.get('SLURM_JOB_ID'), code_sha256=sha(__file__),
                    code_commit='NO_GIT_REPOSITORY_AVAILABLE',
                    config={k:str(v) if isinstance(v, Path) else v for k,v in vars(a).items()},
                    input_hashes={str(a.requirements):sha(a.requirements)}, recovered_frames=0, failure_count=0)
    write(a.output/'progress.json', progress)
    try:
        manifest_path = a.output/'official_sha256.txt'
        if not manifest_path.exists():
            response = get_response('GET', f'{ROOT}/raw/{REVISION}/spar-rgbd-sha256.txt')
            if len(response.content) > 20000: raise ValueError('UNEXPECTED_CHECKSUM_MANIFEST_SIZE')
            manifest_path.write_bytes(response.content)
            response.close()
        manifest = {}
        for line in manifest_path.read_text().splitlines():
            match = re.fullmatch(r'([0-9a-f]{64})\s+(spar-rgbd-\d{2}\.tar\.gz)', line)
            if not match: raise ValueError('INVALID_OFFICIAL_CHECKSUM_MANIFEST')
            digest, name = match.groups()
            if name in manifest: raise ValueError('DUPLICATE_OFFICIAL_ARCHIVE_PART')
            manifest[name] = digest
        if set(manifest) != {f'spar-rgbd-{i:02d}.tar.gz' for i in range(18)}:
            raise ValueError('OFFICIAL_PART_SET_MISMATCH')
        archive_dir = a.output/'archives'
        archive_dir.mkdir(exist_ok=True)
        downloaded = []

        def download(item):
            name, expected = item
            path = archive_dir/name
            if path.exists():
                if sha(path) != expected: raise ValueError(f'EXISTING_ARCHIVE_HASH_MISMATCH:{name}')
                return dict(name=name, bytes=path.stat().st_size, sha256=expected, reused=True)
            url = f'{ROOT}/resolve/{REVISION}/{name}'
            head = get_response('HEAD', url, allow_redirects=False)
            if head.headers.get('X-Linked-Etag', '').strip('"') != expected:
                raise ValueError(f'PINNED_HUB_CHECKSUM_MISMATCH:{name}')
            total = int(head.headers['X-Linked-Size'])
            head.close()
            if not 0 < total <= 10*1024**3: raise ValueError('ARCHIVE_PART_SIZE_OUTSIDE_EXPECTED_BOUND')
            partial = path.with_suffix(path.suffix+'.part')
            for attempt in range(4):
                offset = partial.stat().st_size if partial.exists() else 0
                if offset > total: raise ValueError('PARTIAL_DOWNLOAD_LARGER_THAN_SOURCE')
                if offset == total: break
                try:
                    response = get_response('GET', url, headers={'Range': f'bytes={offset}-', 'Accept-Encoding': 'identity'}, stream=True)
                    if response.status_code == 206:
                        if response.headers.get('Content-Range') != f'bytes {offset}-{total-1}/{total}':
                            raise ValueError('INVALID_RESUME_CONTENT_RANGE')
                    elif not (response.status_code == 200 and offset == 0):
                        raise ValueError('SERVER_DID_NOT_HONOR_RESUME_RANGE')
                    with partial.open('ab') as f:
                        for chunk in response.iter_content(4*1024*1024):
                            offset += len(chunk)
                            if offset > total: raise ValueError('DOWNLOAD_EXCEEDS_VERIFIED_SIZE')
                            f.write(chunk)
                        f.flush(); os.fsync(f.fileno())
                    response.close()
                    if offset != total: raise OSError('TRUNCATED_ARCHIVE_BODY')
                    break
                except (requests.RequestException, OSError) as exc:
                    print(json.dumps(dict(event='TRANSFER_RETRY', part=name, attempt=attempt+1,
                                          exception=type(exc).__name__)), flush=True)
                    if attempt == 3: raise RuntimeError(f'DOWNLOAD_INCOMPLETE:{name}') from None
                    time.sleep(10*(attempt+1))
            if sha(partial) != expected: raise ValueError(f'DOWNLOADED_ARCHIVE_SHA256_MISMATCH:{name}')
            os.replace(partial, path)
            result = dict(name=name, bytes=total, sha256=expected, reused=False)
            print(json.dumps(dict(event='OFFICIAL_ARCHIVE_VERIFIED', **result)), flush=True)
            return result

        progress.update(status='DOWNLOADING', total_parts=18, verified_parts=0)
        write(a.output/'progress.json', progress)
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
            futures = [pool.submit(download, item) for item in sorted(manifest.items())]
            for future in concurrent.futures.as_completed(futures):
                downloaded.append(future.result())
                progress.update(verified_parts=len(downloaded), verified_archive_bytes=sum(x['bytes'] for x in downloaded), parts=downloaded)
                write(a.output/'progress.json', progress)
        wanted = {r['locator'] for r in load(a.requirements)}
        if a.limit is not None: wanted = set(sorted(wanted)[:a.limit])
        progress.update(status='SELECTIVE_EXTRACTION', requested_frames=len(wanted), recovered_frames=0)
        write(a.output/'progress.json', progress)
        images_dir = a.output/'images'
        images_dir.mkdir(exist_ok=True)
        assets = {}; member_count = 0
        with ConcatenatedParts([archive_dir/n for n in sorted(manifest)]) as source:
            with tarfile.open(fileobj=source, mode='r|gz', bufsize=1024*1024) as archive:
                for member in archive:
                    member_count += 1
                    name = member.name.removeprefix('./')
                    if name in wanted:
                        if not member.isfile() or not 0 < member.size <= 20*1024*1024:
                            raise ValueError('REQUIRED_RGB_MEMBER_NOT_REGULAR_OR_OVERSIZE')
                        payload = archive.extractfile(member).read()
                        digest = hashlib.sha256(payload).hexdigest()
                        with Image.open(io.BytesIO(payload)) as image:
                            image.load()
                            if image.format != 'JPEG': raise ValueError('OFFICIAL_IMAGE_COLOR_NOT_JPEG')
                            dimensions = image.size
                        if name in assets and assets[name]['materialized_sha256'] != digest:
                            raise ValueError('CONFLICTING_DUPLICATE_NATIVE_RGB_LOCATOR')
                        target = images_dir/(digest+'.jpg')
                        if target.exists():
                            if sha(target) != digest: raise ValueError('EXISTING_EXTRACTED_RGB_HASH_MISMATCH')
                        else: target.write_bytes(payload)
                        assets[name] = dict(locator=name, status='PASS', identity_status='VERIFIED',
                            materialized_jpg=str(target), materialized_sha256=digest, bytes=len(payload), dimensions=dimensions,
                            provenance=dict(method='EXACT_OFFICIAL_SPAR_RGBD_NATIVE_MEMBER', source_repo='jasonzhango/SPAR-7M-RGBD',
                                source_revision=REVISION, member=name, official_checksum_manifest=str(manifest_path),
                                official_checksum_manifest_sha256=sha(manifest_path),
                                verified_archive_manifest=str(a.output/'verified_parts.json'),
                                relation_to_frozen_release='Native spar/dataset/images/scene/image_color/frame locator; no frame renumbering or nearest-neighbor matching'))
                    if member_count % 10000 == 0:
                        progress.update(recovered_frames=len(assets), archive_members_seen=member_count, compressed_bytes_read=source.total_read)
                        write(a.output/'progress.json', progress)
                        print(json.dumps({k:progress[k] for k in ('status','recovered_frames','archive_members_seen','compressed_bytes_read')}), flush=True)
        write(a.output/'verified_parts.json', sorted(downloaded, key=lambda x:x['name']))
        rows = sorted(assets.values(), key=lambda x:x['locator'])
        missing = sorted(wanted - assets.keys())
        write(a.output/'assets.jsonl', rows, jsonl=True)
        write(a.output/'missing_locators.json', missing)
        report = dict(progress, status='COMPLETE', requested_frames=len(wanted), recovered_frames=len(rows), missing_frames=len(missing),
                      by_dataset=dict(collections.Counter(x['locator'].split('/')[1] for x in rows)),
                      input_hashes={str(a.requirements):sha(a.requirements), str(manifest_path):sha(manifest_path)},
                      output_hashes={str(a.output/n):sha(a.output/n) for n in ('assets.jsonl','missing_locators.json','verified_parts.json')})
        write(a.output/'report.json', report)
        write(a.output/'progress.json', report)
        print(json.dumps(report), flush=True)
    except Exception as exc:
        progress.update(status='FAILED', failure_count=1, error_type=type(exc).__name__, error=str(exc).split('https://')[0])
        write(a.output/'progress.json', progress)
        raise


if __name__ == '__main__': main()
