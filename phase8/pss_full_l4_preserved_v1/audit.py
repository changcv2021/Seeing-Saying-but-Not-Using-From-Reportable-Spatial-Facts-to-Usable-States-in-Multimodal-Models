"""Slurm CPU audit of ACTUAL old exposures and additive frozen schedules."""
import argparse
import collections
import os
from plan import *


def require(condition, message):
    if not condition:
        raise ValueError(message)


def record_type(meta):
    if meta['pool'] == 'answer':
        return 'ANSWER_' + meta['level']
    origin = 'TRAJECTORY_HISTORY' if '/trajectory_aux_v1/' in meta['source'] else 'GROUNDED_STATE'
    return '_'.join([meta['level'], origin, meta.get('stage') or 'UNSPECIFIED'])


def signature(receipt):
    return {k: receipt[k] for k in ('prompt_tokens', 'target_tokens', 'target_ids',
            'visual_inputs', 'prompt_payload_sha256', 'actual_task_prompt', 'processed_tensor_hashes')}


def split_audit(catalog, sources):
    frozen = read(ROOT / 'SPLIT_AUDIT.json')
    require(frozen['status'].startswith('PASS_'), 'APPROVED_SPLIT_NOT_PASS')
    for relative, expected in frozen['files'].items():
        require(sha(ROOT / relative) == expected, 'FROZEN_SPLIT_CHANGED:' + relative)
    canonical = {r['global_world_id']: r['underlying_world_id'] for r in rows(ROOT / 'data/world_groups.jsonl')}
    worlds, ids, media = {}, {}, {}
    for split in ('train', 'dev', 'test'):
        gold = list(rows(ROOT / 'data' / split / 'private_gold.jsonl'))
        requests = list(rows(ROOT / 'data' / split / 'requests.jsonl'))
        worlds[split] = {r['underlying_world_id'] for r in gold}
        ids[split] = {r['sample_id'] for r in gold}
        require(len(gold) == len(ids[split]) == frozen['samples'][split], 'SPLIT_SIZE')
        require(ids[split] == {r['sample_id'] for r in requests}, 'PUBLIC_GOLD_IDS')
        for r in gold:
            require(r['split'] == split and canonical[r['global_world_id']] == r['underlying_world_id'], 'ALIAS_MAPPING')
        media[split] = {str(Path(m['path']).resolve()) for r in requests for m in r.get('media', [])}
    for a, b in (('train', 'dev'), ('train', 'test'), ('dev', 'test')):
        require(not worlds[a] & worlds[b] and not ids[a] & ids[b], 'WORLD_OR_ID_LEAKAGE')
        require(not media[a] & media[b], 'EXACT_MEDIA_PATH_LEAKAGE')
    forbidden = media['dev'] | media['test']
    missing_nested_split = 0
    for key, meta in catalog.items():
        if meta['pool'] == 'cot':
            continue
        row = sources[key]
        require(row['split'] == 'train' and row['underlying_world_id'] in worlds['train'], 'AUX_NOT_TRAIN:' + key)
        require(canonical[row['global_world_id']] == row['underlying_world_id'], 'AUX_ALIAS_MAPPING:' + key)
        # Existing trajectory requests are inference payloads, not split records.
        # The authoritative outer record and world alias map were checked above.
        if 'split' in row['request']:
            require(row['request']['split'] == 'train', 'AUX_PUBLIC_SPLIT')
        else:
            missing_nested_split += 1
        require(not {str(Path(m['path']).resolve()) for m in row['request'].get('media', [])} & forbidden, 'AUX_MEDIA_LEAKAGE')
    return dict(status='PASS_APPROVED_WORLD_ALIAS_AND_MEDIA_ISOLATION',
        approved_audit_sha256=sha(ROOT / 'SPLIT_AUDIT.json'),
        world_alias_map_sha256=sha(ROOT / 'data/world_groups.jsonl'),
        input_hashes=frozen['files'], worlds={s: len(v) for s, v in worlds.items()},
        samples={s: len(v) for s, v in ids.items()}, test_payload_unchanged=True,
        alias_policy=frozen['known_alias_policy'], limitations=frozen['limitations'],
        nested_requests_without_split=missing_nested_split,
        missing_nested_split_policy='require outer train split, approved canonical world map, frozen source hash, and no dev/test media')


def verify_actual(method, seed, units, catalog, receipts):
    run = OLD_OUTPUT / 'runs' / f'{method}__seed_{seed}'
    complete = read(run / 'TRAINING_COMPLETE.json')
    require(complete['status'] == 'COMPLETE_FIXED_UPDATE_BUDGET', 'OLD_TRAINING_NOT_COMPLETE')
    expected = {(i, key): (u['sample_id'], weight) for i, u in enumerate(units) for key, weight in u['records']}
    seen = set(); totals = collections.Counter(); hashes = {}; steps = collections.Counter()
    for path in sorted((run / 'attempts').glob('*/updates_rank_*.jsonl')):
        hashes[str(path)] = sha(path)
        rank = int(path.stem.rsplit('_', 1)[1])
        for update in rows(path):
            require((rank, update['step']) not in steps, 'DUPLICATE_COMMITTED_UPDATE')
            steps[(rank, update['step'])] += 1
            for r in update['receipts']:
                index = r['index']; marker = (index, r['key'])
                require(marker not in seen and marker in expected, 'ACTUAL_EXPOSURE_DUPLICATE_OR_EXTRA')
                require(expected[marker] == (r['sample_id'], r['weight']), 'ACTUAL_SAMPLER_WEIGHT_MISMATCH')
                require(index // 16 + 1 == update['step'] and index % 2 == rank, 'ACTUAL_STEP_OR_RANK')
                require(r['target_tokens'] == catalog[r['key']]['target_tokens'], 'TARGET_TOKENS_CHANGED')
                value = signature(r)
                if r['key'] in receipts:
                    require(receipts[r['key']] == value, 'PROCESSOR_RECEIPT_NOT_STABLE:' + r['key'])
                else:
                    receipts[r['key']] = value
                totals['input_tokens'] += r['prompt_tokens']
                totals['target_tokens'] += r['target_tokens']
                totals['non_padding_tokens'] += r['prompt_tokens'] + r['target_tokens']
                totals['forward_records'] += 1
                seen.add(marker)
    require(seen == set(expected), 'OLD_LOGS_NOT_COMPLETE')
    require(set(steps) == {(rank, step) for rank in (0, 1) for step in range(1, 2238)}, 'OLD_STEP_COVERAGE')
    for field, value in [('processed_tokens', totals['non_padding_tokens']), ('supervised_tokens', totals['target_tokens']),
                         ('forward_records', totals['forward_records']), ('step', 2237), ('base_examples', 35792)]:
        require(complete['progress'][field] == value, 'OLD_COMPLETE_RECEIPT_MISMATCH:' + field)
    hashes[str(run / 'TRAINING_COMPLETE.json')] = sha(run / 'TRAINING_COMPLETE.json')
    return dict(status='EXACT_MATCH_TO_ACTUAL_TWO_RANK_LOGS', totals=dict(totals), input_hashes=hashes)


def summarize(units, catalog, receipts):
    counts = collections.Counter(); weights = collections.Counter()
    for u in units:
        for key, weight in u['records']:
            counts[key] += 1; weights[key] += weight
    groups = collections.defaultdict(list)
    for key in counts:
        groups[record_type(catalog[key])].append(key)
    detail = {}
    for label, keys in sorted(groups.items()):
        eligible = sum(record_type(m) == label for m in catalog.values() if m['pool'] != 'cot')
        detail[label] = dict(unique_samples=len(keys), eligible_unique_samples=eligible,
            sample_exposures=sum(counts[k] for k in keys), loss_weight_exposure=sum(weights[k] for k in keys),
            input_tokens=sum(counts[k] * receipts[k]['prompt_tokens'] for k in keys),
            target_tokens=sum(counts[k] * receipts[k]['target_tokens'] for k in keys),
            non_padding_tokens=sum(counts[k] * (receipts[k]['prompt_tokens'] + receipts[k]['target_tokens']) for k in keys),
            epoch_equivalent_over_eligible_pool=sum(counts[k] for k in keys) / eligible)
    return dict(supervision_types=detail, primary_units=len(units), optimizer_updates=len(units)//16,
        effective_batch_size=16, micro_batch_sequences_per_rank=2, ddp_ranks=2,
        gradient_accumulation='8 primary units/rank; 4-8 micro-batches/rank depending on auxiliary presence; unchanged per-unit mean loss',
        primary_epoch_equivalent=len(units)/13476,
        unique_primary_samples=len({u['sample_id'] for u in units}),
        forward_records=sum(counts.values()),
        input_tokens=sum(v['input_tokens'] for v in detail.values()),
        target_tokens=sum(v['target_tokens'] for v in detail.values()),
        non_padding_tokens=sum(v['non_padding_tokens'] for v in detail.values()),
        per_key_exposures=dict(counts), per_key_loss_weight_exposures=dict(weights))


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.dry_run:
        print(OUTPUT / 'audit'); return
    require(bool(os.environ.get('SLURM_JOB_ID')), 'SLURM_REQUIRED')
    out = OUTPUT / 'audit'
    require(not out.exists(), 'PRESERVE_EXISTING_AUDIT')
    original = read(OLD_OUTPUT / 'PLAN.json')
    for name in ('samples', 'catalog'):
        require(sha(OLD_OUTPUT / (name + '.json')) == original[name + '_sha256'], 'OLD_CATALOG_CHANGED')
    for path, expected in original['source_hashes'].items():
        require(sha(path) == expected, 'OLD_SOURCE_CHANGED:' + path)
    samples, catalog = read(OLD_OUTPUT / 'samples.json'), read(OLD_OUTPUT / 'catalog.json')
    wanted = collections.defaultdict(dict)
    for key, meta in catalog.items():
        wanted[meta['source']][meta['line']] = key
    sources = {}
    for path, mapping in wanted.items():
        for number, row in enumerate(rows(path)):
            if number in mapping:
                sources[mapping[number]] = row
    require(set(sources) == set(catalog), 'CATALOG_RECORD_MAPPING')
    split = split_audit(catalog, sources)
    receipts, audits, schedules = {}, {}, {}
    for seed in SEEDS:
        schedule = old.ExampleSchedule(samples, seed, True)
        prior = {}
        for method in ('pss_l4', 'pss_full'):
            units = [dict(sample_id=schedule.at(i), source_index=i,
                     records=old.unit_records(samples, schedule.at(i), method, seed, i)) for i in range(35792)]
            actual = verify_actual(method, seed, units, catalog, receipts)
            prior[method] = units
            audits[f'{method}__seed_{seed}'] = dict(actual=actual, exposure=summarize(units, catalog, receipts))
        base = [dict(u, stream='preserved_l4') for u in prior['pss_l4']]
        additions = []
        for unit in prior['pss_full']:
            state = [key for key, weight in unit['records'] if catalog[key]['pool'] == 'state']
            if state and catalog[state[0]]['level'] in ('L1', 'L3'):
                additions.append(dict(unit, stream='added_l1_l3_alignment', batch_padding_duplicate=False))
        combined, padding = interleave(base, additions)
        new = summarize(combined, catalog, receipts)
        before = audits[f'pss_l4__seed_{seed}']['exposure']
        l4keys = [k for k in before['per_key_exposures'] if catalog[k]['pool'] == 'state' and catalog[k]['level'] == 'L4']
        require(bool(l4keys), 'NO_OLD_L4_SUPERVISION')
        for k in l4keys:
            require(new['per_key_exposures'][k] == before['per_key_exposures'][k], 'L4_EXPOSURE_CHANGED:' + k)
            require(new['per_key_loss_weight_exposures'][k] == before['per_key_loss_weight_exposures'][k], 'L4_WEIGHT_DILUTED:' + k)
        require(new['optimizer_updates'] > 2237, 'NO_ADDITIONAL_UPDATES')
        stage_counts = lambda exposure: {stage: sum(n for k, n in exposure['per_key_exposures'].items()
            if catalog[k]['pool'] == 'state' and catalog[k]['level'] == 'L4' and catalog[k]['stage'] == stage) for stage in ('S0', 'S1', 'S2')}
        alignment = {level: sum(n for k, n in new['per_key_exposures'].items()
            if catalog[k]['pool'] == 'state' and catalog[k]['level'] == level) for level in ('L1', 'L3')}
        audits[f'{METHOD}__seed_{seed}'] = dict(exposure=new, l4_preservation='PASS_EXACT_PER_KEY_COUNTS_AND_WEIGHTS',
            l4_before=stage_counts(before), l4_after=stage_counts(new), l1_l3_alignment_exposures=alignment,
            added_units_before_batch_padding=len(additions), added_padding_units=padding,
            warmup_steps=math.ceil(new['optimizer_updates'] * original['warmup_fraction']),
            lr_schedule='same 3% ceil warmup and linear decay, recalculated for new total updates',
            source_selection='All actual Full-PSS L1/L3 auxiliary occurrences for corresponding seed, with original same-world answer/state weights; no L2 additions')
        schedules[seed] = combined
    out.mkdir(parents=True)
    write(out / 'SPLIT_CHECK.json', split)
    for seed, units in schedules.items():
        write(out / f'units_{seed}.json', units)
    used = {key for units in schedules.values() for u in units for key, _ in u['records']}
    write(out / 'processor_receipts.json', {k: receipts[k] for k in sorted(used)})
    write(out / 'EXPOSURE_AUDIT.json', dict(status='PASS_BEFORE_TRAINING', job_id=os.environ['SLURM_JOB_ID'],
        audits=audits, preserved_unit_order=True, canonical_serialization_unchanged=True,
        token_measurement='Exact historical actual-processor receipts for the identical record keys, checked against completed rank logs; new training revalidates receipts',
        input_hashes={str(OLD_OUTPUT / 'PLAN.json'): sha(OLD_OUTPUT / 'PLAN.json'), **original['source_hashes']},
        limitations=['Added L1/L3 canonical state supervision is reused, not a newly introduced contrastive alignment loss.',
                    'Not every L1 state record is multiview; no claim that all added items independently prove cross-context alignment.',
                    'Extra same-world answer exposures and longer training are intentional and remain causal confounds versus old PSS-L4.']))
    lines = ['# Preserved-L4：训练前数据与实际 exposure 审计', '',
        '状态：PASS。原 PSS-L4 与 Full PSS 的两个 rank 日志已逐样本重放核对；不是仅比较配置。', '',
        '新实验保留每个原始 PSS-L4 batch、样本顺序、每条 L4 状态题次数和 loss 权重。额外批次复用旧 Full PSS 实际抽中的 L1/L3 状态题及同 world 答案，answer/state 各 0.5。只为新批次补齐最多 15 个额外 L1/L3 单位，不改 L4。', '',
        '| 配置 | seed | 更新步数 | primary units | input tokens | target tokens | non-padding tokens | primary epoch-equivalent |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for key, entry in audits.items():
        e=entry['exposure']; method,seed=key.split('__seed_')
        lines.append(f'| {method} | {seed} | {e["optimizer_updates"]} | {e["primary_units"]} | {e["input_tokens"]} | {e["target_tokens"]} | {e["non_padding_tokens"]} | {e["primary_epoch_equivalent"]:.4f} |')
    lines += ['', '所有配置 effective batch = 16 原始样本单位；2 ranks；micro batch 每 rank 2 条序列；按每 rank 8 个单位累积，实际 4–8 个 micro-batches。input tokens 含实际处理后的视觉 token，但不含 target；non-padding = input + target。', '']
    for key, entry in audits.items():
        lines += ['## '+key, '', '| 监督类型 | pool 唯一数 | 实际唯一数 | 实际 exposures | loss-weight exposures | input tokens | target tokens | non-padding tokens | pool epoch-equivalent |',
                  '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        for kind, d in entry['exposure']['supervision_types'].items():
            lines.append(f'| {kind} | {d["eligible_unique_samples"]} | {d["unique_samples"]} | {d["sample_exposures"]} | {d["loss_weight_exposure"]} | {d["input_tokens"]} | {d["target_tokens"]} | {d["non_padding_tokens"]} | {d["epoch_equivalent_over_eligible_pool"]:.4f} |')
        if 'l4_before' in entry:
            lines += ['', 'L4 保留验证：`'+entry['l4_preservation']+'`；S0/S1/S2 原值与新值：`'+json.dumps(entry['l4_before'])+'` / `'+json.dumps(entry['l4_after'])+'`。',
                '新增 L1/L3 exposures：`'+json.dumps(entry['l1_l3_alignment_exposures'])+'`；warmup steps：'+str(entry['warmup_steps'])+'。']
        lines.append('')
    lines += ['## 解释边界', '',
        'L1/L3 alignment 指复用原 Full PSS 的 canonical state 辅助监督，不新增 contrastive loss，也不把所有 L1 单视图题伪称多视图题。新增单位同时包含原定义的答案监督；更长训练和额外答案 exposure 是本实验的伴随变化，不能仅据性能差异排除其贡献。', '',
        '沿用 approved_v2 的 source/physical-space/exact-media alias 隔离；train/dev/test = 13,476 / 3,267 / 5,608，test 原文件 hash 未变。未获得官方 physical identity 的来源仍保留原审计限制。', '',
        '完整逐 key 曝光在 EXPOSURE_AUDIT.json；冻结顺序在 units_<seed>.json；历史实际 processor token/hash 回执在 processor_receipts.json。所有旧数据只读。']
    (out / 'DATASET_EXPOSURE_AUDIT_CN.md').write_text('\n'.join(lines)+'\n')
    write(out / 'AUDIT_COMPLETE.json', dict(status='PASS', files={str(p): sha(p) for p in out.iterdir() if p.is_file()}))
    print(json.dumps({k: {field: v[field] for field in ('l4_before', 'l4_after', 'l1_l3_alignment_exposures', 'warmup_steps') if field in v}
                      | {'updates': v['exposure']['optimizer_updates']} for k, v in audits.items()}), flush=True)


if __name__ == '__main__':
    main()
