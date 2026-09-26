"""Compute actual target token counts, freeze schedules, and probe current inputs."""
from collections import Counter, defaultdict
import math
import os
import time
from paths import *
from core import METHODS, SEEDS, TOKENS_PER_UPDATE, Schedule, digest


def main():
    compute()
    if PREPARED.exists():
        raise FileExistsError('PRESERVE_PREPARED_OUTPUT:' + str(PREPARED))
    from transformers import AutoProcessor
    from model_io_verified import encode
    from state_interface_v2 import encode_state_v2, state_prompt_v2
    from state_schema import parse_state
    if not read(ROOT/'SPLIT_AUDIT.json')['status'].startswith('PASS'):
        raise ValueError('SPLIT_AUDIT')
    accepted = read(ROOT/'prepared_data_v2/MANIFEST.json')
    processor = AutoProcessor.from_pretrained(MODEL, local_files_only=True, use_fast=True)
    all_rows = {}; metadata = {}; aliases = []; seen_states = {}; hashes = {}
    for pool, path in sources():
        value = sha(path)
        if value != accepted['input_hashes'][str(path)]:
            raise ValueError('PREPARED_SOURCE_HASH_CHANGED:' + str(path))
        hashes[str(path)] = value
        for line, row in enumerate(rows(path)):
            if row['split'] != 'train':
                raise ValueError('NONTRAIN_ROW')
            target = row['target']
            n = len(processor.tokenizer.encode(target, add_special_tokens=False)) + int(row['end_turn'])
            if not 0 < n <= 512:
                raise ValueError('TARGET_BUDGET')
            sid = row['sample_id']
            key = pool + ':' + sid if pool != 'state' else 'state:' + row.get('aux_id', sid)
            if pool == 'state':
                if parse_state(target) != row['state']:
                    raise ValueError('STATE_TARGET')
                prompt = state_prompt_v2(row['task_prompt'])
                signature = digest([row['request'].get('media', []), prompt, target, row['end_turn']])
                if signature in seen_states:
                    aliases.append(dict(source=str(path), line=line, original_key=key, kept=seen_states[signature]))
                    continue
                seen_states[signature] = key
            if key in metadata:
                raise ValueError('DUPLICATE_KEY:' + key)
            metadata[key] = dict(key=key, pool=pool, sample_id=sid, level=row['level'],
                stage=row.get('stage'), source=str(path), line=line, target_tokens=n,
                underlying_world_id=row['underlying_world_id'], end_turn=row['end_turn'],
                rationale_available=row.get('rationale_available'),
                media_count=len(row['request'].get('media', [])))
            all_rows[key] = row
    answer = {r['sample_id'] for r in metadata.values() if r['pool'] == 'answer'}
    cot = {r['sample_id'] for r in metadata.values() if r['pool'] == 'cot'}
    if answer != cot or len(answer) != 13476:
        raise ValueError('ORIGINAL_POOL_CHANGED')
    # Frozen split components already audited; independently enforce aux inheritance.
    worlds = {r['underlying_world_id'] for r in metadata.values() if r['pool'] == 'answer'}
    if any(r['underlying_world_id'] not in worlds for r in metadata.values()):
        raise ValueError('AUX_WORLD_NOT_IN_TRAIN')
    coverage = {f'{m}__seed_{s}': Schedule(metadata, m, s).coverage_tokens() for m in METHODS for s in SEEDS}
    updates = math.ceil(max(coverage.values()) / TOKENS_PER_UPDATE)
    total = updates * TOKENS_PER_UPDATE
    budgets = {}
    for method in METHODS:
        for seed in SEEDS:
            schedule = Schedule(metadata, method, seed); exposures = Counter(); pools = Counter(); levels = Counter()
            fragments = 0
            for _ in range(updates):
                for seg in schedule.segments(TOKENS_PER_UPDATE):
                    fragments += 1
                    if seg['begins_example']:
                        exposures[seg['key']] += 1; r = metadata[seg['key']]
                        pools[r['pool']] += 1; levels[r['pool']+'/'+r['level']] += 1
            base_pool = 'cot' if method == 'cot_partial' else 'answer'
            covered = {metadata[k]['sample_id'] for k in exposures if metadata[k]['pool'] == base_pool}
            if covered != answer:
                raise ValueError('ORIGINAL_SAMPLE_NOT_EXPOSED')
            run = f'{method}__seed_{seed}'
            budgets[run] = dict(method=method, seed=seed, optimizer_updates=updates,
                supervised_tokens=total, tokens_per_update=TOKENS_PER_UPDATE,
                examples_started=sum(exposures.values()), forward_fragments=fragments,
                pool_exposures=dict(pools), level_exposures=dict(levels),
                unique_original_samples=len(covered), unique_training_records=len(exposures),
                original_effective_passes=pools[base_pool]/len(answer),
                final_sampler_state=schedule.state_dict(), exposure_digest=digest(dict(exposures)))
    # Actual current processor inputs: fixed hashes per task/level plus max-media.
    groups = defaultdict(list)
    for key, m in metadata.items():
        groups[(m['pool'], m['level'])].append(key)
    selected = set()
    for group, keys in sorted(groups.items()):
        selected.update(sorted(keys, key=lambda k: digest(['current_input_probe', k]))[:2])
        selected.add(max(keys, key=lambda k: (metadata[k]['media_count'], digest(k))))
    probes = []
    for key in sorted(selected):
        row = all_rows[key]; m = metadata[key]; start = time.monotonic()
        if m['pool'] == 'state':
            batch, receipt = encode_state_v2(processor, row['request'], task_prompt=row['task_prompt'],
                                             target=row['target'], end_turn=row['end_turn'])
        else:
            batch, receipt = encode(processor, row['request'], row['target'],
                                    task_prompt=row.get('task_prompt'), end_turn=row['end_turn'])
        if receipt['target_tokens'] != m['target_tokens']:
            raise ValueError('TARGET_TOKENIZER_PROCESSOR_MISMATCH')
        probes.append(dict(key=key, pool=m['pool'], level=m['level'], seconds=time.monotonic()-start, **receipt))
        del batch
    write(PREPARED/'catalog.jsonl', list(metadata.values()), True)
    write(PREPARED/'state_duplicate_aliases.jsonl', aliases, True)
    write(PREPARED/'processor_probe.jsonl', probes, True)
    result = dict(status='FROZEN_SUPERVISED_TOKEN_AND_UPDATE_BUDGET', job_id=os.environ['SLURM_JOB_ID'],
        methods=list(METHODS), seeds=list(SEEDS), runs=budgets, source_hashes=hashes,
        catalog_sha256=sha(PREPARED/'catalog.jsonl'), coverage_prefix_tokens=coverage,
        budget_rule='Round max required train coverage prefix across all arms/seeds up to 1024 target tokens per update.',
        exact_matching=['nonpadding_supervised_tokens', 'optimizer_updates'],
        not_matched=['input_tokens', 'total_processed_tokens', 'sample_exposure_count', 'walltime', 'FLOPs'],
        base_sampling='Same deterministic base-ID stream for balanced/CoT/PSS; different prefix lengths to match tokens.',
        state_ratio='PSS: alternate one answer event and one state event; full state level-balanced; L4-only restricted L4.',
        boundary_policy='Full targets kept; contiguous loss-token fragments may span update boundaries. No gold truncation.',
        final_checkpoint_policy='Fixed final budget; no test or dev score-based early stopping or checkpoint selection.',
        dev_policy='Describe dev sanity/loss only; no accuracy gate, no adaptive data or prompt tuning.',
        state_dedup='Identical actual state media/query/target kept once; all aliases preserved.',
        original_samples=13476, unique_worlds=len(worlds), catalog_records=len(metadata),
        unique_state_records=sum(m['pool']=='state' for m in metadata.values()),
        state_aliases=len(aliases), actual_processor_probes=len(probes), test_opened=False,
        limitations='Target-token matched, NOT full compute matched. CoT/state targets expose different evidence/granularity.',
        code_sha256=sha(__file__), core_sha256=sha(Path(__file__).with_name('core.py')))
    write(PREPARED/'BUDGET_PLAN.json', result)
    print({k: result[k] for k in ('status','catalog_records','actual_processor_probes','coverage_prefix_tokens')}, flush=True)
    print({k: {x: v[x] for x in ('optimizer_updates','supervised_tokens','examples_started')} for k,v in budgets.items()}, flush=True)


if __name__ == '__main__':
    main()
