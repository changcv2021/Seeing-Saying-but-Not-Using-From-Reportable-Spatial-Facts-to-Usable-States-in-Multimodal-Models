"""Immutable v3 overlay: reuse v2 parsing, frozen held-out inputs and exact metrics."""
import argparse
import collections
import csv
import datetime
import hashlib
import json
import os
import shutil
import statistics
from pathlib import Path
from policy_v3 import CODE, V2_CODE, VERSION, POLICY, parse_observed, v2_config
from common import load, unique, sha, write, metrics

PSS = v2_config.PSS
ROOT = PSS / 'label_rescore_v3'
METHODS = v2_config.METHODS + ('pss_full_l4_preserved',)
KEYS = v2_config.KEYS + tuple(f'pss_full_l4_preserved__seed_{s}' for s in (20260922, 20260923))
LEVELS = ('L1', 'L2', 'L3', 'L4', 'Overall')
RUN_ID = 'phase8_label_rescore_v3_20260925'
SEED = 20260925


def read(path):
    return json.loads(Path(path).read_text())


def jsonlines(path):
    with Path(path).open() as stream:
        for line, text in enumerate(stream, 1):
            if text.strip():
                yield line, json.loads(text)


def verify_manifest(directory):
    if sha(directory / 'MANIFEST.json') != read(directory / 'FREEZE.json')['manifest_sha256']:
        raise ValueError('MANIFEST_CHANGED:' + str(directory))
    manifest = read(directory / 'MANIFEST.json')
    for path, digest in manifest['code_hashes'].items():
        if sha(path) != digest:
            raise ValueError('FROZEN_CODE_CHANGED:' + path)
    return manifest


def freeze():
    if (ROOT / 'FREEZE.json').exists():
        raise FileExistsError('ALREADY_FROZEN')
    old = verify_manifest(PSS / 'label_rescore_v2')
    paths = sorted(CODE.glob('*.py')) + sorted(CODE.glob('*.sbatch')) + [CODE / 'POLICY_CN.md']
    hashes = dict(old['code_hashes'])
    hashes.update({str(p): sha(p) for p in paths})
    sources = {}
    for key in KEYS:
        prior = PSS / 'label_rescore_v2'
        if key.startswith('pss_full_l4_preserved__'):
            seed = int(key.rsplit('_', 1)[1])
            prior = PSS / 'pss_full_l4_preserved_v1/evaluation' / f'seed_{seed}' / 'label_rescore_v2'
        sources[key] = str(prior)
    audit = read(PSS / 'SPLIT_AUDIT.json')
    for name in ('gold', 'requests'):
        path = old[name + '_path']
        digest = sha(path)
        if digest != old[name + '_sha256'] or digest != audit['files'][str(Path(path).relative_to(PSS))]:
            raise ValueError('HELDOUT_DATA_CHANGED')
    manifest = dict(run_id=RUN_ID, policy=POLICY, keys=KEYS, prior_roots=sources,
        code_hashes=hashes, n=5608, worlds=old['worlds'],
        gold_path=old['gold_path'], gold_sha256=old['gold_sha256'],
        requests_path=old['requests_path'], requests_sha256=old['requests_sha256'],
        code_revision='SHA256_SNAPSHOT_NO_COMMIT_ASSERTED', seed=SEED,
        freeze_time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        job_id=os.environ['SLURM_JOB_ID'], status='FROZEN_BEFORE_V3_SCORING',
        pending_sources='Future v2 results are hash-sealed in per-model INPUT_RECEIPT before v3 scoring.',
        no_training=True, no_new_inference=True, no_gold_repair=True)
    for path in paths:
        target = ROOT / 'source_snapshot/v3' / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for path in (V2_CODE / 'label_policy.py', v2_config.LEGACY / 'common.py', v2_config.LEGACY / 'output_policy.py'):
        target = ROOT / 'source_snapshot/read_only_dependencies' / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    write(ROOT / 'MANIFEST.json', manifest)
    write(ROOT / 'FREEZE.json', dict(manifest_sha256=sha(ROOT / 'MANIFEST.json'), status='PASS'))
    print(json.dumps(dict(status='FROZEN', models=len(KEYS), n_each=5608)), flush=True)


def grouped(rows):
    return {level: metrics(rows if level == 'Overall' else [r for r in rows if r['level'] == level]) for level in LEVELS}


def score(index):
    if index not in range(len(KEYS)):
        raise ValueError('INVALID_INDEX')
    manifest = verify_manifest(ROOT)
    key = KEYS[index]
    output = ROOT / key
    if (output / 'RESULT.json').exists():
        raise FileExistsError('ALREADY_SCORED_NO_SELECTIVE_RETRY')
    old_root = Path(manifest['prior_roots'][key])
    old_manifest = verify_manifest(old_root)
    source = old_manifest['sources'][key]
    previous = read(old_root / key / 'RESULT.json')
    if previous['status'] != 'COMPLETE_VERSIONED_LABEL_RESCORING' or previous['n'] != 5608:
        raise ValueError('V2_RESULT_INCOMPLETE')
    input_hashes = {}
    for name in ('gold', 'requests'):
        path, digest = manifest[name + '_path'], manifest[name + '_sha256']
        if sha(path) != digest or old_manifest[name + '_sha256'] != digest:
            raise ValueError('TEST_CHANGED')
        input_hashes[path] = digest
    for name in ('original_report', 'original_scored'):
        if sha(source[name]) != source[name + '_sha256']:
            raise ValueError('HISTORICAL_RESULT_CHANGED')
        input_hashes[source[name]] = source[name + '_sha256']
    prior_path = old_root / key / 'scored_v2.jsonl'
    if sha(prior_path) != previous['output_hashes']['scored_v2.jsonl']:
        raise ValueError('V2_SCORED_CHANGED')
    for path in (prior_path, old_root / key / 'RESULT.json', old_root / 'MANIFEST.json', old_root / 'FREEZE.json'):
        input_hashes[str(path)] = sha(path)
    for path, digest in source['raw_hashes'].items():
        if sha(path) != digest:
            raise ValueError('RAW_CHANGED')
        input_hashes[path] = digest
    write(output / 'INPUT_RECEIPT.json', dict(key=key, input_hashes=input_hashes,
        freeze_sha256=sha(ROOT / 'FREEZE.json'), policy=VERSION, job_id=os.environ['SLURM_JOB_ID']))
    prior, gold = unique(load(prior_path)), unique(load(manifest['gold_path']))
    if len(gold) != 5608 or set(prior) != set(gold):
        raise ValueError('INCOMPLETE_HELDOUT_COVERAGE')
    rows, audits, seen = [], [], set()
    diag = collections.Counter()
    by_recovery_level = collections.defaultdict(collections.Counter)
    for path, digest in source['raw_hashes'].items():
        for line, raw in jsonlines(path):
            sid = raw['sample_id']
            if sid not in gold:
                if key == 'base_qwen35_9b':
                    continue
                raise ValueError('EXTRA_TEST_ID')
            if sid in seen:
                raise ValueError('DUPLICATE_PREDICTION')
            seen.add(sid)
            # This call has no access to gold or prior selected labels.
            parsed = parse_observed(raw)
            old, expected = prior[sid], gold[sid]
            if parsed['v2_label'] != old['label']:
                raise ValueError('V2_LABEL_NOT_EXACTLY_REPRODUCED:' + sid)
            for field in ('schema_valid', 'strict_json_valid', 'normalized_json_valid', 'confidence', 'reason'):
                if parsed[field] != old[field]:
                    raise ValueError('FORMAT_OR_AUXILIARY_FIELD_CHANGED:' + sid)
            for field in ('gold', 'level', 'pair_id', 'component'):
                if old[field] != expected[field]:
                    raise ValueError('GOLD_OR_PAIR_CHANGED:' + sid)
            if raw['config_sha256'] != source['config_sha256']:
                raise ValueError('CONFIG_CHANGED')
            if old['raw_response_sha256'] != hashlib.sha256(raw.get('raw_response', '').encode()).hexdigest():
                raise ValueError('RAW_RESPONSE_CHANGED')
            location = dict(path=path, line=line, file_sha256=digest)
            if old['raw_location'] != location:
                raise ValueError('RAW_LOCATION_CHANGED')
            row = dict(old, **parsed)
            rows.append(row)
            for field in ('schema_valid', 'strict_json_valid', 'normalized_json_valid'):
                diag[field] += bool(parsed[field])
            diag['v2_identified'] += parsed['v2_label'] is not None
            diag['v3_identified'] += parsed['label'] is not None
            diag['newly_recovered'] += parsed['label_recovered_v3']
            diag['runtime_errors'] += bool(raw.get('error'))
            diag['output_limit_hits'] += raw.get('finish_reason') == 'length'
            if parsed['recovery_reject']:
                diag['reject:' + parsed['recovery_reject']] += 1
            if parsed['label_recovered_v3']:
                kind = 'recovered_correct' if parsed['label'] == expected['gold'] else 'recovered_incorrect'
                diag[kind] += 1
                by_recovery_level[expected['level']][kind] += 1
            audits.append(dict(sample_id=sid, level=expected['level'], gold=expected['gold'],
                v2_label=parsed['v2_label'], v3_label=parsed['label'],
                recovered=parsed['label_recovered_v3'], label_evidence_span=parsed['label_evidence_span'],
                recovery_reject=parsed['recovery_reject'], v2_recovery_reject=parsed['v2_recovery_reject'],
                raw_location=location, raw_response_sha256=old['raw_response_sha256'],
                schema_valid=parsed['schema_valid']))
    if seen != set(gold):
        raise ValueError('MISSING_PREDICTIONS_NEVER_DROP_DENOMINATOR')
    groups = grouped(rows)
    old_groups = grouped([dict(r, label=r['v2_label']) for r in rows])
    for level in LEVELS:
        old = previous['overall']['corrected'] if level == 'Overall' else previous['by_level'][level]['corrected']
        if old_groups[level] != old:
            raise ValueError('V2_METRICS_NOT_EXACTLY_REPRODUCED:' + level)
        if groups[level]['complete_pairs'] != old['complete_pairs'] or groups[level]['n'] != old['n']:
            raise ValueError('DENOMINATOR_CHANGED')
    # Recheck historical inputs after scoring, not just on entry.
    if any(sha(path) != digest for path, digest in input_hashes.items()):
        raise ValueError('HISTORICAL_INPUT_MUTATED_DURING_SCORE')
    write(output / 'scored_v3.jsonl', rows, jsonl=True)
    write(output / 'label_audit.jsonl', audits, jsonl=True)
    result = dict(status='COMPLETE_UNIFORM_V3_LABEL_RESCORING', model=key, n=5608,
        worlds=manifest['worlds'], policy=VERSION, post_hoc_correction=True,
        by_level={level: dict(v2=old_groups[level], v3=groups[level],
            original=previous['overall']['old'] if level == 'Overall' else previous['by_level'][level]['old']) for level in LEVELS},
        diagnostics=dict(diag), recovery_by_level=dict(by_recovery_level), unresolved=5608-diag['v3_identified'],
        original_json_not_repaired=True, no_new_inference=True, no_reason_judge=True,
        checks=dict(v2_labels_exact=True, v2_metrics_exact=True, frozen_test_unchanged=True,
            original_inputs_hashes_unchanged=True, schema_reason_confidence_unchanged=True,
            all_5608_inputs_retained=True, complete_pair_denominator_unchanged=True),
        output_hashes={name: sha(output / name) for name in ('scored_v3.jsonl', 'label_audit.jsonl', 'INPUT_RECEIPT.json')},
        job_id=os.environ['SLURM_JOB_ID'], prior_result=str(old_root / key / 'RESULT.json'))
    write(output / 'RESULT.json', result)
    print(json.dumps(dict(model=key, diagnostics=result['diagnostics'], overall=groups['Overall'])), flush=True)


def summary(final=False):
    verify_manifest(ROOT)
    results = {k: read(ROOT / k / 'RESULT.json') for k in KEYS if (ROOT / k / 'RESULT.json').exists()}
    missing = [k for k in KEYS if k not in results]
    if final and missing:
        raise ValueError('FINAL_REQUIRES_ALL_13_RESULTS')
    for key, r in results.items():
        if r['status'] != 'COMPLETE_UNIFORM_V3_LABEL_RESCORING':
            raise ValueError('INCOMPLETE_SCORE')
        for name, digest in r['output_hashes'].items():
            if sha(ROOT / key / name) != digest:
                raise ValueError('SCORED_OUTPUT_CHANGED')
    output = ROOT / ('final' if final else 'available')
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for key, r in results.items():
        for level, g in r['by_level'].items():
            record = dict(model=key, level=level, n=g['v3']['n'], pairs=g['v3']['complete_pairs'])
            for metric in ('claim_accuracy', 'pair_accuracy', 'macro_f1', 'unknown_f1'):
                for version in ('original', 'v2', 'v3'):
                    record[metric + '_' + version] = g[version][metric]
            records.append(record)
    with (output / 'ALL_LEVELS_BEFORE_AFTER.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    aggregated = {}
    for method in METHODS:
        keys = [f'{method}__seed_{s}' for s in (20260922, 20260923)]
        if not all(k in results for k in keys):
            continue
        aggregated[method] = {level: {metric: dict(
            mean=statistics.mean(results[k]['by_level'][level]['v3'][metric] for k in keys),
            seed_sample_sd=statistics.stdev(results[k]['by_level'][level]['v3'][metric] for k in keys), n_seeds=2)
            for metric in ('claim_accuracy', 'pair_accuracy')} for level in LEVELS}
    lines = ['# Phase8：v3 统一标签重评分结果', '',
        f'已完成 {len(results)}/13 项（Base + 12 个训练模型）；每项同一 5,608 test inputs / 1,124 worlds。', '',
        '## 修复与边界', '',
        '完整且唯一的开头标签不再因后续缺少逗号而消失，例如 `{"label":"SUPPORTED"confidence:0.9...`。',
        '本次仅取消 v2 的标签闭合引号后字符限制；不从解释猜标签，保留额外 label 字段歧义拒绝规则。',
        '这是用户授权、一次冻结的事后评分修正，不是原始预注册结果；所有对照使用同一规则。',
        '不改 raw/gold/test，不重训练或推理，不改 JSON 合规/解释/confidence；未识别项仍计错。', '',
        '## Overall：修复前后', '',
        '| 模型 / seed | v2 ClaimAcc | v3 ClaimAcc | v2 PairAcc | v3 PairAcc | 新恢复 | 其中正确 | 仍未识别 | 原 schema 合规 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for key, r in results.items():
        g, d = r['by_level']['Overall'], r['diagnostics']
        lines.append(f'| {key} | {100*g["v2"]["claim_accuracy"]:.2f}% | {100*g["v3"]["claim_accuracy"]:.2f}% | '
            f'{100*g["v2"]["pair_accuracy"]:.2f}% | {100*g["v3"]["pair_accuracy"]:.2f}% | '
            f'{d["newly_recovered"]} | {d.get("recovered_correct",0)} | {r["unresolved"]} | {d["schema_valid"]}/5608 |')
    lines += ['', '## 每个模型 L1–L4（v3 ClaimAcc / PairAcc，%）', '',
              '| 模型 / seed | L1 | L2 | L3 | L4 | Overall |', '|---|---:|---:|---:|---:|---:|']
    for key, r in results.items():
        values = [f'{100*r["by_level"][level]["v3"]["claim_accuracy"]:.2f} / '
                  f'{100*r["by_level"][level]["v3"]["pair_accuracy"]:.2f}' for level in LEVELS]
        lines.append(f'| {key} | ' + ' | '.join(values) + ' |')
    lines += ['', '## 两 seed 均值 ± 样本标准差（ClaimAcc / PairAcc，%）', '',
              '| 方法 | L1 | L2 | L3 | L4 | Overall |', '|---|---:|---:|---:|---:|---:|']
    for method, group in aggregated.items():
        values = [' / '.join(f'{100*group[level][m]["mean"]:.2f} ± {100*group[level][m]["seed_sample_sd"]:.2f}'
                             for m in ('claim_accuracy', 'pair_accuracy')) for level in LEVELS]
        lines.append(f'| {method} | ' + ' | '.join(values) + ' |')
    lines += ['', '两个 seed 的 SD 不是 world-level 置信区间，不能据此宣称统计显著或因果增益。', '',
              '## Preserved-L4 与 PSS-L4 / 旧 Full PSS 比较', '']
    new_method = 'pss_full_l4_preserved'
    if new_method not in aggregated:
        lines += ['新方法两 seed 尚未齐，不报告其两 seed 均值/标准差。以下仅比较已完成的对应 seed。', '']
    for seed in (20260922, 20260923):
        new_key = f'{new_method}__seed_{seed}'
        if new_key not in results:
            continue
        lines += [f'### seed {seed}：v3 差值（新方法减对照，百分点）', '',
                  '| 对照 | Level | ClaimAcc Δ | PairAcc Δ |', '|---|---|---:|---:|']
        for method in ('answer_balanced', 'pss_l4', 'pss_full'):
            old_key = f'{method}__seed_{seed}'
            if old_key not in results:
                continue
            for level in LEVELS:
                new, old = results[new_key]['by_level'][level]['v3'], results[old_key]['by_level'][level]['v3']
                lines.append(f'| {method} | {level} | {100*(new["claim_accuracy"]-old["claim_accuracy"]):+.2f} | '
                             f'{100*(new["pair_accuracy"]-old["pair_accuracy"]):+.2f} |')
    lines += ['', '## 标签类型诊断：新方法与 PSS-L4 的召回率（%）', '',
              '| seed | Level | gold label | support | PSS-L4 Recall | Preserved-L4 Recall | Δ pp |',
              '|---|---|---|---:|---:|---:|---:|']
    for seed in (20260922, 20260923):
        nk, pk = f'{new_method}__seed_{seed}', f'pss_l4__seed_{seed}'
        if nk not in results or pk not in results:
            continue
        for level in LEVELS:
            for label, counts in results[nk]['by_level'][level]['v3']['per_label'].items():
                old = results[pk]['by_level'][level]['v3']['per_label'][label]
                lines.append(f'| {seed} | {level} | {label} | {counts["support"]} | '
                    f'{100*old["recall"]:.2f} | {100*counts["recall"]:.2f} | {100*(counts["recall"]-old["recall"]):+.2f} |')
    lines += ['', '## 验收与文件', '',
        '- 每条 v2 label 及每个 level 的 v2 指标精确重现；原始输入前后 hash 一致。',
        '- JSON/schema、reason、confidence 与 v2 逐条一致；所有样本及 complete pair 分母不变。',
        '- `../<model>/label_audit.jsonl`：逐样本恢复/拒绝、v2/v3 标签、gold、原始路径/行号/hash、字符区间。',
        '- `../<model>/INPUT_RECEIPT.json`：旧预测及评分文件的不可变来源 hash。',
        '- `../<model>/RESULT.json`：详细指标与验收布尔值；`ALL_LEVELS_BEFORE_AFTER.csv` 含严格原版/v2/v3。',
        '- `../FREEZE.json`、`../MANIFEST.json`、`../source_snapshot/`：规则与依赖冻结。',
        '- `SUMMARY.json`：全模型结果、两 seed 汇总；未齐的 seed 不填估计值。',
        '- 本轮没有运行解释 judge；不能把 ClaimAcc 修复当作解释分或视觉依据正确性证明。',
        '- 若新方法比较仍有增益/下降，新增跨上下文监督和更长训练长度同时变化，不能单独归因。', '',
        '待完成：' + (', '.join(missing) if missing else '无；全部 13 项完成。'), '',
        '## 复现命令（只能在 Slurm CPU allocation 上；已完成目录禁止覆盖）', '',
        '```bash', f'python "{CODE}/run_v3.py" score --index <0..12> --run-id {RUN_ID} --seed {SEED}',
        f'python "{CODE}/run_v3.py" summary --final --run-id {RUN_ID} --seed {SEED}', '```', '']
    (output / 'RESCORING_REPORT_CN.md').write_text('\n'.join(lines))
    write(output / 'SUMMARY.json', dict(status='COMPLETE' if not missing else 'PARTIAL_COMPLETED_MODELS_ONLY',
        completed=len(results), expected=13, missing=missing, policy=VERSION, by_method=aggregated, models=results,
        report=str(output / 'RESCORING_REPORT_CN.md'), job_id=os.environ['SLURM_JOB_ID']))
    write(output / 'ACCEPTANCE.json', dict(status='PASS_COMPLETED_MODELS', pending=missing,
        checks={k:r['checks'] for k,r in results.items()},
        outputs={name:sha(output/name) for name in ('ALL_LEVELS_BEFORE_AFTER.csv','RESCORING_REPORT_CN.md','SUMMARY.json')}))
    print(json.dumps(dict(completed=len(results), missing=missing, report=str(output / 'RESCORING_REPORT_CN.md'))), flush=True)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('stage', choices=('freeze', 'score', 'summary'))
    parser.add_argument('--index', type=int)
    parser.add_argument('--final', action='store_true')
    parser.add_argument('--run-id', default=RUN_ID)
    parser.add_argument('--seed', type=int, default=SEED)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if (args.run_id, args.seed, args.limit) != (RUN_ID, SEED, None):
        raise ValueError('PROTOCOL_MISMATCH')
    if args.dry_run:
        print(json.dumps(dict(policy=POLICY, keys=KEYS, root=str(ROOT))))
        return
    if not os.environ.get('SLURM_JOB_ID'):
        raise ValueError('SLURM_REQUIRED')
    if args.stage == 'freeze':
        freeze()
    elif args.stage == 'score':
        score(args.index if args.index is not None else int(os.environ['SLURM_ARRAY_TASK_ID']))
    else:
        summary(args.final)


if __name__ == '__main__':
    main()
