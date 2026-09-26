"""Freeze a finite set of existing prediction prefixes once, and reuse on resume."""
from common import *

def frozen_predictions(root, base, models):
    directory = Path(root) / 'raw/E0_existing_snapshot'
    lockpath = directory / 'SNAPSHOT_LOCK.json'
    if lockpath.exists():
        lock = load(lockpath)
        if lock['models'] != models or lock['base'] != str(base): raise ValueError('SNAPSHOT_SCOPE_MISMATCH')
        for ref in lock['files']:
            if sha(ref['snapshot_path']) != ref['snapshot_sha256']: raise ValueError('FROZEN_SNAPSHOT_CHANGED')
        return lock
    refs = []
    for model in models:
        for path in sorted((Path(base) / model / 'full').glob('predictions_*.jsonl')):
            snapshot = directory / model / path.name
            metapath = snapshot.with_suffix('.meta.json')
            if metapath.exists():
                meta = load(metapath)
                if sha(snapshot) != meta['snapshot_sha256']: raise ValueError('PARTIAL_SNAPSHOT_CHANGED')
            else:
                if snapshot.exists(): raise ValueError('ORPHAN_SNAPSHOT_PRESERVE_AND_INSPECT:' + str(snapshot))
                stat = path.stat(); captured_at = now()
                with path.open('rb') as f: data = f.read(stat.st_size)
                if len(data) != stat.st_size: raise ValueError('SOURCE_TRUNCATED_DURING_SNAPSHOT')
                tail = b''
                if data and not data.endswith(b'\n'):
                    cut = data.rfind(b'\n') + 1; data, tail = data[:cut], data[cut:]
                # Raw invalid model responses remain; only an incomplete JSONL write tail is excluded.
                save(snapshot, data.decode('utf-8'), 'text')
                meta = dict(model_id=model, path=str(path), snapshot_path=str(snapshot), captured_at=captured_at,
                            captured_bytes=stat.st_size, complete_bytes=len(data), incomplete_tail_bytes=len(tail),
                            snapshot_sha256=hashlib.sha256(data).hexdigest())
                if tail:
                    save(snapshot.with_suffix('.incomplete_tail.json'), dict(hex=tail.hex(), captured_at=captured_at))
                save(metapath, meta)
            refs.append(meta)
    lock = dict(status='FROZEN_EXISTING_PREFIXES_NOT_NEW_INFERENCE', created_at=now(), base=str(base), models=models, files=refs,
                incomplete_tails_not_scored_as_model_responses=True, resume_policy='REUSE_ONLY_NO_REFRESH')
    save(lockpath, lock)
    return lock
