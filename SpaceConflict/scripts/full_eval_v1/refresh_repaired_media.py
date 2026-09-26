"""Snapshot verified recoveries, rebuild blind inputs, and safely promote before inference."""
import argparse
import collections
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import zlib
from pathlib import Path
from PIL import Image
from common import load, sha, write


def freeze_json(path, destination):
    if not destination.exists():
        payload = path.read_bytes()  # Producer checkpoints use atomic replacement.
        json.loads(payload)
        destination.write_bytes(payload)
    return json.loads(destination.read_text())


def verified_s3d(row, bundle):
    if row.get('status') != 'PASS' or row.get('withheld'):
        return None
    for prefix in ('source', 'materialized'):
        path = Path(row['source_png' if prefix == 'source' else 'materialized_jpg']).resolve()
        if bundle.resolve() not in path.parents:
            raise ValueError('RECOVERY_OUTSIDE_PERSISTENT_BUNDLE')
        payload = path.read_bytes()
        if len(payload) != row[prefix + '_size'] or hashlib.sha256(payload).hexdigest() != row[prefix + '_sha256']:
            raise ValueError('RECOVERY_FILE_HASH_OR_SIZE_MISMATCH')
        if prefix == 'source' and f'{zlib.crc32(payload) & 0xffffffff:08x}' != row['source_crc32']:
            raise ValueError('RECOVERY_SOURCE_CRC_MISMATCH')
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
    return dict(row, identity_status='VERIFIED', provenance=dict(
        method='EXACT_OFFICIAL_STRUCTURED3D_MEMBER_CRC_AND_IMAGE_HASH',
        source_url=row['source_url'], source_member=row['source_member'],
        source_crc32=row['source_crc32'], source_sha256=row['source_sha256']))


def counts(rows):
    return dict(collections.Counter(r['level'] for r in rows))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--repair-root', type=Path, required=True)
    p.add_argument('--rgbd-root', type=Path, help='Completed versioned official RGBD recovery directory')
    p.add_argument('--run-id', required=True)
    p.add_argument('--seed', type=int, default=20260905)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--limit', type=int)
    p.add_argument('--promote', action='store_true')
    a = p.parse_args()
    if a.limit is not None: raise ValueError('FULL_RELEASE_REFRESH_DOES_NOT_ALLOW_LIMIT')
    if a.dry_run:
        print('Snapshot completed assets only; preserve gold/splits; full media validation; optional promotion.')
        return
    run = a.run_root
    stage = run/'preparation_revisions'/a.run_id
    if (stage/'refresh_report.json').exists():
        previous = json.loads((stage/'refresh_report.json').read_text())
        if a.resume and previous['status'] == 'PASS':
            print(json.dumps(previous)); return
        raise FileExistsError(stage/'refresh_report.json')
    stage.mkdir(parents=True, exist_ok=True)
    acq = a.bundle/'upstream_media/spar7m_acquisition'
    # The baseline is preserved before any output changes. Never modify release files.
    baseline = stage/'before'
    baseline.mkdir(exist_ok=True)
    for name in ('inventory.json', 'requests.jsonl', 'smoke.jsonl', 'private_gold.jsonl',
                 'unavailable.jsonl', 'media_audit.jsonl', 'rubric.json', 'preparation_progress.json'):
        if not (baseline/name).exists(): shutil.copy2(run/name, baseline/name)
    before = json.loads((baseline/'inventory.json').read_text())
    for path, digest in before['output_hashes'].items():
        if sha(baseline/Path(path).name) != digest: raise ValueError('BASELINE_SNAPSHOT_HASH_MISMATCH')
    report = freeze_json(a.repair_root/'structured3d_report.json', stage/'structured3d_snapshot.json')
    old_s3d = json.loads((acq/'alternative_sources/validation/structured3d/full_extract_report.json').read_text())
    existing = {r['locator'] for r in old_s3d['completed'] if not r['withheld']}
    assets_path = acq/'integration_v1_20260905/assets.jsonl'
    assets = {r['locator']: r for r in load(assets_path)}
    extras = []
    for row in report['completed']:
        if row['locator'] in existing or row['locator'] in assets: continue
        recovered = verified_s3d(row, a.bundle)
        if recovered: extras.append(recovered)
    bench_path = a.repair_root/'bench_unmarked/assets.jsonl'
    if bench_path.exists():
        for row in load(bench_path):
            if row['locator'] not in existing and row['locator'] not in assets:
                extras.append(row)
    for row in extras:
        if row['locator'] in assets:
            if assets[row['locator']]['materialized_sha256'] != row['materialized_sha256']:
                raise ValueError('CONFLICTING_RECOVERED_LOCATOR')
        else: assets[row['locator']] = row
    rgbd_root = a.rgbd_root or acq/'rgbd_recovery_v1_20260905'
    rgbd_report = None
    if a.rgbd_root and not (rgbd_root/'report.json').exists():
        raise ValueError('REQUESTED_OFFICIAL_RGBD_RECOVERY_REPORT_MISSING')
    if (rgbd_root/'report.json').exists():
        rgbd_report = freeze_json(rgbd_root/'report.json', stage/'official_rgbd_snapshot.json')
        if rgbd_report.get('status') != 'COMPLETE': raise ValueError('OFFICIAL_RGBD_RECOVERY_NOT_COMPLETE')
        for path, digest in rgbd_report['output_hashes'].items():
            if sha(path) != digest: raise ValueError('OFFICIAL_RGBD_RECOVERY_MANIFEST_HASH_MISMATCH')
        for row in load(rgbd_root/'assets.jsonl'):
            # Keep already verified inputs byte-identical; RGBD fills gaps only.
            if row['locator'] not in existing and row['locator'] not in assets:
                assets[row['locator']] = row
    write(stage/'assets.jsonl', sorted(assets.values(), key=lambda r:r['locator']), jsonl=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name('prepare.py')),
        '--bundle', str(a.bundle), '--project', str(a.project), '--run-root', str(stage),
        '--run-id', a.run_id, '--seed', str(a.seed), '--resume',
        '--spar-assets', str(stage/'assets.jsonl'), '--checkpoint-source', str(run/'media_checkpoint.jsonl')], check=True)
    after = json.loads((stage/'inventory.json').read_text())
    if sha(stage/'private_gold.jsonl') != sha(baseline/'private_gold.jsonl'):
        raise ValueError('GOLD_CHANGED_DURING_MEDIA_ONLY_REPAIR')
    old_rows = {r['sample_id']: r for r in load(baseline/'requests.jsonl')}
    new_rows = {r['sample_id']: r for r in load(stage/'requests.jsonl')}
    if not old_rows.keys() <= new_rows.keys(): raise ValueError('PREVIOUSLY_AVAILABLE_INPUT_LOST')
    if any(new_rows[k] != v for k,v in old_rows.items()): raise ValueError('PREVIOUSLY_AVAILABLE_INPUT_CHANGED')
    if len(new_rows) != after['eligible'] or after['eligible'] + after['unavailable'] != 24196:
        raise ValueError('FULL_RELEASE_ACCOUNTING_MISMATCH')
    new_ids = sorted(new_rows.keys() - old_rows.keys())
    write(stage/'recovered_sample_ids.json', new_ids)
    unavailable = load(stage/'unavailable.jsonl')
    by_base = collections.Counter()
    for row in unavailable:
        found = next((s for s in ('scannet', 'scannetpp', 'structured3d')
                      if 'spar/'+s+'/' in row.get('reject_code', '')), 'other')
        by_base[found] += 1
    result = dict(status='PASS', promoted=False, run_id=a.run_id,
        seed=a.seed, code_commit='NO_GIT_REPOSITORY_AVAILABLE',
        source_revision='frozen SpaceConflict release plus verified source assets',
        config={k:str(v) if isinstance(v, Path) else v for k,v in vars(a).items()},
        before_eligible=before['eligible'], eligible=after['eligible'], newly_available=len(new_ids),
        unavailable=after['unavailable'], release_total=after['release_total'],
        by_level=after['by_level'], unavailable_by_base=dict(by_base),
        source_download_status_at_snapshot=report['status'],
        source_completed_frames_at_snapshot=report['passed'], source_pending_frames_at_snapshot=report['pending'],
        code_sha256=sha(__file__), unchanged_private_gold_sha256=sha(stage/'private_gold.jsonl'),
        combined_assets_sha256=sha(stage/'assets.jsonl'), source_snapshot_sha256=sha(stage/'structured3d_snapshot.json'),
        official_rgbd_recovered_frames=(rgbd_report or {}).get('recovered_frames', 0),
        scope='single model inputs, not pairs or image files', job_id=os.environ.get('SLURM_JOB_ID'))
    if a.promote:
        # Root inputs must not change after any GPU output has been produced.
        for scope in ('smoke', 'full'):
            if any((run/scope).glob('predictions_*.jsonl')):
                raise ValueError('INFERENCE_ALREADY_STARTED_CREATE_A_NEW_RUN')
        marker = run/'MEDIA_REFRESH_IN_PROGRESS.json'
        write(marker, dict(stage=str(stage), status='PROMOTING'))
        for path in after['output_hashes']:
            source = Path(path)
            tmp = run/(source.name+'.refresh_part')
            shutil.copy2(source, tmp)
            os.replace(tmp, run/source.name)
        for name in ('media_checkpoint.jsonl', 'preparation_progress.json'):
            shutil.copy2(stage/name, run/name)
        promoted = dict(after, output_hashes={str(run/Path(path).name): digest
            for path,digest in after['output_hashes'].items()}, preparation_revision=str(stage))
        write(run/'inventory.json', promoted)
        result['promoted'] = True
        write(marker, dict(stage=str(stage), status='COMPLETE'))
    write(stage/'refresh_report.json', result)
    if a.promote: write(run/'latest_media_repair_report.json', result)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__': main()
