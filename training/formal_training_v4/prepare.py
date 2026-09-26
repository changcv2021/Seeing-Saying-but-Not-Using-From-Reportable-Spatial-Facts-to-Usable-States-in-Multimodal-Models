"""Freeze approved train-only sources for v4. Run in a Slurm CPU allocation."""
import argparse
import json
import os
from collections import Counter, defaultdict
from plan import *


def main():
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('SLURM_REQUIRED_FOR_DATA_PREPARATION')
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--updates', type=int, default=DEFAULTS['optimizer_updates'])
    parser.add_argument('--effective-batch-size', type=int, default=DEFAULTS['effective_batch_size'])
    parser.add_argument('--micro-batch-size', type=int, default=DEFAULTS['micro_batch_size'])
    parser.add_argument('--attention-backend', choices=('sdpa_auto',), default='sdpa_auto')
    args = parser.parse_args()
    plan = dict(DEFAULTS, optimizer_updates=args.updates,
                effective_batch_size=args.effective_batch_size, micro_batch_size=args.micro_batch_size,
                attention_backend=args.attention_backend)
    validate_plan(plan)
    if args.output.exists():
        raise FileExistsError('PRESERVE_EXISTING_RUN:' + str(args.output))
    previous = ROOT / 'formal_training_v1/prepared_v1'
    old = read(previous / 'BUDGET_PLAN.json')
    if sha(previous / 'catalog.jsonl') != old['catalog_sha256']:
        raise ValueError('APPROVED_CATALOG_CHANGED')
    if not read(ROOT / 'SPLIT_AUDIT.json')['status'].startswith('PASS'):
        raise ValueError('SPLIT_AUDIT')
    if any(sha(p) != h for p, h in old['source_hashes'].items()):
        raise ValueError('APPROVED_TRAIN_SOURCE_CHANGED')
    meta = [json.loads(l) for l in (previous / 'catalog.jsonl').read_text().splitlines() if l.strip()]
    samples = {}
    cot = {}
    state_by_world = defaultdict(list)
    for row in meta:
        if row['pool'] == 'answer':
            if row['sample_id'] in samples:
                raise ValueError('DUPLICATE_BASE_SAMPLE')
            samples[row['sample_id']] = dict(world=row['underlying_world_id'], level=row['level'], answer=row['key'])
        elif row['pool'] == 'cot':
            cot[row['sample_id']] = row['key']
        elif row['pool'] == 'state':
            state_by_world[row['underlying_world_id']].append(row)
    if set(samples) != set(cot) or len(samples) != old['original_samples']:
        raise ValueError('SAME_ORIGINAL_SAMPLE_POOL_REQUIRED')
    worlds = {s['world'] for s in samples.values()}
    if set(state_by_world) - worlds:
        raise ValueError('AUXILIARY_WORLD_OUTSIDE_TRAIN')
    coverage = {'pss_l4_no_aux': 0, 'pss_full_no_aux': 0}
    for sid, sample in samples.items():
        sample['cot'] = cot[sid]
        # Auxiliary supervision is attached to this SAME underlying world.
        # Never sample an unrelated world to fill an output-token quota.
        available = state_by_world[sample['world']]
        for method in ('pss_l4', 'pss_full'):
            selected = [r for r in available if method != 'pss_l4' or r['level'] == 'L4']
            sample[method] = sorted(r['key'] for r in selected)
            if not selected:
                coverage[method + '_no_aux'] += 1
    exposure = {}
    for method in METHODS:
        for seed in SEEDS:
            schedule = ExampleSchedule(samples, seed, method != 'answer_natural')
            seen = set(); levels = Counter(); token_count = 0; forward_count = 0
            meta_by_key = {r['key']: r for r in meta}
            stream_hash = hashlib.sha256()
            for index in range(plan['optimizer_updates'] * plan['effective_batch_size']):
                sid = schedule.at(index); seen.add(sid); levels[samples[sid]['level']] += 1
                stream_hash.update((sid+'\n').encode())
                for key, weight in unit_records(samples, sid, method, seed, index):
                    token_count += meta_by_key[key]['target_tokens']; forward_count += 1
            exposure[f'{method}__seed_{seed}'] = dict(base_examples=plan['optimizer_updates']*plan['effective_batch_size'],
                unique_samples=len(seen), unique_worlds=len({samples[s]['world'] for s in seen}),
                level_exposures=dict(levels), supervised_tokens=token_count, forward_records=forward_count,
                base_stream_sha256=stream_hash.hexdigest())
    for seed in SEEDS:
        if len({exposure[f'{m}__seed_{seed}']['base_stream_sha256'] for m in METHODS if m!='answer_natural'}) != 1:
            raise ValueError('BALANCED_STREAM_MISMATCH')
    plan.update(methods=list(METHODS), seeds=list(SEEDS), source_hashes=old['source_hashes'],
                expected_exposure=exposure,
                original_samples=len(samples), train_worlds=len(worlds),
                auxiliary_coverage=coverage, legacy_catalog_sha256=old['catalog_sha256'],
                source_budget_sha256=sha(previous / 'BUDGET_PLAN.json'),
                primary_unit='one original sample with optional same-world auxiliary target',
                auxiliary_weighting='mean of answer and one selected auxiliary record per primary unit',
                target_policy='existing answer/partial-CoT/state targets unchanged',
                schedule='balanced level/world/sample stream; natural retains sample-frequency control',
                matched=['optimizer_updates', 'effective_batch_size', 'LoRA', 'learning_rate_schedule'],
                measured_not_matched=['supervised_output_tokens', 'input_tokens', 'forward_records', 'walltime'],
                checkpoint_policy='fixed final step; no held-out test selection',
                code_hashes=code_hashes(), output=str(args.output))
    args.output.mkdir(parents=True)
    (args.output / 'logs').mkdir()
    for name, value in [('samples.json', samples), ('catalog.json', {r['key']: r for r in meta})]:
        (args.output / name).write_text(json.dumps(value, sort_keys=True) + '\n')
    plan['samples_sha256'] = sha(args.output / 'samples.json')
    plan['catalog_sha256'] = sha(args.output / 'catalog.json')
    (args.output / 'PLAN.json').write_text(json.dumps(plan, indent=2, sort_keys=True) + '\n')
    ordered=sorted(samples,key=lambda k:digest(['fixed_engineering_panel',k]))
    panel=[]
    for level in ('L1','L2','L3','L4'):
        panel.extend([s for s in ordered if samples[s]['level']==level][:2])
    panel.append(max(ordered,key=lambda s:meta_by_key[samples[s]['answer']]['media_count']))
    panel.append(max(ordered,key=lambda s:meta_by_key[samples[s]['cot']]['target_tokens']))
    fallback=next((s for s in ordered if meta_by_key[samples[s]['cot']].get('rationale_available') is False),None)
    if fallback:panel.append(fallback)
    s2worlds={r['underlying_world_id'] for r in meta if r['pool']=='state' and r.get('stage')=='S2'}
    s2=next((s for s in ordered if samples[s]['world'] in s2worlds),None)
    if s2:panel.append(s2)
    panel=list(dict.fromkeys(panel))
    panel=(panel+[s for s in ordered if s not in panel])[:plan['effective_batch_size']]
    (args.output/'SMOKE_PANEL.json').write_text(json.dumps(dict(sample_ids=panel,
        selection='train-only fixed hashes, all levels, largest media/target, CoT fallback and S2 world',
        model_errors_used=False),indent=2)+'\n')
    # Preserve the exact source snapshot as well as hashes; repairs require a new version.
    import shutil
    snapshot=args.output/'source_snapshot'
    snapshot.mkdir()
    for path in plan['code_hashes']:
        source=Path(path);dest=snapshot/digest(str(source))[:12]/source.name
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    print(json.dumps(dict(output=str(args.output), samples=len(samples), coverage=coverage,
                         updates=plan['optimizer_updates'], effective_batch_size=plan['effective_batch_size'],
                         status='PREPARED_NOT_GPU_VALIDATED'), indent=2))


if __name__ == '__main__':
    main()
