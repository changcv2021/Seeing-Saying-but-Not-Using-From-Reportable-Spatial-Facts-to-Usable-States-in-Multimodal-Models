"""B0 namespace; reuse read-only A.1 IO and actual processor, not its gold/scorer."""
import sys
from pathlib import Path
CODE = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE.parent.parent/'src'))
A1CODE = CODE.parent / 'state_binding_phase_a1/core_execution_v3'
sys.path.insert(0, str(A1CODE))
from v3common import (argparse, csv, hashlib, json, os, socket, digest, sha, load,
                      rows, csvrows, save, csvsave, entry, now, compute,
                      check_entries, import_file)


def arguments(description):
    p = argparse.ArgumentParser(description=description)
    p.add_argument('--config', type=Path, default=CODE/'config.json')
    p.add_argument('--run-id', default='b0_20260908_r1')
    p.add_argument('--seed', type=int, default=20260908)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--limit', type=int)
    return p


def setup(a):
    c = load(a.config)
    if (a.run_id, a.seed) != (c['run_id'], c['seed']) or a.limit is not None:
        raise ValueError('RUN_SEED_LIMIT_MISMATCH_USE_FROZEN_PANEL')
    root = Path(c['root'])
    if root.parent.name != 'spaceconflict_b0' or root.name != c['run_id']:
        raise ValueError('NEW_B0_NAMESPACE_REQUIRED')
    return c, root


def cluster(world):
    if world.startswith('hypo3d:'):
        s = world.split(':', 1)[1]
        if s.startswith('scene'): return 'scannet:' + s
        if len(s) == 36 and s.count('-') == 4: return '3rscan:' + s
    return world


def dependency_files(c):
    files = list(CODE.glob('*.py')) + list(CODE.glob('*.sh')) + [CODE/'config.json',CODE/'analysis_rules.json']
    files += [A1CODE/x for x in ['v3common.py','pipeline_v3.py','contracts_v3.py']]
    files += [A1CODE/'analysis_v1/cluster_stats.py']
    files += [A1CODE.parent/'src'/x for x in ['scorer.py','interfaces.py','common.py']]
    files += [A1CODE.parent/'format_repair_v2/format_adapter_v2.py']
    files += [CODE.parent.parent/'src/spaceconflict/mllm_l4.py']
    files += [Path(c['campaign'])/'code'/x for x in ['protocol.py','vision_process_frozen.py']]
    return [entry(p) for p in sorted(set(files))]


def union_csv(path, records):
    import io
    records = list(records)
    fields = list(dict.fromkeys(k for r in records for k in r)) or ['status']
    buf=io.StringIO(newline='')
    writer=csv.DictWriter(buf,fieldnames=fields,lineterminator='\n'); writer.writeheader()
    for r in records:
        writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()})
    # Stable logical newlines; existing CSV bytes are not rewritten on resume.
    save(path,buf.getvalue(),'text',frozen=True)
