"""CPU-only freeze, blind parsing, exact rescoring and paired reports."""
import collections
import csv
import datetime
import hashlib
import os
import shutil
import statistics
from config import *
from label_policy import POLICY, VERSION, parse_observed


def jsonlines(path):
    with Path(path).open() as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                yield number, json.loads(line)


def prepare():
    if (ROOT / 'FREEZE.json').exists():
        raise FileExistsError('ALREADY_FROZEN')
    summary = read(TEN)
    if summary['complete'] != 10 or summary['status'] != 'COMPLETE':
        raise ValueError('TEN_PREVIOUS_EVALUATIONS_NOT_COMPLETE')
    audit = read(PSS / 'SPLIT_AUDIT.json')
    gold_path, requests_path = PSS / 'data/test/private_gold.jsonl', PSS / 'data/test/requests.jsonl'
    for p in (gold_path, requests_path):
        if sha(p) != audit['files'][str(p.relative_to(PSS))]:
            raise ValueError('FROZEN_TEST_CHANGED')
    gold, requests = unique(load(gold_path)), unique(load(requests_path))
    if len(gold) != 5608 or set(gold) != set(requests) or any(r['split'] != 'test' for r in gold.values()):
        raise ValueError('NOT_THE_COMPLETE_HELDOUT_TEST')
    sources = {}
    for key in KEYS:
        source = BASE if key == KEYS[0] else Path(summary['paths'][key])
        report_path = source / ('full_score_with_identity.json' if key == KEYS[0] else 'TEST_RESULT.json')
        report = read(report_path)
        if key != KEYS[0] and report['status'] != 'COMPLETE_HELDOUT_TEST':
            raise ValueError('SOURCE_INCOMPLETE:' + key)
        files = sorted((source / 'full').glob('predictions_*.jsonl'))
        if len(files) != 4:
            raise ValueError('EXPECTED_FOUR_CANONICAL_SHARDS:' + key)
        hashes = {}
        for p in files:
            digest = sha(p)
            if digest != report['input_hashes'][str(p)]:
                raise ValueError('ORIGINAL_PREDICTION_CHANGED:' + str(p))
            hashes[str(p)] = digest
        sources[key] = dict(directory=str(source), raw_hashes=hashes,
             original_report=str(report_path), original_report_sha256=sha(report_path),
             original_scored=str(source / 'full_scored.jsonl'),
             original_scored_sha256=sha(source / 'full_scored.jsonl'),
             config_sha256=sha(source / 'config.json'), expected_test_inputs=5608)
    paths = list(CODE.glob('*.py')) + list(CODE.glob('*.sbatch')) + [CODE / 'POLICY_CN.md']
    paths += [LEGACY / 'common.py', LEGACY / 'output_policy.py']
    code_hashes = {str(p): sha(p) for p in paths}
    for p in paths:
        target = ROOT / 'source_snapshot' / ('legacy' if p.parent == LEGACY else 'v2') / p.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
    write(ROOT / 'POLICY.json', POLICY)
    manifest = dict(run_id=RUN_ID, status='FROZEN_BEFORE_REVISED_SCORING', policy=POLICY,
         time=datetime.datetime.now(datetime.timezone.utc).isoformat(), sources=sources, keys=KEYS,
         code_hashes=code_hashes, source_revision='REUSE_FROZEN_QWEN35_9B_OUTPUTS',
         code_commit='FILE_HASH_PROVENANCE_NO_COMMIT_ASSERTED', random_seed=SEED,
         gold_path=str(gold_path), gold_sha256=sha(gold_path), requests_path=str(requests_path),
         requests_sha256=sha(requests_path), n_test=5608,
         worlds=len({r['underlying_world_id'] for r in gold.values()}),
         baseline_input_policy='Select identical frozen test IDs, never all-split baseline score',
         no_new_inference=True, no_training_changes=True, no_gold_based_repair=True,
         auxiliary_judge='NOT_RUN', job_id=os.environ['SLURM_JOB_ID'])
    write(ROOT / 'MANIFEST.json', manifest)
    write(ROOT / 'FREEZE.json', dict(status='PASS', manifest_sha256=sha(ROOT / 'MANIFEST.json')))
    print(json.dumps(dict(status='FROZEN', models=len(KEYS), n_each=5608)), flush=True)


def score(index):
    if index not in range(len(KEYS)):
        raise ValueError('INVALID_MODEL_INDEX')
    manifest = verify()
    key = KEYS[index]
    source = manifest['sources'][key]
    output = ROOT / key
    if (output / 'RESULT.json').exists():
        raise FileExistsError('ALREADY_SCORED_NO_SELECTIVE_RETRY')
    for path_key, hash_key in (('gold_path', 'gold_sha256'), ('requests_path', 'requests_sha256')):
        if sha(manifest[path_key]) != manifest[hash_key]:
            raise ValueError('TEST_CHANGED')
    for name in ('original_report', 'original_scored'):
        if sha(source[name]) != source[name + '_sha256']:
            raise ValueError('OLD_RESULT_CHANGED')
    gold = unique(load(manifest['gold_path']))
    prior = {r['sample_id']: r for _, r in jsonlines(source['original_scored']) if r['sample_id'] in gold}
    if set(prior) != set(gold):
        raise ValueError('PRIOR_TEST_COVERAGE')
    rows, parsed_rows, indices, seen = [], [], [], set()
    diag = collections.Counter()
    for path, digest in source['raw_hashes'].items():
        if sha(path) != digest:
            raise ValueError('RAW_CHANGED')
        for line, raw in jsonlines(path):
            sid = raw['sample_id']
            if sid not in gold:
                if index == 0:
                    continue
                raise ValueError('EXTRA_TEST_ID')
            if sid in seen:
                raise ValueError('DUPLICATE_PREDICTION_ID')
            seen.add(sid)
            # Parsing is completed before any expected-label lookup/comparison.
            parsed = parse_observed(raw)
            expected, old = gold[sid], prior[sid]
            if parsed['legacy_label'] != old['label']:
                raise ValueError('LEGACY_SCORE_NOT_EXACTLY_REPRODUCED:' + sid)
            if any(old[k] != expected[k] for k in ('gold', 'level', 'pair_id', 'component')):
                raise ValueError('GOLD_OR_PAIR_MISMATCH')
            if raw['config_sha256'] != source['config_sha256']:
                raise ValueError('PREDICTION_CONFIGURATION_CHANGED')
            row = dict(expected, **parsed, runtime_error=raw.get('error'),
                 raw_location=dict(path=path, line=line, file_sha256=digest),
                 raw_response_sha256=hashlib.sha256(raw.get('raw_response', '').encode()).hexdigest(),
                 generated_tokens=raw.get('generated_tokens'), finish_reason=raw.get('finish_reason'))
            rows.append(row)
            diag['complete_schema_valid'] += bool(parsed['schema_valid'])
            diag['strict_json_valid'] += bool(parsed['strict_json_valid'])
            diag['normalized_json_valid'] += bool(parsed['normalized_json_valid'])
            diag['legacy_label_identified'] += parsed['legacy_label'] is not None
            diag['label_identified_v2'] += parsed['label'] is not None
            diag['labels_recovered'] += parsed['label_recovered_v2']
            diag['runtime_errors'] += bool(raw.get('error'))
            diag['output_limit_hits'] += raw.get('finish_reason') == 'length'
            if parsed['recovery_reject']:
                diag['reject:' + parsed['recovery_reject']] += 1
            # No edited/synthetic response string is emitted as a model output.
            parsed_rows.append(dict(sample_id=sid, legacy_label=parsed['legacy_label'],
                  label=parsed['label'], source=parsed['label_source'],
                  label_evidence_span=parsed['label_evidence_span'],
                  recovery_reject=parsed['recovery_reject'], schema_valid=parsed['schema_valid'],
                  raw_location=row['raw_location'], raw_response_sha256=row['raw_response_sha256']))
        indices.append(dict(path=path, sha256=digest))
    if seen != set(gold):
        raise ValueError('MISSING_PREDICTIONS_NEVER_DROP_DENOMINATOR')
    old_rows = [dict(r, label=r['legacy_label']) for r in rows]
    by_level = {level: dict(old=metrics([r for r in old_rows if r['level'] == level]),
                           corrected=metrics([r for r in rows if r['level'] == level]))
                for level in ('L1', 'L2', 'L3', 'L4')}
    result = dict(status='COMPLETE_VERSIONED_LABEL_RESCORING', model=key, n=5608, worlds=manifest['worlds'],
          policy_version=VERSION, policy_sha256=sha(CODE / 'label_policy.py'), post_hoc_correction=True,
          overall=dict(old=metrics(old_rows), corrected=metrics(rows)), by_level=by_level,
          diagnostics=dict(diag), unresolved=5608-diag['label_identified_v2'],
          original_json_not_repaired=True, original_predictions_unchanged=True,
          original_report=source['original_report'], raw_index=indices, gold_sha256=manifest['gold_sha256'],
          auxiliary_judge='NOT_RUN_NO_REASON_INVENTED', job_id=os.environ['SLURM_JOB_ID'])
    write(output / 'scored_v2.jsonl', rows, jsonl=True)
    write(output / 'label_audit.jsonl', parsed_rows, jsonl=True)
    result['output_hashes'] = {name: sha(output / name) for name in ('scored_v2.jsonl', 'label_audit.jsonl')}
    write(output / 'RESULT.json', result)
    print(json.dumps(result), flush=True)


def summary():
    manifest = verify()
    results = {k: read(ROOT / k / 'RESULT.json') for k in KEYS}
    if any(r['status'] != 'COMPLETE_VERSIONED_LABEL_RESCORING' or r['n'] != 5608 for r in results.values()):
        raise ValueError('REVISED_SCORING_INCOMPLETE')
    baseline = results[KEYS[0]]
    records = []
    for k, result in results.items():
        for level in ('L1', 'L2', 'L3', 'L4', 'Overall'):
            score_pair = result['overall'] if level == 'Overall' else result['by_level'][level]
            base = baseline['overall']['corrected'] if level == 'Overall' else baseline['by_level'][level]['corrected']
            row = dict(model=k, level=level, n=score_pair['corrected']['n'], pairs=score_pair['corrected']['complete_pairs'])
            for metric in ('claim_accuracy', 'pair_accuracy', 'macro_f1', 'unknown_f1'):
                before, after = score_pair['old'][metric], score_pair['corrected'][metric]
                row.update({metric + '_old_parser': before, metric + '_v2': after})
                if metric in ('claim_accuracy', 'pair_accuracy'):
                    row[metric + '_delta_base_pp'] = 100 * (after-base[metric])
            records.append(row)
    with (ROOT / 'ALL_LEVELS_BEFORE_AFTER.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    aggregated = {}
    for method in METHODS:
        seeds = [results[f'{method}__seed_{s}'] for s in (20260922, 20260923)]
        aggregated[method] = {}
        for level in ('L1', 'L2', 'L3', 'L4', 'Overall'):
            metrics_list = [r['overall']['corrected'] if level == 'Overall' else r['by_level'][level]['corrected'] for r in seeds]
            aggregated[method][level] = {m: dict(mean=statistics.mean(r[m] for r in metrics_list),
                      seed_sample_sd=statistics.stdev(r[m] for r in metrics_list), n_seeds=2)
                      for m in ('claim_accuracy', 'pair_accuracy')}
    lines = ['# Phase8：十模型输出接口修复与统一重评分', '',
             '状态：十项训练模型及同一 held-out test 的 base 均已完成新规则重评分。',
             '每项 5,608 输入 / 1,124 worlds；不重推理、不重训、不改 gold、原始输出或旧评分。', '',
             '## 修复内容与边界', '',
             '训练 answer-only target 是未闭合的 label 前缀；旧评分器仅在达到 512-token 上限时恢复前缀，正常 EOS 的同类输出被漏计。',
             'v2 接受已有严格解析结果，或回答开头完整、唯一的 quoted label 字段；正常 EOS/stop 与 length 一视同仁。',
             '无标签、部分标签、多个 label 字段、仅在解释中提及标签等不补猜。JSON 合规、confidence、reason 不伪造。',
             '**这是看到接口问题后、用户授权的事后评分协议修正，不是原始预注册结果。** 新旧分数并列，所有十项及基线应用同一规则。',
             '不能把标签恢复率称作 JSON 合规率，也不能据此宣称已修复模型生成完整 JSON 的能力。', '',
             '## Overall 结果', '',
             '| 模型 / seed | 原 ClaimAcc | 修正 ClaimAcc | 原 PairAcc | 修正 PairAcc | 可识别标签 | 原完整 JSON |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for k in KEYS:
        r = results[k]
        old, new, d = r['overall']['old'], r['overall']['corrected'], r['diagnostics']
        lines.append(f'| {k} | {100*old["claim_accuracy"]:.2f}% | {100*new["claim_accuracy"]:.2f}% | '
                     f'{100*old["pair_accuracy"]:.2f}% | {100*new["pair_accuracy"]:.2f}% | '
                     f'{d["label_identified_v2"]}/5608 | {d["complete_schema_valid"]}/5608 |')
    lines += ['', '## L1–L4（两个训练 seeds 的均值；ClaimAcc / PairAcc，%）', '',
              '| 方法 | L1 | L2 | L3 | L4 | Overall |', '|---|---:|---:|---:|---:|---:|']
    for method, group in aggregated.items():
        values = [f'{100*group[level]["claim_accuracy"]["mean"]:.2f} / {100*group[level]["pair_accuracy"]["mean"]:.2f}'
                  for level in ('L1', 'L2', 'L3', 'L4', 'Overall')]
        lines.append(f'| {method} | ' + ' | '.join(values) + ' |')
    lines += ['', '## 验收与复现', '',
              '- 原始预测 hash 与原评分记录逐文件匹配；旧逐题 label 必须全部精确重现，否则停止。',
              '- 新解析函数只接收原始输出、终止原因、token 数和运行错误；gold/模型身份不影响解析，有对应单元测试。',
              '- 评分保留所有样本和原 complete pairs 分母；不能识别的输出仍计错。',
              '- 新规则单次冻结后统一应用，不按测试准确率修改；没有重新生成任何答案。',
              '- 解释 rubric judge 未运行；未补造 confidence 或 reason，也未用标签恢复冒充解释分。',
              '- 原 JSON 合规仍很低；若未来要求模型生成完整 JSON，需要独立的 dev 接口校准/训练目标修正，不能根据 test 调提示。',
              '- `ALL_LEVELS_BEFORE_AFTER.csv`：逐 seed / level 新旧指标及同规则 baseline 差值。',
              '- 各模型 `label_audit.jsonl` / `scored_v2.jsonl`：原始文件/行号、hash、恢复字符区间、拒绝原因、逐题新旧 label。',
              '- `MANIFEST.json` / `FREEZE.json` / `source_snapshot/`：数据、旧代码、新规则 hash 和一次性冻结记录。',
              '- `SUMMARY.json`：所有 seeds 与方法均值/seed 标准差；seed SD 不是 world-level CI。', '']
    (ROOT / 'RESCORING_REPORT_CN.md').write_text('\n'.join(lines))
    write(ROOT / 'SUMMARY.json', dict(status='COMPLETE_UNIFORM_POST_HOC_RESCORING', trained_models=10,
          baseline_models=1, n_each=5608, policy_version=VERSION, by_method=aggregated,
          models={k: dict(overall=r['overall'], diagnostics=r['diagnostics'], unresolved=r['unresolved']) for k, r in results.items()},
          report=str(ROOT / 'RESCORING_REPORT_CN.md'), csv_sha256=sha(ROOT / 'ALL_LEVELS_BEFORE_AFTER.csv')))
    print(json.dumps(dict(status='COMPLETE', report=str(ROOT / 'RESCORING_REPORT_CN.md'))), flush=True)


def main():
    args = parser(__doc__).parse_args()
    if (args.run_id, args.seed, args.limit) != (RUN_ID, SEED, None):
        raise ValueError('PROTOCOL_MISMATCH')
    if args.dry_run:
        print(json.dumps(dict(stage=args.stage, keys=KEYS, policy=POLICY)))
        return
    if not os.environ.get('SLURM_JOB_ID'):
        raise ValueError('SLURM_REQUIRED')
    if args.stage == 'prepare':
        prepare()
    elif args.stage == 'score':
        score(args.index if args.index is not None else int(os.environ['SLURM_ARRAY_TASK_ID']))
    else:
        summary()


if __name__ == '__main__':
    main()
