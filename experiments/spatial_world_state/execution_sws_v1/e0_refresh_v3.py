"""Immutable E0 refresh from existing full-benchmark outputs; zero model calls."""
from collections import Counter, defaultdict
from itertools import combinations
import sys

from common_auto_v2 import *
from e0_snapshot import module, interval
from snapshot_store_v2 import frozen_predictions
from world_identity_v2 import checked_overlay, unique

VERSION = 'e0_refresh_20260910_v3'
ENDPOINTS = ('ClaimAcc', 'BinaryClaimAcc', 'ContradictoryRecall', 'UnknownRecall', 'WorldMacroAcc', 'PairAcc')


def parsers(project):
    old = project / 'scripts/full_multimodel_20260908_v1'
    legacy = module(old / 'common.py', 'e0_v3_legacy')
    keep = sys.modules['common']
    sys.modules['common'] = legacy
    try:
        policy = module(old / 'output_policy.py', 'e0_v3_policy')
    finally:
        sys.modules['common'] = keep
    return legacy, policy, old


def cells(records):
    result = defaultdict(list)
    for r in records:
        for key in [('OVERALL', 'ALL'), ('LEVEL', r['level']), ('SOURCE', r['dataset']),
                    ('TRACK', r.get('track') or 'NOT_ANNOTATED'), ('SOURCE_SPLIT', r['split']), ('GOLD_LABEL', r['gold'])]:
            result[key].append(r)
    return result


def endpoint_values(records, metric):
    byworld = defaultdict(list)
    if metric == 'PairAcc':
        pairs = defaultdict(list)
        for r in records:
            if r['component'] == 'binary':
                pairs[r['pair_id']].append(r)
        for pair in pairs.values():
            if len(pair) == 2 and {r['gold'] for r in pair} == {'SUPPORTED', 'CONTRADICTORY'}:
                if len({r['world_cluster_id'] for r in pair}) != 1:
                    raise ValueError('PAIR_WORLD_MISMATCH')
                byworld[pair[0]['world_cluster_id']].append(int(all(r['correct'] for r in pair)))
    else:
        for r in records:
            if metric == 'BinaryClaimAcc' and r['component'] != 'binary':
                continue
            if metric == 'ContradictoryRecall' and r['gold'] != 'CONTRADICTORY':
                continue
            if metric == 'UnknownRecall' and r['gold'] != 'UNKNOWN':
                continue
            byworld[r['world_cluster_id']].append(int(r['correct']))
    return [(w, sum(v) / len(v), 1) if metric == 'WorldMacroAcc' else (w, sum(v), len(v))
            for w, v in sorted(byworld.items())]


def same_metrics(actual, expected, prefix):
    # The existing final report adds auxiliary fields; compare every primary field.
    for key, value in actual.items():
        if isinstance(value, dict):
            same_metrics(value, expected[key], prefix + '/' + key)
        elif isinstance(value, float):
            if abs(value - expected[key]) > 1e-12:
                raise ValueError('LEGACY_METRIC_MISMATCH:' + prefix + '/' + key)
        elif value != expected[key]:
            raise ValueError('LEGACY_METRIC_MISMATCH:' + prefix + '/' + key)


def self_tests(project):
    legacy, policy, _ = parsers(project)
    raw_field = 'raw_response'
    def p(raw, **kwargs):
        return policy.parse_prediction({raw_field: raw, **kwargs})
    assert p('{"label":"SUPPORTED","confidence":0.7,"reason":"ok"}')['schema_valid']
    assert p('```json\n{"label":"SUPPORTED","confidence":0.7,"reason":"ok"}\n```')['label'] == 'SUPPORTED'
    assert p('SUPPORTED')['label'] is None
    assert p('{"label":"SUPPORTED","label":"CONTRADICTORY","confidence":0.7,"reason":"ok"}')['label'] is None
    assert p('{"label":"SUPPORTED","confidence":0.7,"reason":"prefix', finish_reason='length', generated_tokens=512)['label'] == 'SUPPORTED'
    fixture = [dict(sample_id='s', component='binary', pair_id='p', gold='SUPPORTED', label='SUPPORTED', correct=True, world_cluster_id='x:1'),
               dict(sample_id='c', component='binary', pair_id='p', gold='CONTRADICTORY', label=None, correct=False, world_cluster_id='x:1')]
    assert legacy.metrics(fixture)['claim_accuracy'] == .5
    assert legacy.metrics(fixture)['pair_accuracy'] == 0
    assert endpoint_values(fixture, 'PairAcc') == [('x:1', 0, 1)]
    assert interval([('x:1', 1, 1)], 1, 100) == (1., 1.)
    return dict(status='PASS', cases=9, raw_field=raw_field)


def freeze_metadata(dest, base, registry, old, project):
    lockpath = dest / 'manifest/INPUT_LOCK.json'
    if lockpath.exists():
        lock = load(lockpath)
        for ref in lock['refs']:
            if sha(ref['path']) != ref['sha256']:
                raise ValueError('FROZEN_SOURCE_CHANGED:' + ref['path'])
        return lock
    paths = [base / x for x in ('private_gold.jsonl', 'requests.jsonl', 'protocol_lock.json', 'registry.json', 'rubric.json')]
    paths += [old / x for x in ('common.py', 'output_policy.py')]
    paths += [project / 'scripts/full_multimodel_split_v5' / x for x in ('base_score_v2.py', 'judge_interface.json')]
    paths += [Path(__file__), CODE / 'snapshot_store_v2.py', CODE / 'world_identity_v2.py', CODE / 'e0_snapshot.py', CODE / 'common.py']
    metadata = {}
    for model in registry:
        metadata[model] = {}
        for name in ('config.json', 'full_candidate_acceptance.json', 'full_score_with_identity.json', 'full_judge_submission_v5.json', 'active_full_submission.json'):
            path = base / model / name
            if path.exists():
                value = load(path)
                save(dest / 'manifest/source_metadata' / model / name, value)
                metadata[model][name] = value
                paths.append(path)
    lock = dict(created_at=now(), refs=[entry(p) for p in paths], model_metadata=metadata,
                scope='EXISTING_PREDICTIONS_ONLY_NO_NEW_TEST_INFERENCE', new_model_calls=0)
    save(lockpath, lock)
    return lock


def main():
    ap = arguments(__doc__)
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--verify', action='store_true', help='Recompute primary scores from the immutable snapshot; write nothing.')
    a = ap.parse_args()
    if a.self_test:
        print(json.dumps(self_tests(Path(load(a.config)['project'])))); return
    c, root = setup(a)
    if a.dry_run:
        print('Snapshot existing 13-model campaign; score complete models; 3-model E0 world-cluster CIs; no inference.'); return
    dest = root / VERSION
    if a.verify:
        verify_results(dest, c)
        return
    if (dest / 'acceptance.json').exists():
        raise ValueError('ALREADY_FINISHED_CREATE_NEW_VERSION_FOR_FRESH_CAPTURE')
    project, base = Path(c['project']), Path(c['baseline'])
    tests = self_tests(project)
    legacy, policy, old = parsers(project)
    registry = load(base / 'registry.json')
    lock = freeze_metadata(dest, base, registry, old, project)
    protocol = load(base / 'protocol_lock.json')
    refs = {x['path']: x['sha256'] for x in lock['refs']}
    for path in [base / 'private_gold.jsonl', base / 'requests.jsonl', base / 'registry.json', old / 'common.py', old / 'output_policy.py']:
        if refs[str(path)] != protocol['files'][str(path)]:
            raise ValueError('BASELINE_PROTOCOL_HASH_MISMATCH:' + str(path))
    gold = unique(rows(base / 'private_gold.jsonl'), 'gold')
    requests = unique(rows(base / 'requests.jsonl'), 'requests')
    overlay, identity_acceptance = checked_overlay(c, root)
    if set(gold) != set(requests) or set(gold) != set(overlay) or len(gold) != protocol['expected_inputs']:
        raise ValueError('BASELINE_UNIVERSE_MISMATCH')
    snapshot = frozen_predictions(dest, base, list(registry))
    print(json.dumps(dict(stage='SNAPSHOT_COMPLETE', files=len(snapshot['files']), bytes=sum(r['complete_bytes'] for r in snapshot['files']))), flush=True)
    statuses, diagnostics, protocols, raw_index, scored_all, statistics, metric_rows, confusion, regression = [], [], [], [], [], [], [], [], []
    complete_scores, core_rows = {}, {}
    for model, spec in registry.items():
        meta = lock['model_metadata'][model]
        prediction_refs = [r for r in snapshot['files'] if r['model_id'] == model]
        accepted = meta.get('full_candidate_acceptance.json')
        if accepted:
            if accepted['status'] != 'COMPLETE' or accepted['n'] != len(gold):
                raise ValueError('CANDIDATE_ACCEPTANCE_MISMATCH:' + model)
            if accepted['files'] != {r['path']: r['snapshot_sha256'] for r in prediction_refs}:
                raise ValueError('ACCEPTED_RAW_HASH_MISMATCH:' + model)
        scored, ids, signatures = [], set(), Counter()
        for ref in prediction_refs:
            for lineno, r in enumerate(rows(ref['snapshot_path']), 1):
                sid = r['sample_id']
                if sid in ids or sid not in gold:
                    raise ValueError('DUPLICATE_OR_UNEXPECTED_ID:' + model + ':' + sid)
                ids.add(sid)
                if r.get('model_id') not in (None, spec['model_id']) or r.get('model_revision') not in (None, spec['revision']):
                    raise ValueError('MODEL_IDENTITY_MISMATCH:' + model)
                if r.get('config_sha256') not in (None, refs[str(base / model / 'config.json')]):
                    raise ValueError('MODEL_CONFIG_HASH_MISMATCH:' + model)
                parsed = policy.parse_prediction(r)
                label = None if r.get('error') else parsed['label']
                g = gold[sid]
                item = {k: g.get(k) for k in ('sample_id', 'pair_id', 'gold', 'level', 'dataset', 'track', 'split', 'component')}
                item.update(model_id=model, world_cluster_id=overlay[sid]['world_cluster_id'], world_resolution=overlay[sid]['resolution'],
                            label=label, correct=label == g['gold'], schema_valid=parsed['schema_valid'], runtime_error=r.get('error'),
                            truncated=r.get('finish_reason') == 'length', prefix_recovered=parsed.get('prefix_recovered', False),
                            fence_removed=parsed.get('fence_removed', False), generated_tokens=r.get('generated_tokens'))
                scored.append(item)
                raw_index.append(dict(model_id=model, sample_id=sid, snapshot_path=ref['snapshot_path'], line=lineno,
                                      raw_record_sha256=digest(r), request_sha256=digest(requests[sid]), original_path=ref['path']))
                signatures[json.dumps({k: r.get(k) for k in ('model_revision', 'prompt_version', 'decode', 'max_new_tokens', 'config_sha256')}, sort_keys=True)] += 1
        complete = len(ids) == len(gold) and bool(accepted)
        if model in c['models'] and not complete:
            raise ValueError('MAIN_E0_NOT_COMPLETE:' + model)
        score = meta.get('full_score_with_identity.json')
        if score:
            if not complete or score['status'] != 'PASS' or score['model_id'] != spec['model_id']:
                raise ValueError('FINAL_SCORE_IDENTITY_OR_COMPLETION_MISMATCH')
            for ref in prediction_refs:
                if score['input_hashes'][ref['path']] != ref['snapshot_sha256']:
                    raise ValueError('FINAL_SCORE_RAW_HASH_MISMATCH')
        status = dict(model_id=model, display_name=spec['display_name'], expected=len(gold), returned=len(ids),
                      missing=len(gold) - len(ids), worlds=len({r['world_cluster_id'] for r in scored}),
                      primary_status='COMPLETE' if complete else 'RUNNING_PARTIAL' if spec['enabled'] else 'BLOCKED_DISABLED',
                      auxiliary_status=score.get('judge_status') if score else 'IN_PROGRESS' if accepted else 'NOT_COMPLETE',
                      auxiliary_score_0_100=score.get('explanation_rubric_score') if score else None,
                      blocked_reason=spec.get('blocked_reason'), acceptance_present=bool(accepted))
        statuses.append(status)
        diagnostics.append(dict(model_id=model, returned=len(ids), runtime_errors=sum(bool(r['runtime_error']) for r in scored),
                                noncompliant_schema=sum(not r['schema_valid'] for r in scored), unusable_label=sum(r['label'] is None for r in scored),
                                truncated=sum(r['truncated'] for r in scored), prefix_recovered=sum(r['prefix_recovered'] for r in scored),
                                fence_removed=sum(r['fence_removed'] for r in scored), denominator_policy='COMPLETE_MODELS_ALL_REQUESTS_RETAINED'))
        for signature, n in signatures.items():
            protocols.append(dict(model_id=model, n=n, **json.loads(signature)))
        scored_all.extend(scored)
        if not complete:
            print(json.dumps(status), flush=True); continue
        cellmap = cells(scored)
        overall = legacy.metrics(scored)
        test = legacy.metrics([r for r in scored if r['split'] == 'test'])
        complete_scores[model] = dict(overall=overall, test_only=test, grouped={})
        if score:
            same_metrics(overall, score['overall'], model + '/overall')
            same_metrics(test, score['test_only'], model + '/test_only')
        for (dimension, stratum), rs in sorted(cellmap.items()):
            metrics = legacy.metrics(rs)
            complete_scores[model]['grouped'][dimension + ':' + stratum] = metrics
            metric_rows.append(dict(model_id=model, dimension=dimension, stratum=stratum, worlds=len({r['world_cluster_id'] for r in rs}),
                                    **{k: v for k, v in metrics.items() if k != 'per_label'}))
            field = {'LEVEL': 'level', 'SOURCE': 'dataset', 'TRACK': 'track', 'SOURCE_SPLIT': 'split'}.get(dimension)
            if score and field:
                same_metrics(metrics, score['grouped'][field][stratum], model + '/' + field + '/' + stratum)
            for endpoint in ENDPOINTS:
                values = endpoint_values(rs, endpoint)
                num, den = sum(v[1] for v in values), sum(v[2] for v in values)
                lo, hi = interval(values, c['statistics']['seed'], c['statistics']['bootstrap_repetitions']) if model in c['models'] else (None, None)
                statistics.append(dict(model_id=model, dimension=dimension, stratum=stratum, metric=endpoint,
                                       claims=len(rs), worlds=len(values), numerator=num, denominator=den,
                                       estimate=num / den if den else None, ci95_low=lo, ci95_high=hi,
                                       status='COMPLETE', uncertainty='SOURCE_STRATIFIED_WORLD_BOOTSTRAP_5000' if model in c['models'] else 'POINT_ESTIMATE_ONLY'))
            counts = Counter((r['gold'], r['label'] or 'NO_USABLE_LABEL') for r in rs)
            for (g, p), n in sorted(counts.items()):
                confusion.append(dict(model_id=model, dimension=dimension, stratum=stratum, gold=g, predicted=p, n=n))
        regression.append(dict(model_id=model, status='EXACT_MATCH_ALL_PRIMARY_FIELDS' if score else 'NEW_PRIMARY_AGGREGATE_AUXILIARY_PENDING'))
        if model in c['models']:
            core_rows[model] = {r['sample_id']: r for r in scored}
        print(json.dumps(dict(model_id=model, returned=len(ids), claim_accuracy=overall['claim_accuracy'], auxiliary=status['auxiliary_status'])), flush=True)
    # Matching is on identical frozen sample IDs, never smaller-model failures.
    common = set.intersection(*(set(v) for v in core_rows.values()))
    if common != set(gold):
        raise ValueError('CORE_MODEL_COMMON_UNIVERSE_MISMATCH')
    transitions, patterns = [], Counter()
    for sid in sorted(common):
        pattern = ''.join(str(int(core_rows[m][sid]['correct'])) for m in c['models'])
        patterns[(gold[sid]['level'], pattern)] += 1
    for left, right in combinations(c['models'], 2):
        for (dimension, stratum), rs in cells(core_rows[left].values()).items():
            changes = Counter(); byworld = defaultdict(list)
            for r in rs:
                x, y = int(r['correct']), int(core_rows[right][r['sample_id']]['correct'])
                changes[(x, y)] += 1
                byworld[r['world_cluster_id']].append(y - x)
            values = [(w, sum(v), len(v)) for w, v in sorted(byworld.items())]
            lo, hi = interval(values, c['statistics']['seed'], c['statistics']['bootstrap_repetitions'])
            transitions.append(dict(model_from=left, model_to=right, dimension=dimension, stratum=stratum,
                                    claims=len(rs), worlds=len(byworld), both_correct=changes[1, 1], both_wrong=changes[0, 0],
                                    wrong_to_correct=changes[0, 1], correct_to_wrong=changes[1, 0],
                                    claim_acc_delta=(changes[0, 1] - changes[1, 0]) / len(rs), ci95_low=lo, ci95_high=hi,
                                    interpretation='DESCRIPTIVE_PAIRED_DIFFERENCE_NOT_CAUSAL_OR_CONFIRMATORY'))
    for name, data in [('model_status', statuses), ('interface_diagnostics', diagnostics), ('actual_protocols', protocols),
                       ('primary_metrics', metric_rows), ('primary_statistics_ci', statistics), ('label_confusion', confusion),
                       ('common_model_transitions', transitions), ('legacy_score_regression', regression),
                       ('common_scale_patterns', [dict(level=l, model_order=c['models'], correctness_pattern=p, claims=n) for (l,p),n in sorted(patterns.items())])]:
        csvsave(dest / 'tables' / (name + '.csv'), data)
    save(dest / 'scores/per_sample_primary.jsonl', scored_all, 'jsonl')
    save(dest / 'manifest/raw_response_index.jsonl', raw_index, 'jsonl')
    save(dest / 'scores/complete_primary_results.json', complete_scores)
    # Reject mutations of any frozen source read during this refresh.
    for ref in lock['refs']:
        if sha(ref['path']) != ref['sha256']:
            raise ValueError('SOURCE_CHANGED_DURING_REFRESH:' + ref['path'])
    acceptance = dict(status='PASS_E0_THREE_MODEL_PRIMARY_COMPLETE', created_at=now(), captured_at=lock['created_at'], job_id=os.environ['SLURM_JOB_ID'],
                      expected_inputs=len(gold), main_models=c['models'], main_common_inputs=len(common),
                      main_common_worlds=len({v['world_cluster_id'] for v in overlay.values()}),
                      complete_primary_models=sum(r['primary_status'] == 'COMPLETE' for r in statuses),
                      complete_auxiliary_models=sum(str(r['auxiliary_status']).startswith('COMPLETE') for r in statuses),
                      registered_models=len(registry), model_status=statuses, self_tests=tests, regression=regression,
                      world_identity_overlay=identity_acceptance['overlay'], bootstrap_repetitions=5000, bootstrap_seed=c['statistics']['seed'],
                      new_model_calls=0, original_release_gold_raw_scores_unchanged=True, prior_full_test_authority='EXISTING_FULL_BENCHMARK_EVALUATION_ONLY',
                      test_not_used_for_prompt_or_mechanism_selection=True, no_sws_v3_parser_applied_to_e0=True,
                      review_status='HUMAN_REVIEW_WAIVED_BY_RESEARCHER', scientific_review_grade='AUTO_ONLY_PROVISIONAL',
                      score_denominator='ALL_FROZEN_ELIGIBLE_INPUTS_FOR_COMPLETE_MODELS_RUNTIME_AND_INTERFACE_FAILURES_RETAINED',
                      auxiliary_policy='REUSE_HASH_LINKED_EXISTING_FINAL_ARTIFACT_ONLY_NO_PARTIAL_JUDGE_AVERAGE')
    save(dest / 'acceptance.json', acceptance)
    write_report(dest, c, gold, overlay, complete_scores, statuses, statistics, transitions, acceptance)
    save(dest / 'manifest/OUTPUT_INDEX.json', [entry(p) for p in sorted(dest.rglob('*')) if p.is_file() and 'raw/E0_existing_snapshot' not in str(p)])
    print(json.dumps(dict(status=acceptance['status'], report=str(dest / 'E0_Full_Benchmark_Results_CN.md'))), flush=True)


def write_report(dest, c, gold, overlay, scores, statuses, statistics, transitions, acc):
    def pct(x): return 'N/A' if x is None else f'{100*x:.2f}%'
    def stat(model, metric, dim='OVERALL', group='ALL'):
        return next(r for r in statistics if (r['model_id'], r['metric'], r['dimension'], r['stratum']) == (model, metric, dim, group))
    def with_ci(s): return pct(s['estimate']) + (f" [{pct(s['ci95_low'])}, {pct(s['ci95_high'])}]" if s['ci95_low'] is not None else '')
    lines = ['# SpaceConflict E0 全 benchmark 完整主结果（2026-09-10 刷新）', '',
             f"快照时间：{acc['captured_at']}（UTC）；CPU 汇总作业：{acc['job_id']}。", '',
             '## 1. 完成情况', '',
             f"E0 规定的 Qwen3.5-4B、9B、27B **三模型主评测已全部完成**：每模型 {len(gold):,} 条，相同 {acc['main_common_worlds']:,} 个 underlying world，共 {3*len(gold):,} 条已有响应。27B 的辅助解释 judge 尚未完成，不影响本报告准确率、pair、recall 和 world-macro。", '',
             f"扩展模型清单共 {acc['registered_models']} 个：{acc['complete_primary_models']} 个全量推理及主评分完成，{acc['complete_auxiliary_models']} 个辅助解释评分完成。不能把三模型 E0 完成等同于全部 13 个模型全部阶段完成。", '',
             '本轮只有读取、冻结副本、确定性评分和统计；没有新推理、没有新 test 调用、没有改提示、gold、release 或旧预测。旧 E0 的 27B 部分返回快照已过时，仍原样保留。本报告是新的汇总入口。', '',
             '## 2. 样本范围与协议', '',
             '| Level | 输入数 | world 数 | S | C | U |', '|---|---:|---:|---:|---:|---:|']
    for level in ('L1', 'L2', 'L3', 'L4'):
        gs = [g for g in gold.values() if g['level'] == level]; counts = Counter(g['gold'] for g in gs)
        lines.append(f"| {level} | {len(gs):,} | {len({overlay[g['sample_id']]['world_cluster_id'] for g in gs}):,} | {counts['SUPPORTED']:,} | {counts['CONTRADICTORY']:,} | {counts['UNKNOWN']:,} |")
    lines += ['', 'world 可跨 Level/来源，不能将各行 world 数相加。全量 all-split 是全覆盖描述性结果，不等于独立 test 成绩；已有 test-only 单列如下。', '',
              '主协议沿用原冻结全量评测：greedy / do_sample=false，512 output tokens，原 label/confidence/reason JSON 接口；按已产生的 512-token 前缀评分，截断本身不判无效。有效 label 不因 reason/confidence 不完整而自动抹去；无法获得 label 和运行错误仍留在分母。原解析器 retained_prefix_512_v1 / outer_json_fence_v1 未修改；SWS 的 value/facts v3 解析修复不适用于本表。', '',
              '逐模型真实 prompt、decode、revision、config hash 见 tables/actual_protocols.csv；不同模型架构/视觉 processor、thinking 模式仍是跨家族比较的限制，扩展模型不与机制实验拼接。配置中残留的 Industry per-task token 字段不是本次实际预算。', '',
              '## 3. E0 三模型全量主结果', '',
              '准确率与 CI 均为百分比。95% CI：按底层 world 聚类、按来源 family 分层 bootstrap，5,000 次，固定种子 20260909；是数据 world 重采样不确定性，不是多次生成方差，也不是因果检验。', '',
              '| 模型 | N | ClaimAcc [95% CI] | BinaryClaimAcc | PairAcc [95% CI] | C recall | U recall | World-macro |',
              '|---|---:|---|---:|---|---:|---:|---:|']
    for m in c['models']:
        lines.append(f"| {m} | {scores[m]['overall']['n']:,} | {with_ci(stat(m,'ClaimAcc'))} | {pct(stat(m,'BinaryClaimAcc')['estimate'])} | {with_ci(stat(m,'PairAcc'))} | {pct(stat(m,'ContradictoryRecall')['estimate'])} | {pct(stat(m,'UnknownRecall')['estimate'])} | {pct(stat(m,'WorldMacroAcc')['estimate'])} |")
    lines += ['', '所有端点及 Level / 来源 / Track / S-C-U / 原 split 的分组 CI 均在 tables/primary_statistics_ci.csv；Balanced Accuracy、Macro-F1、Unknown F1 等补充指标在 tables/primary_metrics.csv。', '',
              'PairAcc 只统计完整 S/C 两成员 pair，必须两条都正确；它受到单侧 C recall 等结构性上限约束，不能把 pair 下降当作独立机制证据。UNKNOWN 不参与二元 PairAcc。world-macro 对 world 等权；ClaimAcc 对输入等权。', '',
              '### L1–L4 分层', '', '| 模型 | Level | N | world 数 | ClaimAcc [95% CI] | PairAcc |', '|---|---|---:|---:|---|---:|']
    for m in c['models']:
        for level in ('L1', 'L2', 'L3', 'L4'):
            s = stat(m, 'ClaimAcc', 'LEVEL', level)
            lines.append(f"| {m} | {level} | {s['claims']:,} | {s['worlds']:,} | {with_ci(s)} | {pct(stat(m,'PairAcc','LEVEL',level)['estimate'])} |")
    lines += ['', '### 已有 test-only（未运行新 test）', '', '| 模型 | N | ClaimAcc [95% CI] | PairAcc | Macro-F1 |', '|---|---:|---|---:|---:|']
    for m in c['models']:
        s = scores[m]['test_only']
        lines.append(f"| {m} | {s['n']:,} | {with_ci(stat(m,'ClaimAcc','SOURCE_SPLIT','test'))} | {pct(s['pair_accuracy'])} | {pct(s['macro_f1'])} |")
    lines += ['', '## 4. 共同输入上的模型错误变化', '', '| 从 → 到 | 共同 N / worlds | 错→对 | 对→错 | ClaimAcc 差值及 95% CI |', '|---|---:|---:|---:|---|']
    for r in transitions:
        if r['dimension'] == 'OVERALL':
            lines.append(f"| {r['model_from']} → {r['model_to']} | {r['claims']:,} / {r['worlds']:,} | {r['wrong_to_correct']:,} | {r['correct_to_wrong']:,} | {100*r['claim_acc_delta']:+.2f} pp [{100*r['ci95_low']:+.2f}, {100*r['ci95_high']:+.2f}] |")
    lines += ['', '全部共同样本均进入比较；没有按 4B/9B 错误选择 27B。保留三模型 8 种正确/错误模式与反例。上述差异是行为描述，不能据此归因为 state selection、内部状态或模型规模的因果效应。', '',
              '## 5. 扩展模型完整状态与已有成绩', '',
              '仅 COMPLETE 模型给全量主分。扩展模型点估计不附本轮 bootstrap CI；尚未完成的模型不以已返回子集冒充全量成绩。辅助解释分是 Qwen3.5-4B 自动 rubric 的 0–100 分，非准确率、非独立视觉核验，存在同家族/自评分偏差。', '',
              '| 模型 | 已返回 / 总数 | 主评测状态 | ClaimAcc | PairAcc | 解释辅助分 / 状态 |', '|---|---:|---|---:|---:|---|']
    for r in statuses:
        s = scores.get(r['model_id'], {}).get('overall', {})
        aux = f"{r['auxiliary_score_0_100']:.2f}" if r['auxiliary_score_0_100'] is not None else r['auxiliary_status']
        lines.append(f"| {r['display_name']} | {r['returned']:,} / {r['expected']:,} | {r['primary_status']} | {pct(s.get('claim_accuracy'))} | {pct(s.get('pair_accuracy'))} | {aux} |")
    lines += ['', 'Llama 4 Scout 的注册记录为 ACCESS_BLOCKED:GatedRepoError / 缺权重，非模型测评失败。27B 与 Qwen2.5-VL-32B 的解释 judge 不用部分结果报最终均分；其完成后可另建刷新版本。本报告不取消或改变这些在运行作业。', '',
              '解释 judge 沿用当前 judge_interface_1000chars_512tokens_v2：每次 judge 最多 512 tokens，evidence 最多 1,000 非空白字符；没有恢复旧的 160 字符限制。', '',
              '## 6. 验收、限制与证据入口', '',
              f"- 验收：{acc['status']}；主三模型共同 {acc['main_common_inputs']:,} 条。", 
              '- 主输入、gold、parser、模型 config、完整预测的哈希与冻结协议及候选验收一致；已有 8 份最终评分的 overall、test 及相关分组主指标逐字段重算一致。',
              '- 原来缺失的 world metadata 只复用已验收的 exact sample-ID/release 对照 overlay，不依据模型答案补世界或 gold。',
              '- 未注释 Track 保留 NOT_ANNOTATED（Not annotated in released pair），不按 operator 猜；这里使用原冻结主 Track，并非多标签展开，禁止将多标签计数当独立样本相加。',
              '- 人工流程来源记为 HUMAN_REVIEW_WAIVED_BY_RESEARCHER / AUTO_ONLY_PROVISIONAL；这不冒充新增人工 VERIFIED。E0 统计完成不代表 SWS 全部行为、白盒与留出模块完成。',
              '- 严格格式、无可评分 label、截断、运行错误仅在 interface_diagnostics.csv 作为审计；本轮未据成绩调 parser、补答案或重试选优。', '',
              f"结果根目录：`{dest}`。", '',
              '| 文件 | 用途 |', '|---|---|',
              '| acceptance.json | 完成状态、样本/world 数、输入验收与来源 |',
              '| tables/primary_statistics_ci.csv | E0 六项指标，所有要求分组及主三模型 CI |',
              '| tables/primary_metrics.csv | 含 BalancedAcc / Macro-F1 / Unknown-F1 的精确主分 |',
              '| tables/label_confusion.csv | 标签混淆与无可评分 label 分布 |',
              '| tables/common_model_transitions.csv / common_scale_patterns.csv | 匹配输入错误转移与反例分布 |',
              '| scores/per_sample_primary.jsonl | 逐样本预测标签、gold、world 与正确性；含未完成模型的已返回记录，完成状态须结合 model_status.csv |',
              '| manifest/raw_response_index.jsonl | 原始文件和冻结副本行号、请求及响应 hash |',
              '| raw/E0_existing_snapshot/SNAPSHOT_LOCK.json | 固定字节前缀快照及所有原始响应副本 |',
              '| manifest/INPUT_LOCK.json / OUTPUT_INDEX.json | 源文件和结果哈希、元数据副本 |',
              '| tables/legacy_score_regression.csv | 旧最终主分的一致性检查 |', '',
              '复核/复现：在 Slurm CPU allocation 中运行以下命令，校验全部快照及输出 hash，并从冻结原始响应重算所有完整模型的主指标（不覆盖任何文件）：', '', '```bash',
              f"bash '{CODE}/job_e0_refresh_v3.sh' --verify", '```', '',
              '固定快照的逐样本矩阵、原解析器和原始响应索引均已保留；模型推理复现应遵循 BASE/protocol_lock.json，而非重用 Industry 的历史字段。', '']
    save(dest / 'E0_Full_Benchmark_Results_CN.md', '\n'.join(lines), 'text')


def verify_results(dest, config):
    lock = load(dest / 'manifest/INPUT_LOCK.json')
    for ref in lock['refs'] + load(dest / 'manifest/OUTPUT_INDEX.json'):
        if sha(ref['path']) != ref['sha256']:
            raise ValueError('VERIFY_HASH_MISMATCH:' + ref['path'])
    snap = frozen_predictions(dest, Path(config['baseline']), list(load(Path(config['baseline']) / 'registry.json')))
    legacy, policy, _ = parsers(Path(config['project']))
    gold = unique(rows(Path(config['baseline']) / 'private_gold.jsonl'), 'verify_gold')
    expected = load(dest / 'scores/complete_primary_results.json')
    checked = {}
    for model, score in expected.items():
        preds = unique((r for ref in snap['files'] if ref['model_id'] == model for r in rows(ref['snapshot_path'])), model)
        if set(preds) != set(gold):
            raise ValueError('VERIFY_UNIVERSE_MISMATCH')
        scored = [dict(g, label=None if preds[sid].get('error') else policy.parse_prediction(preds[sid])['label']) for sid, g in gold.items()]
        same_metrics(legacy.metrics(scored), score['overall'], model + '/overall')
        same_metrics(legacy.metrics([r for r in scored if r['split'] == 'test']), score['test_only'], model + '/test')
        for (dimension, stratum), rs in cells(scored).items():
            same_metrics(legacy.metrics(rs), score['grouped'][dimension + ':' + stratum], model + '/' + dimension + ':' + stratum)
        checked[model] = len(scored)
    print(json.dumps(dict(status='VERIFIED_FROM_FROZEN_RAW', primary_models=checked, writes=0, new_model_calls=0)), flush=True)


if __name__ == '__main__':
    main()
