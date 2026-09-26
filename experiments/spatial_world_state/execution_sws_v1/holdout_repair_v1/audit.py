"""Reconcile holdout prerequisites without predictions or fabricated qualification."""
import sys
from collections import Counter, defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common_auto_v2 import *
from data_continuation_v1.prepare import source_guard, validate_fact_pairs


def main():
    a = arguments(__doc__).parse_args(); c, root = setup(a)
    if a.dry_run:
        print('Source-only audit of locally complete unexposed worlds, historical media coverage and missing locators.'); return
    dest = root / 'preparation/holdout_repair_v1_20260910'
    if (dest / 'ACCEPTANCE.json').exists(): print('ALREADY_COMPLETE'); return
    guard = source_guard()
    old = root / 'preparation/global_assets_breadth_v1_20260910'
    inv = root / 'repairs/world_identity_v2/inventory'
    inputs = [old / n for n in ('holdout_eligibility.jsonl', 'asset_signatures.jsonl', 'unresolved_assets.jsonl', 'cross_world_edges.jsonl')]
    inputs += [inv / 'manifest/source_membership_audit.jsonl', inv / 'private_gold/source_fact_catalog.jsonl']
    save(dest / 'AUDIT_PROTOCOL.json', dict(created_at=now(), code=entry(__file__), inputs=[entry(p) for p in inputs],
        seed=c['seed'], selection='ALL_LOCAL_COVERAGE_UNEXPOSED_CANDIDATES_NO_OUTCOME_SELECTION',
        rules=['Existing excluded/sealed/test worlds remain excluded', 'Unresolved unselected assets are quarantined, not silently qualified',
               'All historically supplied media must be reconciled before any reduced-scope certificate',
               'Source-certified independent fact pairs required; no pixel or model inferred gold'],
        automatic_confirmation_inference=False, mechanism_lock_created=False))
    eligibility = list(rows(inputs[0])); members = {r['world_cluster_id']: r for r in rows(inputs[4])}
    candidates = {r['world_cluster_id'] for r in eligibility if r['local_coverage_pass']}
    aliases = {alias: w for w, m in members.items() for alias in m['aliases']}
    canon = lambda w: aliases.get(cluster(w), cluster(w))
    signed = list(rows(inputs[1])); bypath = {r['path']: r for r in signed}
    gap_counts = Counter(); gap_worlds = defaultdict(set); missing = []
    for r in rows(inputs[2]):
        sources = sorted({w.split(':', 1)[0] for w in r['worlds']})
        exposed = [w for w in r['worlds'] if members.get(w, {}).get('previously_exposed')]
        reason = 'EXPOSED_WORLD_UNUSED_OR_UNRESOLVED_SOURCE_ASSET' if exposed else 'UNSELECTED_SOURCE_ASSET_QUARANTINED'
        key = ('+'.join(sources), reason); gap_counts[key] += 1; gap_worlds[key].update(r['worlds'])
        if candidates.intersection(r['worlds']): missing.append(dict(r, priority='CANDIDATE_REQUIRED'))
    csvsave(dest / 'unresolved_by_source.csv', [dict(source=k[0], category=k[1], locators=v, worlds=len(gap_worlds[k])) for k, v in sorted(gap_counts.items())])
    # Read public request manifests only, not responses. Keep missing/nonimage paths explicit.
    manifests = [Path(c['baseline']) / 'requests.jsonl']
    for base in (root / 'batches', Path(c['b0']) / 'public_inputs', Path(c['phase_a']) / 'public_inputs'):
        if base.exists(): manifests.extend(base.rglob('requests.jsonl'))
    public_refs = []; supplied = {}; exposed_now = set(); unknown_world = []
    for path in sorted(set(manifests)):
        public_refs.append(entry(path))
        for r in rows(path):
            w = r.get('world_cluster_id') or r.get('global_world_id')
            if w: exposed_now.add(canon(w))
            media = r.get('payload', {}).get('media', r.get('media', []))
            for m in media:
                if not isinstance(m, dict) or not m.get('path'): continue
                f = m['path']; supplied.setdefault(f, dict(path=f, world_ids=set(), manifests=set(), declared_sha256=set()))
                if w: supplied[f]['world_ids'].add(canon(w))
                supplied[f]['manifests'].add(str(path))
                if m.get('sha256'): supplied[f]['declared_sha256'].add(m['sha256'].removeprefix('sha256:'))
    supply_rows = []
    for f, rr in sorted(supplied.items()):
        rec = {k: sorted(v) if isinstance(v, set) else v for k, v in rr.items()}
        signature = bypath.get(f)
        rec['coverage'] = 'SIGNED_IMAGE' if signature and signature.get('modality') == 'image' else 'REQUIRES_SIGNATURE_RECONCILIATION'
        if signature: rec['signature_sha256'] = signature['sha256']
        supply_rows.append(rec)
    save(dest / 'historical_supplied_media.jsonl', supply_rows, 'jsonl')
    save(dest / 'historical_public_manifest_index.json', public_refs)
    rejects = []; pairs = validate_fact_pairs(c, candidates, inputs[5], rejects)
    summaries = []; selected = []
    for w in sorted(candidates):
        m = members[w]; reasons = list(m['reasons'])
        if m['previously_exposed'] or w in exposed_now: reasons.append('EXPOSED_WORLD')
        families = {}
        for family in ('COUNT', 'NONCOUNT_RELATION'):
            choices = pairs.get((w, family), [])
            families[family] = len(choices)
            if choices:
                _, aa, bb = choices[0]
                selected.append(dict(world_cluster_id=w, family=family, source_pair=[aa, bb],
                    status='SOURCE_PAIR_AVAILABLE_NOT_YET_HOLDOUT_CERTIFIED', split='UNASSIGNED'))
        if not any(families.values()): reasons.append('NO_SOURCE_CERTIFIED_INDEPENDENT_PAIR')
        summaries.append(dict(world_cluster_id=w, source_membership=m, independent_pair_counts=families,
            reasons=reasons, source_pair_ready=not reasons, globally_qualified=False, split='UNASSIGNED'))
    save(dest / 'private_gold/candidate_source_pairs.jsonl', selected, 'jsonl')
    save(dest / 'candidate_qualification.jsonl', summaries, 'jsonl')
    save(dest / 'source_pair_rejects.jsonl', rejects, 'jsonl')
    save(dest / 'required_media_recovery.jsonl', missing, 'jsonl')
    report = dict(status='HOLDOUT_REPAIR_AUDIT_COMPLETE_NOT_CERTIFICATION', created_at=now(), job_id=os.environ['SLURM_JOB_ID'],
        local_complete_candidates=len(candidates), source_pair_ready=sum(r['source_pair_ready'] for r in summaries),
        later_exposure_overlap=sorted(candidates & exposed_now), required_candidate_missing_assets=len(missing),
        public_manifests=len(public_refs), supplied_media=len(supply_rows), supplied_signature_coverage=dict(Counter(r['coverage'] for r in supply_rows)),
        prediction_guard=guard, global_holdout_frozen=False, mechanism_lock=False,
        next='Reconcile supplied media including nonimage modalities; certify closed eligible pool or retain explicit blocker; then source-first split and frozen behavior compiler')
    save(dest / 'ACCEPTANCE.json', report); print(json.dumps(report), flush=True)


if __name__ == '__main__': main()
