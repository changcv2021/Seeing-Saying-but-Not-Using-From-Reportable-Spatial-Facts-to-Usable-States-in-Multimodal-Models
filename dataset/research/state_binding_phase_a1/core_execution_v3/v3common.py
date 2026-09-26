"""Versioned namespace and IO. No model, source-gold, or prediction reads on import."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
import socket
import sys
from pathlib import Path
from datetime import datetime, timezone

CODE = Path(__file__).resolve().parent


def digest(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def rows(path):
    with Path(path).open(encoding='utf-8-sig') as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def csvrows(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def save(path, obj, kind='json', frozen=True):
    path = Path(path)
    if kind == 'jsonl':
        text = ''.join(json.dumps(x, ensure_ascii=False, sort_keys=True) + '\n' for x in obj)
    elif kind == 'text':
        text = obj
    else:
        text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    if frozen and path.exists():
        if path.read_text() != text:
            raise ValueError('FROZEN_OUTPUT_CHANGED:' + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.{os.getpid()}.part')
    tmp.write_text(text)
    tmp.replace(path)


def csvsave(path, records, fields=None, frozen=True):
    import io
    records = list(records)
    buf = io.StringIO(newline='')
    fields = fields or list(records[0])
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for r in records:
        w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in r.items()})
    save(path, buf.getvalue(), 'text', frozen)


def entry(path):
    p = Path(path)
    return dict(path=str(p), bytes=p.stat().st_size, sha256=sha(p))


def now():
    return datetime.now(timezone.utc).isoformat()


def compute():
    if not os.environ.get('SLURM_JOB_ID') or socket.gethostname().startswith('login'):
        raise RuntimeError('SLURM_COMPUTE_NODE_REQUIRED')


def arguments(description):
    p = argparse.ArgumentParser(description=description)
    p.add_argument('--config', type=Path, default=CODE/'config.json')
    p.add_argument('--run-id', default='phase_a1_20260907_core_v3')
    p.add_argument('--seed', type=int, default=20260907)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--limit', type=int)
    return p


def setup(a):
    c = load(a.config)
    if (a.run_id, a.seed) != (c['run_id'], c['seed']) or a.limit is not None:
        raise ValueError('RUN_SEED_LIMIT_MISMATCH')
    root = Path(c['root'])
    if any(root == Path(c[k]) for k in ['phase_a_root', 'old_a1_root', 'format_v2_root']):
        raise ValueError('HISTORY_NAMESPACE_FORBIDDEN')
    return c, root


def import_file(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def code_entries(c):
    files = list(CODE.glob('*.py')) + list(CODE.glob('*.sh')) + [CODE/'config.json']
    files += [Path(c['old_a1_code'])/'src'/x for x in ['common.py','interfaces.py','scorer.py']]
    files += [Path(c['old_a1_code'])/'format_repair_v2/format_adapter_v2.py']
    files += [Path(c['campaign'])/'code'/x for x in ['protocol.py','vision_process_frozen.py']]
    files += [Path(c['package'])/'scripts/build_semantic_bridge.py']
    return [entry(p) for p in sorted(set(files))]


def check_entries(records):
    changed = []
    for r in records:
        p = Path(r['path'])
        if not p.is_file() or p.stat().st_size != r['bytes'] or sha(p) != r['sha256']:
            changed.append(str(p))
    if changed:
        raise ValueError('HASH_MISMATCH:' + json.dumps(changed[:20]))
    return len(records)
