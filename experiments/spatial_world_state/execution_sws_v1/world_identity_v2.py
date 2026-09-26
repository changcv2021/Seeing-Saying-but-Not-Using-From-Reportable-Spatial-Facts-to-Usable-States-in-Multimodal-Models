"""Read-only, exact-ID metadata repair; never infer a world from answers or pixels."""
from collections import Counter
from common import *

VERSION = 'world_identity_v2'
RELEASE_UNKNOWN_SHA = '82f62083a9c05ea9f5508ad471093d557d6a7669a8a19c0f8b53b39044f597ad'
RELEASE_MANIFEST_SHA = '63e17000eaec9d073a738b8d5687fa101bbe753c41b3400f340aad9c7490ac6a'
META_FIELDS = ('sample_id', 'global_world_id', 'level', 'dataset', 'split', 'component')

def repair_root(root):
    return Path(root) / 'repairs' / VERSION

def valid_world(w):
    return isinstance(w, str) and w == w.strip() and ':' in w and all(w.split(':', 1))

def unique(records, name):
    out = {}
    for row in records:
        sid = row.get('sample_id')
        if not isinstance(sid, str) or not sid:
            raise ValueError('MISSING_SAMPLE_ID:' + name)
        if sid in out:
            raise ValueError('DUPLICATE_SAMPLE_ID:' + name + ':' + sid)
        out[sid] = row
    return out

def resolve_one(meta, source, public):
    """Only exact source sample ID + scene/branch/split checks authorize recovery."""
    original = meta.get('global_world_id')
    if source is None:
        if valid_world(original):
            return original, 'ORIGINAL_METADATA'
        raise ValueError('UNRESOLVED_WORLD_ID_NO_EXACT_RELEASE_MATCH')
    if not public or meta['sample_id'] != source['sample_id'] or meta['sample_id'] != public['sample_id']:
        raise ValueError('SOURCE_SAMPLE_ID_MISMATCH')
    if meta.get('level') != 'L4' or meta.get('component') != 'unknown' or meta.get('dataset') != 'hypo3d':
        raise ValueError('SOURCE_COHORT_MISMATCH')
    w = source.get('global_world_id')
    if not valid_world(w) or w != 'hypo3d:' + str(source.get('base_scene_id')):
        raise ValueError('SOURCE_WORLD_SCENE_MISMATCH')
    for field in ('base_scene_id', 'branch_id', 'level', 'split'):
        if source.get(field) != public.get(field) or source.get(field) is None:
            raise ValueError('SOURCE_PUBLIC_METADATA_MISMATCH:' + field)
    if meta.get('split') != source['split'] or meta.get('level') != source['level']:
        raise ValueError('BASELINE_SOURCE_SPLIT_OR_LEVEL_MISMATCH')
    if original is not None and original != w:
        raise ValueError('CONFLICTING_EXISTING_WORLD_ID')
    return w, 'EXACT_RELEASE_SAMPLE_ID' if original is None else 'ORIGINAL_CROSSCHECKED_RELEASE'

def checked_overlay(c, root):
    rr = repair_root(root)
    acceptance = load(rr / 'identity_acceptance.json')
    if acceptance['status'] != 'PASS' or acceptance['unresolved_records']:
        raise ValueError('WORLD_IDENTITY_NOT_ACCEPTED')
    # Hash checks include immutable baseline input and exact release provenance.
    for ref in acceptance['immutable_inputs'] + acceptance['code_files']:
        if sha(ref['path']) != ref['sha256']:
            raise ValueError('REPAIR_FROZEN_INPUT_CHANGED:' + ref['path'])
    path = rr / 'baseline_world_metadata.jsonl'
    if sha(path) != acceptance['overlay']['sha256']:
        raise ValueError('REPAIR_OVERLAY_CHANGED')
    records = unique(rows(path), 'derived_metadata')
    if len(records) != acceptance['baseline_records'] or any(not valid_world(r['global_world_id']) for r in records.values()):
        raise ValueError('INCOMPLETE_WORLD_MAPPING')
    return records, acceptance

def tests():
    import copy
    s = dict(sample_id='u1', global_world_id='hypo3d:scene0001_00', base_scene_id='scene0001_00', branch_id='b', level='L4', split='dev')
    p = {k: s[k] for k in ('sample_id', 'base_scene_id', 'branch_id', 'level', 'split')}
    m = dict(sample_id='u1', global_world_id=None, level='L4', dataset='hypo3d', split='dev', component='unknown')
    before = copy.deepcopy((m, s, p)); count = 0
    assert resolve_one(m, s, p) == (s['global_world_id'], 'EXACT_RELEASE_SAMPLE_ID'); count += 1
    assert (m, s, p) == before; count += 1
    for w in (None, '', ' ', 7, [], 'unknown', 'hypo3d:', ':scene'):
        assert not valid_world(w); count += 1
    assert resolve_one(dict(m, global_world_id='scannet:scene0001_00'), None, None)[0] == 'scannet:scene0001_00'; count += 1
    cases = [(m, None, None), (m, s, dict(p, sample_id='u2')), (m, s, dict(p, branch_id='other')),
             (dict(m, split='test'), s, p), (dict(m, global_world_id='hypo3d:other'), s, p),
             (m, dict(s, global_world_id=None), p), (dict(m, component='binary'), s, p),
             (dict(m, global_world_id=''), s, p), (m, dict(s, base_scene_id='other'), p)]
    for args in cases:
        try: resolve_one(*args)
        except ValueError: count += 1
        else: raise AssertionError('UNSAFE_MAPPING_ACCEPTED')
    try: unique([m, m], 'fixture')
    except ValueError: count += 1
    else: raise AssertionError('DUPLICATE_ACCEPTED')
    assert cluster(s['global_world_id']) == 'scannet:scene0001_00'; count += 1
    return count

def main():
    a = arguments(__doc__).parse_args(); c, root = setup(a)
    if a.dry_run:
        print('Exact source metadata repair and regression checks only; no gold/prompt edits or inference'); return
    rr = repair_root(root)
    if (rr / 'identity_acceptance.json').exists():
        records, report = checked_overlay(c, root)
        print(json.dumps(dict(status='REUSED_FROZEN_IDENTITY_PASS', records=len(records)))); return
    test_count = tests()
    project = Path(c['project']); baseline = Path(c['baseline'])
    source = project / 'l4/v3_3/release/unknown_challenge.l4_v3.jsonl'
    public = project / 'l4/v3_3/release/model_inputs.l4_unknown_v3.jsonl'
    manifest = project / 'l4/v3_3/release/manifest.json'
    inputs = [entry(x) for x in (source, public, manifest, baseline / 'private_gold.jsonl', baseline / 'requests.jsonl', baseline / 'protocol_lock.json')]
    refs = {r['path']: r for r in inputs}
    if refs[str(source)]['sha256'] != RELEASE_UNKNOWN_SHA or refs[str(manifest)]['sha256'] != RELEASE_MANIFEST_SHA:
        raise ValueError('RELEASE_HASH_DIFFERS_FROM_DATASET_REGISTRY')
    lock = load(baseline / 'protocol_lock.json')
    for path in (baseline / 'private_gold.jsonl', baseline / 'requests.jsonl'):
        if refs[str(path)]['sha256'] != lock['files'][str(path)]:
            raise ValueError('FROZEN_BASELINE_INPUT_CHANGED:' + str(path))
    # Private release bodies are projected immediately; claim/gold/witness fields never enter the overlay.
    sources = unique((dict({k:r.get(k) for k in ('sample_id', 'global_world_id', 'base_scene_id', 'branch_id', 'level', 'split')}, source_line=n)
                      for n,r in enumerate(rows(source), 1)), 'release_unknown')
    publics = unique(({k:r.get(k) for k in ('sample_id', 'base_scene_id', 'branch_id', 'level', 'split')}
                      for r in rows(public)), 'release_public_metadata')
    metadata = unique((dict({k:r.get(k) for k in META_FIELDS}, baseline_line=n)
                       for n,r in enumerate(rows(baseline / 'private_gold.jsonl'), 1)), 'baseline')
    requests = unique(({k:r.get(k) for k in ('sample_id', 'level', 'split', 'component', 'dataset')}
                       for r in rows(baseline / 'requests.jsonl')), 'baseline_requests_metadata')
    if set(metadata) != set(requests) or set(sources) != set(publics) or not set(sources) <= set(metadata):
        raise ValueError('BASELINE_RELEASE_REQUEST_ID_SET_MISMATCH')
    overlay = []; repaired = []; rejects = []
    for sid, meta in metadata.items():
        try:
            for field in ('level', 'split', 'component', 'dataset'):
                if meta[field] != requests[sid][field]:
                    raise ValueError('BASELINE_REQUEST_METADATA_MISMATCH:' + field)
            w, method = resolve_one(meta, sources.get(sid), publics.get(sid))
        except ValueError as exc:
            rejects.append(dict(sample_id=sid, baseline_line=meta['baseline_line'], reject_code=str(exc))); continue
        item = dict(meta, global_world_id=w, world_cluster_id=cluster(w), original_global_world_id=meta['global_world_id'], resolution=method)
        if sid in sources:
            item['source_provenance'] = dict(path=str(source), sha256=RELEASE_UNKNOWN_SHA, line=sources[sid]['source_line'], sample_id=sid,
                                           release_public_metadata=refs[str(public)])
        overlay.append(item)
        if method == 'EXACT_RELEASE_SAMPLE_ID': repaired.append(item)
    save(rr / 'unresolved_world_ids.jsonl', rejects, 'jsonl')
    save(rr / 'baseline_world_metadata.jsonl', overlay, 'jsonl')
    save(rr / 'recovered_world_ids.jsonl', repaired, 'jsonl')
    code = [entry(CODE / name) for name in ('config.json', 'common.py', 'world_identity_v2.py', 'inventory.py', 'inventory_v2.py', 'e0_snapshot.py', 'e0_snapshot_v2.py', 'snapshot_store_v2.py', 'job_cpu_v2.sh')]
    protected = [entry(p) for p in sorted((root / 'raw/E0_existing_snapshot').rglob('*.jsonl'))]
    protected += [entry(root / 'scores/E9' / m / 'acceptance.json') for m in c['models']]
    protected += [entry(root / 'whitebox/M0_v1/M0_ACCEPTANCE.json')]
    for ref in inputs:
        if sha(ref['path']) != ref['sha256']: raise ValueError('INPUT_CHANGED_DURING_REPAIR')
    report = dict(status='PASS' if not rejects else 'BLOCKED_UNRESOLVED_WORLD_ID', created_at=now(), job_id=os.environ['SLURM_JOB_ID'],
                  version=VERSION, config_snapshot=c, code_commit='UNAVAILABLE_NOT_A_GIT_WORKTREE; SHA256_SOURCE_REVISION_USED',
                  baseline_records=len(metadata), original_missing_world_ids=sum(not valid_world(x['global_world_id']) for x in metadata.values()),
                  recovered_records=len(repaired), recovered_world_clusters=len({x['world_cluster_id'] for x in repaired}),
                  recovered_split_counts=dict(Counter(x['split'] for x in repaired)), unresolved_records=len(rejects),
                  baseline_world_clusters=len({x['world_cluster_id'] for x in overlay}), regression_tests_passed=test_count,
                  immutable_inputs=inputs, code_files=code, protected_historical_files=protected, overlay=entry(rr / 'baseline_world_metadata.jsonl'),
                  output_files=[entry(rr / x) for x in ('recovered_world_ids.jsonl', 'unresolved_world_ids.jsonl')],
                  old_data_writes=0, model_calls=0, original_labels_prompts_predictions_unchanged=True,
                  downstream_policy='REQUIRE_ZERO_UNRESOLVED_BEFORE_ANY_WORLD_CLUSTER_CI_OR_SOURCE_POOL; NO_SYNTHETIC_IDS')
    save(rr / 'identity_acceptance.json', report)
    print(json.dumps({k:report[k] for k in ('status', 'baseline_records', 'original_missing_world_ids', 'recovered_records', 'recovered_world_clusters', 'unresolved_records', 'regression_tests_passed')}), flush=True)
    if rejects: raise ValueError('WORLD_IDENTITY_UNRESOLVED_SEE_REJECT_MANIFEST')

if __name__ == '__main__': main()
