"""Materialize native E8 evidence bundles and C1 asset coverage without predictions.

Native task levels come from the frozen baseline metadata. This compiler does not
invent intermediate truth, relabel controlled D01 worlds, or open sealed graphs.
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common_auto_v2 import *
from prepare import source_guard, image_signature
from real_compile_v1 import SOURCE_IMAGES


def walk_fields(value, wanted):
    found = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k in wanted: found.append(dict(field=k, value=v))
            found.extend(walk_fields(v, wanted))
    elif isinstance(value, list):
        for v in value: found.extend(walk_fields(v, wanted))
    return found


def main():
    a = arguments(__doc__).parse_args(); c, root = setup(a)
    if a.dry_run: print('Native E8 source bundles and independent C1 media audit; no model inference.'); return
    dest = root / 'preparation/native_e8_c1_v1_20260910'
    if (dest / 'PREPARATION_ACCEPTANCE.json').exists(): print('ALREADY_PREPARED'); return
    audit = source_guard(); project = Path(c['project'])
    inv = root / 'repairs/world_identity_v2/inventory'
    inventory_path = inv / 'manifest/world_candidate_inventory.jsonl'
    metadata_path = root / 'repairs/world_identity_v2/baseline_world_metadata.jsonl'
    inventory = {r['world_cluster_id']: r for r in rows(inventory_path)}
    canonical = {alias: w for w, r in inventory.items() for alias in r['source_membership']['aliases']}
    def world_id(w):
        w = cluster(w); return canonical.get(w, w)
    permitted = {w: r for w, r in inventory.items() if not r['source_membership']['reasons']}
    bylevel = defaultdict(lambda: defaultdict(list)); sample_metadata = {}
    for r in rows(metadata_path):
        w = world_id(r['global_world_id'])
        if r['split'] not in ('train', 'dev') or w not in permitted: continue
        if not permitted[w]['source_membership']['previously_exposed']: continue
        sample_metadata[r['sample_id']] = r
        if r['component'] == 'binary': bylevel[r['level']][w].append(r['sample_id'])
    # Native level/world anchors selected before examining proof completeness or outcomes.
    chosen = []
    for level in ('L1', 'L2', 'L3', 'L4'):
        ranked = sorted(bylevel[level], key=lambda w: digest([c['seed'], 'E8_NATIVE_WORLD_V1', level, w]))
        for w in ranked[:c['sampling']['E8_target_per_level']]:
            chosen.append(dict(level=level, world_cluster_id=w, sample_ids=sorted(bylevel[level][w]), split='discovery'))
    save(dest / 'NATIVE_ANCHOR_LOCK.json', dict(created_at=now(), seed=c['seed'], targets=chosen,
        metadata=entry(metadata_path), inventory=entry(inventory_path), selection='FIXED_LEVEL_WORLD_HASH_NO_MODEL_OUTPUTS',
        original_level_preserved=True, original_source_test_and_sealed_excluded=True,
        union_worlds=len({x['world_cluster_id'] for x in chosen}), code=entry(__file__)))
    selected_samples = {s for x in chosen for s in x['sample_ids']}
    pair_requests = defaultdict(list)
    # The mixed release input stream is filtered using metadata; excluded records are not retained or used.
    for r in rows(Path(c['baseline']) / 'requests.jsonl'):
        if r['sample_id'] not in selected_samples: continue
        pair_requests[r['pair_id']].append(r)
    anchor_keys = {(x['level'], x['world_cluster_id']) for x in chosen}
    pairs_for_world = defaultdict(list)
    for pid, reqs in pair_requests.items():
        meta = sample_metadata[reqs[0]['sample_id']]
        key = meta['level'], world_id(meta['global_world_id'])
        if key in anchor_keys: pairs_for_world[key].append(pid)
    selected_pair_ids = {min(v, key=lambda p: digest([c['seed'], 'E8_NATIVE_PAIR_V1', p])) for v in pairs_for_world.values()}
    sources = [project / 'release/production_available_v10/pairs.jsonl',
        Path('artifacts/benchmark/l4/release/pairs.l4_three_part_v3.jsonl')]
    pairs = {}; source_refs = []
    for path in sources:
        source_refs.append(entry(path))
        for line, r in enumerate(rows(path), 1):
            if r.get('pair_id') not in selected_pair_ids: continue
            if r['pair_id'] in pairs: raise ValueError('DUPLICATE_SELECTED_NATIVE_PAIR')
            pairs[r['pair_id']] = dict(pair=r, file=str(path), line=line)
    missing_pairs = sorted(selected_pair_ids - set(pairs))
    selected_worlds = {x['world_cluster_id'] for x in chosen}
    graph_refs = defaultdict(dict); fact_refs = defaultdict(dict); asset_owners = defaultdict(set)
    representative = {}; facts_scanned = 0
    catalog_path = inv / 'private_gold/source_fact_catalog.jsonl'
    for row in rows(catalog_path):
        facts_scanned += 1; w = row['world_cluster_id']; f = row['fact']
        if w in selected_worlds:
            graph_refs[w][row['source_graph']['path']] = row['source_graph']
            fact_refs[w][f['fact_id']] = row
        roles = f.get('grounding', {}).get('frame_roles', {})
        for member in roles.values():
            if isinstance(member, str) and member.startswith('cavqa_val/images/'):
                asset_owners[member].add(w)
        dataset = f['provenance']['source_dataset']
        key = (dataset, f['provenance'].get('adapter_version'), f['predicate'], f['context'].get('scope'))
        if key not in representative: representative[key] = row
    save(dest / 'source_adapter_examples.jsonl', representative.values(), 'jsonl')
    bundle_rows = []; statuses = Counter()
    for key, candidates in sorted(pairs_for_world.items()):
        level, w = key; pid = min(candidates, key=lambda p: digest([c['seed'], 'E8_NATIVE_PAIR_V1', p]))
        if pid not in pairs:
            bundle_rows.append(dict(level=level, world_cluster_id=w, pair_id=pid, status='MISSING_RELEASE_PAIR')); continue
        source = pairs[pid]; pair = source['pair']
        refs = list(graph_refs[w].values())
        for ref in refs:
            if sha(ref['path']) != ref['sha256']: raise ValueError('E8_GRAPH_HASH_CHANGED')
        sid = {s for r in pair_requests[pid] for s in [r['sample_id']]}
        if any(sample_metadata[s]['level'] != level for s in sid): raise ValueError('NATIVE_LEVEL_CHANGED')
        witness = walk_fields(pair, {'premise_ids', 'premise_fact_ids', 'supporting_fact_ids', 'fact_ids',
            'pre_state', 'post_state', 'pre_count', 'post_count', 'transition', 'transition_result', 'intervention',
            'proof', 'certificate', 'evidence', 'evidence_subgraph_id', 'rule_id', 'rule_ids'})
        source_item_ids = set(pair.get('source', {}).get('source_item_ids', []))
        native_facts = [r for r in fact_refs[w].values()
            if source_item_ids & set(r['fact']['provenance'].get('source_item_ids', []))]
        media = {m['path']: m for r in pair_requests[pid] for m in r.get('media', [])}
        media_checks = []
        for path, m in media.items():
            expected = m.get('sha256', '').removeprefix('sha256:')
            if not Path(path).is_file(): media_checks.append(dict(path=path, status='MISSING')); continue
            actual = sha(path)
            media_checks.append(dict(path=path, status='HASH_PASS' if actual == expected else 'HASH_MISMATCH', sha256=actual))
        status = 'EVIDENCE_BUNDLE_READY_FOR_TYPED_QUERY_COMPILER'
        if not media_checks or any(x['status'] != 'HASH_PASS' for x in media_checks): status = 'MEDIA_CHECK_FAILED'
        payload = dict(level=level, world_cluster_id=w, pair_id=pid, source=source, source_graphs=refs,
            matching_source_facts=native_facts, native_proof_fields=witness,
            original_requests=pair_requests[pid], media_checks=media_checks, split='discovery', status=status,
            cannot_infer_missing_intermediate_truth=True, predictions_used=False)
        path = dest / 'private_gold/native_bundles' / (level + '_' + digest([w, pid])[:24] + '.json')
        save(path, payload)
        bundle_rows.append(dict(level=level, world_cluster_id=w, pair_id=pid, status=status,
            matching_direct_facts=len(native_facts), proof_fields=len(witness), source_graphs=len(refs), bundle=entry(path)))
        statuses[(level, status)] += 1
    save(dest / 'native_bundle_index.jsonl', bundle_rows, 'jsonl')
    # Compute actual-byte and coarse image signatures for the CA validation asset universe.
    # Other modalities remain explicit gaps; this file never declares C1 qualification.
    signatures, failures = [], []
    for n, (member, owners) in enumerate(sorted(asset_owners.items()), 1):
        path = SOURCE_IMAGES / member
        try:
            h, q = image_signature(path)
            signatures.append(dict(member=member, worlds=sorted(owners), path=str(path), sha256=h,
                quantized_reference_signature=q, previously_exposed=any(inventory[w]['source_membership']['previously_exposed'] for w in owners)))
        except (OSError, ValueError) as exc: failures.append(dict(member=member, worlds=sorted(owners), reason=str(exc)))
        if n % 1000 == 0: print(json.dumps(dict(stage='CA_ASSET_HASH_AUDIT', checked=n, total=len(asset_owners))), flush=True)
    owner_maps = {'sha256': {}, 'quantized_reference_signature': {}}; edges = []
    for r in signatures:
        for typ, owners in owner_maps.items():
            key = r[typ]
            if key in owners:
                prior = owners[key]
                if set(prior['worlds']) != set(r['worlds']): edges.append(dict(kind=typ, left=prior['worlds'], right=r['worlds'], signature=key))
            else: owners[key] = r
    save(dest / 'ca_asset_signatures.jsonl', signatures, 'jsonl')
    save(dest / 'ca_cross_world_asset_edges.jsonl', edges, 'jsonl')
    save(dest / 'ca_asset_failures.jsonl', failures, 'jsonl')
    report = dict(status='NATIVE_EVIDENCE_AND_PARTIAL_ASSET_AUDIT_COMPLETE', created_at=now(), job_id=os.environ['SLURM_JOB_ID'],
        native_anchor_worlds_by_level=dict(Counter(r['level'] for r in chosen)),
        native_bundles=len(bundle_rows), native_unique_worlds=len(selected_worlds),
        bundle_status=[dict(level=k[0], status=k[1], worlds=v) for k, v in sorted(statuses.items())],
        missing_release_pairs=missing_pairs, source_facts_scanned=facts_scanned,
        actual_ca_images_checked=len(signatures), ca_asset_failures=len(failures), cross_world_edges=len(edges),
        source_guard=audit, human_gate=False, source_release_refs=source_refs,
        E8='NATIVE_EVIDENCE_MATERIALIZED_TYPED_PUBLIC_DIAGNOSTIC_QUERIES_NOT_YET_COMPILED',
        C1='PARTIAL_CA_ASSET_AUDIT_NOT_GLOBAL_HOLDOUT_QUALIFICATION',
        C1_remaining=['NON_CA_AND_EXCLUDED_WORLD_ASSET_RECONCILIATION', 'ROBUST_NEAR_DUPLICATE_QUALIFICATION', 'GLOBAL_SPLIT_FREEZE'],
        input_truth_from_models=False, no_new_model_generations=True)
    save(dest / 'PREPARATION_ACCEPTANCE.json', report); print(json.dumps(report), flush=True)


if __name__ == '__main__': main()
