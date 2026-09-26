"""Source-only continuation: qualify additional worlds, then freeze complete batches.

No predictions are consulted. Existing releases, code, batches and scores are read-only.
This is additional discovery coverage, not a replacement for missing spatial strata.
"""
import copy
import io
import itertools
import shutil
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common_auto_v2 import *
import real_design_v1 as design
from real_compile_v1 import SOURCE_IMAGES, BUNDLE, runtime_files

NAME = 'data_continuation_v1_20260910'
SUBS = ('ADD', 'REMOVE_POST_POSITIVE', 'REMOVE_POST_ZERO', 'PROTECTION_NOOP')


def source_guard():
    audit = dict(prediction_read_attempts=0)
    def hook(event, args):
        if event != 'open' or not isinstance(args[0], (str, bytes)): return
        path = str(args[0])
        if '/raw/' in path or '/scores/' in path or '/rescoring/' in path or 'predictions' in path:
            audit['prediction_read_attempts'] += 1
            raise PermissionError('SOURCE_SELECTION_MUST_NOT_READ_PREDICTIONS:' + path)
    sys.addaudithook(hook)
    return audit


def validate_fact_pairs(c, worlds, catalog, rejects):
    groups = defaultdict(dict)
    for row in rows(catalog):
        w, f = row['world_cluster_id'], row['fact']
        if w not in worlds or f['provenance']['source_dataset'] != 'CA-VQA' or not design.qualified_fact(f): continue
        roles = f.get('grounding', {}).get('frame_roles', {})
        if set(roles) != {'reference_frame', 'support_frame_1', 'support_frame_2', 'support_frame_3', 'support_frame_4'}: continue
        family = 'COUNT' if f['predicate'] == 'COUNT' else 'NONCOUNT_RELATION'
        key = (w, family, digest(roles))
        semantic = (f['subject'].split('@source_item:')[0], f['predicate'], str(f.get('object')).split('@source_item:')[0])
        prior = groups[key].get(semantic)
        if prior is not None and design.fact_value(prior['fact']) != design.fact_value(f):
            prior['conflicted'] = True
            rejects.append(dict(world_cluster_id=w, reason='CONFLICTING_SAME_FRAME_SOURCE_FACT', semantic=semantic))
        elif prior is None: groups[key][semantic] = copy.deepcopy(row)
    pairs = defaultdict(list)
    for (w, family, _), facts in groups.items():
        usable = [r for r in facts.values() if not r.get('conflicted')]
        for a, b in itertools.permutations(usable, 2):
            if design.independent_facts(a['fact'], b['fact']):
                rank = digest([c['seed'], 'SOURCE_PAIR', w, a['fact']['fact_id'], b['fact']['fact_id']])
                pairs[(w, family)].append((rank, a, b))
    for options in pairs.values(): options.sort(key=lambda x: x[0])
    return pairs


def image_signature(path):
    from PIL import Image, ImageOps
    h = sha(path)
    with Image.open(path) as im: im.verify()
    with Image.open(path) as im:
        quantized = [int(v) // 16 for v in ImageOps.grayscale(im).resize((16, 16)).getdata()]
    return h, digest(quantized)


def qualify_panel(c, root, dest, world, family, subtype, options, membership,
                  used_assets, used_reference_signatures, cache):
    if subtype == 'REMOVE_POST_POSITIVE': options = [x for x in options if design.fact_value(x[1]['fact']) >= 2]
    if subtype == 'REMOVE_POST_ZERO': options = [x for x in options if design.fact_value(x[1]['fact']) == 1]
    if not options: raise ValueError('NO_LEGAL_SOURCE_PAIR_FOR_SUBSTRATUM')
    # Same deterministic pair rule as D01; do not search alternative pairs for better model outcomes.
    _, a, b = options[0]
    for record in (a, b):
        ref = record['source_graph']; path = ref['path']
        if path not in cache:
            if sha(path) != ref['sha256']: raise ValueError('SOURCE_GRAPH_HASH_MISMATCH')
            cache[path] = {f['fact_id']: f for f in load(path)['facts']}
        if cache[path].get(record['fact']['fact_id']) != record['fact']: raise ValueError('SOURCE_FACT_REPLAY_MISMATCH')
    facts = [a['fact'], b['fact']]
    roles = facts[0]['grounding']['frame_roles']
    staged = []
    for role, member in sorted(roles.items(), key=lambda x: (x[0] != 'reference_frame', x[0])):
        if not member.startswith('cavqa_val/images/') or '..' in Path(member).parts:
            raise ValueError('MEDIA_ADAPTER_NOT_IMPLEMENTED_FOR_LOCATOR:' + member)
        src = SOURCE_IMAGES / member
        if not src.is_file(): raise ValueError('SOURCE_MEDIA_MISSING:' + str(src))
        h, perceptual = image_signature(src)
        if h in used_assets and used_assets[h] != world:
            raise ValueError('CROSS_WORLD_EXACT_IMAGE_REUSE:' + used_assets[h])
        if role == 'reference_frame' and perceptual in used_reference_signatures:
            raise ValueError('REFERENCE_QUANTIZED_NEAR_DUPLICATE:' + used_reference_signatures[perceptual])
        staged.append((role, src, h, perceptual))
    media, refs = [], []
    for role, src, h, perceptual in staged:
        cached = [BUNDLE / 'media/l1_l3' / (h[:24] + suffix) for suffix in ('.png', '.jpg')]
        dst = next((p for p in cached if p.is_file() and sha(p) == h), None)
        if dst is None:
            dst = dest / 'media' / (h + '.image'); dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() and sha(dst) != h: raise ValueError('PERSISTENT_MEDIA_HASH_CONFLICT')
            if not dst.exists(): shutil.copyfile(src, dst)
        if sha(dst) != h: raise ValueError('COPIED_MEDIA_HASH_MISMATCH')
        media.append(dict(kind='image', path=str(dst), role=role, sha256='sha256:' + h, presentation_max_pixels=401408))
        refs.append(dict(world_cluster_id=world, role=role, source=entry(src), persistent=entry(dst)))
    panel = dict(world_cluster_id=world, primary_stratum=family, count_substratum=subtype, split='discovery',
        source_membership=membership, facts=facts, source_graphs=[a['source_graph'], b['source_graph']], media=media,
        review_status=c['review']['default_review_status'], scientific_review_grade='AUTO_ONLY_PROVISIONAL',
        genuine_multiview_necessity=False, reference_only_sufficiency='SOURCE_REFERENCE_FRAME_QA',
        independent_fact_scope='DIFFERENT_CATEGORY_COUNTS_OR_DISJOINT_NAMED_ENTITY_CLASSES')
    if family == 'COUNT': design.branch_spec(facts[0], subtype)
    for role, _, h, perceptual in staged:
        used_assets[h] = world
        if role == 'reference_frame': used_reference_signatures[perceptual] = world
    return panel, refs


def compile_batch(c, root, batch, panels, prep_refs):
    out = root / 'batches' / batch
    if (out / 'manifest/REQUEST_LOCK.json').exists(): raise ValueError('REFUSE_REFREEZE_EXISTING_BATCH')
    previous = design.BATCH; design.BATCH = batch
    try:
        reqs, gold, matches, aliases = [], [], [], []
        for p in panels:
            r, g, m, a = design.build_world(c, p, p['media'])
            reqs.extend(r); gold.extend(g); matches.extend(m); aliases.extend(a)
    finally: design.BATCH = previous
    if len({r['request_id'] for r in reqs}) != len(reqs): raise ValueError('DUPLICATE_REQUEST')
    if {r['request_id'] for r in reqs} != {g['request_id'] for g in gold}: raise ValueError('GOLD_ID_MISMATCH')
    save(out / 'public_inputs/requests.jsonl', reqs, 'jsonl')
    for name, data in [('world_panel', panels), ('request_gold', gold), ('matched_structure', matches), ('logical_aliases', aliases)]:
        save(out / f'private_gold/{name}.jsonl', data, 'jsonl')
    ordered = sorted(panels, key=lambda p: digest([c['seed'], 'REAL_D01_SHARD', p['world_cluster_id']]))
    shards = []
    for sid, start in enumerate(range(0, len(ordered), 6)):
        ws = {p['world_cluster_id'] for p in ordered[start:start + 6]}
        rr = [r for r in reqs if r['world_cluster_id'] in ws]
        path = out / f'public_inputs/shard_{sid:03}.jsonl'; save(path, rr, 'jsonl')
        shards.append(dict(shard=sid, worlds=len(ws), requests=len(rr), request_file=entry(path)))
    save(out / 'manifest/shards.json', shards)
    code = runtime_files(c) + [entry(HERE / name) for name in ('prepare.py', 'runner.py', 'job.sh', 'submit.py')]
    code.extend(entry(CODE / 'interface_repair_v2' / n) for n in ('adapter.py', 'rescore.py', 'test_adapter.py', 'job.sh'))
    media = {m['path']: entry(m['path']) for p in panels for m in p['media']}
    save(out / 'manifest/REQUEST_LOCK.json', dict(batch=batch, run_id=c['run_id'], created_at=now(),
        status='FROZEN_SOURCE_QUALIFIED_PROCESSOR_PENDING', config_snapshot=c, code=code,
        public_inputs=[entry(out / 'public_inputs/requests.jsonl'), entry(out / 'manifest/shards.json')] + [s['request_file'] for s in shards],
        private_inputs=[entry(out / f'private_gold/{n}.jsonl') for n in ('world_panel', 'request_gold', 'matched_structure', 'logical_aliases')],
        media=list(media.values()), preparation=prep_refs, models=c['models'], human_gate=False,
        selection='SOURCE_ONLY_FIXED_SEED_HASH_CONTINUATION_WITHOUT_PRIOR_WORLD_REUSE',
        legacy_design_reused_byte_for_byte=True, E6_world_cap_reserved=True,
        genuine_multiview_necessity=False, controlled_branches_not_native_L4=True))
    report = dict(batch=batch, status='COMPILED_PROCESSOR_PENDING', worlds=len(panels), requests_per_model=len(reqs),
        logical_requests_per_model=len(aliases), primary_strata=dict(Counter(p['primary_stratum'] for p in panels)),
        count_substrata=dict(Counter(p['count_substratum'] for p in panels if p['count_substratum'])),
        logical_module_requests=dict(Counter(a['experiment'] for a in aliases)), shards=shards,
        predictions_used_for_selection=False, human_gate=False, full_study_complete=False)
    save(out / 'reports/COMPILE_ACCEPTANCE.json', report)
    print(json.dumps(report), flush=True)
    return report


def main():
    a = arguments(__doc__).parse_args(); c, root = setup(a)
    if a.dry_run: print('Source-only additional discovery compilation; no new model calls on login.'); return
    dest = root / 'preparation' / NAME
    if (dest / 'PREPARATION_ACCEPTANCE.json').exists():
        print('ALREADY_PREPARED_READ_EXISTING_ACCEPTANCE'); return
    audit = source_guard()
    from real_tests_v1 import DesignTests
    buf = io.StringIO(); test = unittest.TextTestRunner(stream=buf, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DesignTests))
    save(dest / 'design_tests.txt', buf.getvalue(), 'text')
    if not test.wasSuccessful(): raise RuntimeError(buf.getvalue())
    inv = root / 'repairs/world_identity_v2/inventory'
    inventory = inv / 'manifest/world_candidate_inventory.jsonl'; catalog = inv / 'private_gold/source_fact_catalog.jsonl'
    source_refs = [entry(inventory), entry(catalog)]
    expected = {r['path']: r['sha256'] for r in load(root / 'repairs/world_identity_v2/REPAIR_ACCEPTANCE.json')['output_files']}
    if any(expected[r['path']] != r['sha256'] for r in source_refs): raise ValueError('SOURCE_INVENTORY_CHANGED')
    old_panels, old_locks = [], []
    for path in sorted((root / 'batches').glob('*/manifest/REQUEST_LOCK.json')):
        data = load(path)
        if path.parent.parent.name.startswith('ca_source_d'):
            old_locks.append(entry(path))
            old_panels.extend(rows(path.parent.parent / 'private_gold/world_panel.jsonl'))
    old_by_world = {p['world_cluster_id']: p for p in old_panels}
    used = set(old_by_world); assets, perceptual = {}, {}
    for w, p in old_by_world.items():
        for m in p['media']:
            h, sig = image_signature(m['path']); assets[h] = w
            if m['role'] == 'reference_frame': perceptual[sig] = w
    worlds = {r['world_cluster_id']: r for r in rows(inventory)
        if r['world_cluster_id'].startswith('arkitscenes:') and r['source_membership']['previously_exposed']
        and r['source_membership']['allowed_future_split'] == 'DISCOVERY_ONLY' and not r['source_membership']['reasons']}
    old_counts = Counter(p['count_substratum'] for p in old_by_world.values() if p['primary_stratum'] == 'COUNT')
    quota = [('COUNT', s, max(0, 20 - old_counts[s])) for s in SUBS]
    quota.append(('NONCOUNT_RELATION', None, max(0, 80 - sum(p['primary_stratum'] == 'NONCOUNT_RELATION' for p in old_by_world.values()))))
    # All these worlds run E6. Reserve its existing fixed 144-world overall limit.
    capacity = max(0, 144 - len(old_by_world))
    rule = dict(created_at=now(), seed=c['seed'], old_batch_locks=old_locks, source_refs=source_refs,
        count_discovery_target_per_substratum=20, relation_discovery_target=80, quotas=quota,
        E6_remaining_capacity=capacity, selection_rank='sha256([seed, REAL_D01_<subtype_or_family>, world])',
        pair_rank='sha256([seed, SOURCE_PAIR, world, fact_a_id, fact_b_id])',
        old_global_targets_unchanged=c['sampling']['stratum_targets'], no_prediction_selection=True,
        supplementary_batch_implementation_not_retroactive_preregistration=True,
        near_duplicate_policy='REDACTED_OPAQUE_CREDENTIAL',
        unexposed_worlds_not_assigned_or_read_for_this_discovery_batch=True)
    save(dest / 'SOURCE_SELECTION_LOCK.json', rule)
    rejects = []; pairs = validate_fact_pairs(c, worlds, catalog, rejects)
    ranked = {}
    for family, subtype, n in quota:
        ranked[(family, subtype)] = iter(sorted({w for w, f in pairs if f == family and w not in used},
            key=lambda w: digest([c['seed'], 'REAL_D01_' + str(subtype or family), w])))
    chosen, media_refs, cache, selected_counts, exhausted = [], [], {}, Counter(), set()
    while len(chosen) < capacity:
        advanced = False
        for family, subtype, limit in quota:
            key = family, subtype
            if key in exhausted or selected_counts[key] >= limit or len(chosen) >= capacity: continue
            for w in ranked[key]:
                if w in used: continue
                try:
                    panel, refs = qualify_panel(c, root, dest, w, family, subtype, pairs[(w, family)],
                        worlds[w]['source_membership'], assets, perceptual, cache)
                except (ValueError, FileNotFoundError, OSError) as exc:
                    rejects.append(dict(world_cluster_id=w, family=family, subtype=subtype, reason=str(exc))); continue
                chosen.append(panel); media_refs.extend(refs); used.add(w); selected_counts[key] += 1; advanced = True
                if len(chosen) % 10 == 0: print(json.dumps(dict(stage='SOURCE_MEDIA_QUALIFIED', worlds=len(chosen))), flush=True)
                break
            else: exhausted.add(key)
        if not advanced: break
    save(dest / 'qualified_worlds.jsonl', chosen, 'jsonl'); save(dest / 'media_provenance.jsonl', media_refs, 'jsonl')
    save(dest / 'rejects.jsonl', rejects, 'jsonl')
    reports = []
    for idx, start in enumerate(range(0, len(chosen), 24), 2):
        batch = f'ca_source_d{idx:02}_20260910'
        reports.append(compile_batch(c, root, batch, chosen[start:start + 24],
            [entry(dest / 'SOURCE_SELECTION_LOCK.json'), entry(dest / 'qualified_worlds.jsonl')]))
    save(dest / 'BATCH_MANIFEST.json', reports)
    for ref in old_locks + source_refs:
        if sha(ref['path']) != ref['sha256']: raise ValueError('HISTORICAL_INPUT_MODIFIED')
    report = dict(status='SOURCE_AND_REQUEST_PREPARATION_COMPLETE' if chosen else 'NO_ADDITIONAL_QUALIFIED_WORLDS',
        created_at=now(), job_id=os.environ['SLURM_JOB_ID'], additional_worlds=len(chosen),
        prior_worlds=len(old_by_world), unique_discovery_worlds=len(used), batches=len(reports),
        requests_per_model=sum(x['requests_per_model'] for x in reports),
        primary_strata=dict(Counter(p['primary_stratum'] for p in chosen)),
        count_substrata=dict(Counter(p['count_substratum'] for p in chosen if p['count_substratum'])),
        reject_counts=dict(Counter(r['reason'].split(':')[0] for r in rejects)),
        tests=test.testsRun, source_guard=audit, human_gate=False, old_inputs_unchanged=True,
        GPU_execution='NOT_YET_SUBMITTED', genuinely_multiview_worlds=0,
        qualification='AUTO_ONLY_PROVISIONAL', full_480_panel_complete=False,
        batches_manifest=entry(dest / 'BATCH_MANIFEST.json'))
    save(dest / 'PREPARATION_ACCEPTANCE.json', report); print(json.dumps(report), flush=True)


if __name__ == '__main__': main()
