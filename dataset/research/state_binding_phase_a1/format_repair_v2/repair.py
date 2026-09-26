"""Versioned setup-only format repair. Does not modify or regenerate source predictions."""
import hashlib
import json
import random
import shutil
import time
from collections import defaultdict
from pathlib import Path
from common import arguments, load, rows, sha, save, csvsave, entry, require_compute
from format_adapter_v2 import score_v2, selftest, VERSION


def percentile(xs, q):
    ys=sorted(xs); p=(len(ys)-1)*q; lo=int(p); hi=min(lo+1,len(ys)-1)
    return ys[lo]+(ys[hi]-ys[lo])*(p-lo)


def cluster_cis(records, seed, repeats):
    buckets=defaultdict(list)
    for r in records: buckets[r['world_id']].append(r)
    groups=sorted(buckets)
    totals={g:(len(buckets[g]),sum(r['strict_correct'] for r in buckets[g]),
               sum(r['semantic_correct'] for r in buckets[g])) for g in groups}
    rng=random.Random(seed); strict=[]; semantic=[]; delta=[]
    for _ in range(repeats):
        selected=[totals[rng.choice(groups)] for _ in groups]
        n=sum(t[0] for t in selected); a=sum(t[1] for t in selected)/n; b=sum(t[2] for t in selected)/n
        strict.append(a); semantic.append(b); delta.append(b-a)
    return {k:[percentile(vals,.025),percentile(vals,.975)] for k,vals in
            [('strict_accuracy_ci95',strict),('semantic_accuracy_ci95',semantic),('paired_delta_ci95',delta)]}


def main():
    a=arguments(__doc__).parse_args(); cfg=load(a.config); out=Path(cfg['root'])
    assert (a.run_id,a.seed)==(cfg['run_id'],cfg['seed'])
    if a.limit is not None: raise ValueError('NO_POSTHOC_SUBSET')
    if a.dry_run: print('PLANNED: all 426 existing setup responses, gold-blind alias adapter, zero generation'); return
    require_compute()
    source=Path(cfg['source_a1_root']); code=Path(cfg['source_a1_code']); repair=Path(cfg['format_repair_code'])
    assert out!=source and out!=Path(cfg['phase_a_root'])
    assert cfg['format_policy']['accepted_single_value_keys']==['value','query_value']
    assert cfg['parser_version']==VERSION and not cfg['prompt_changed'] and cfg['gpu_generation_requests']==0
    old_lock=load(source/'manifest/setup_v1_lock.json')
    for e in old_lock['code']:
        assert sha(e['path'])==e['sha256'], 'SOURCE_CODE_CHANGED'
    assert sha(source/'inputs/setup_v1/requests.jsonl')==old_lock['inputs_sha256']
    assert sha(source/'gold/setup_v1.jsonl')==old_lock['gold_sha256']
    policy_lock=dict(status='FROZEN_BEFORE_REANALYSIS',config=entry(a.config),policy=cfg['format_policy'],
        files=[entry(p) for p in sorted(repair.glob('*.py'))]+[entry(p) for p in sorted(repair.glob('*.sh'))],
        source_setup_lock=entry(source/'manifest/setup_v1_lock.json'),
        source_inference_unchanged=True,source_prompt_version=cfg['prompt_version'],
        scope='POSTHOC_SETUP_MEASUREMENT_REPAIR_NOT_INDEPENDENT_CONFIRMATION',seed=cfg['seed'])
    save(out/'manifest/format_policy_lock.json',policy_lock,frozen=True)
    tests=selftest()
    print(json.dumps(dict(stage='adapter_tests',**tests)),flush=True)
    before=[entry(p) for p in sorted(source.rglob('*')) if p.is_file()]
    before += [entry(p) for p in sorted((code/'src').glob('*.py'))]
    before += [entry(p) for p in sorted((code/'scripts').glob('*.sh'))]
    before += [entry(code/'configs/a1.json')]
    save(out/'manifest/source_a1_files_before.jsonl',before,'jsonl',frozen=True)
    save(out/'config_snapshot.json',cfg,frozen=True)
    requests=list(rows(source/'inputs/setup_v1/requests.jsonl'))
    assert len(requests)==142 and all(r['level']=='SETUP_ONLY' and not r['payload']['media'] for r in requests)
    assert all(r['models']==cfg['models'] for r in requests)
    # Only this synthetic setup gold is used. No real-world model response/gold comparison.
    gold={r['request_id']:r for r in rows(source/'gold/setup_v1.jsonl')}
    import csv
    with (source/'setup_interface_calibration.csv').open(newline='') as f:
        old_scores={(r['model'],r['request_id']):r for r in csv.DictReader(f)}
    records=[]; index=[]
    for model in cfg['models']:
        complete=load(source/'raw/setup_v1'/model/'completion.json')
        assert complete['status']=='COMPLETE' and complete['requests']==142
        hashes={Path(e['path']).name:e['sha256'] for e in complete['raw_index']}
        for request in requests:
            rid=request['request_id']; path=source/'raw/setup_v1'/model/(rid+'.json')
            assert sha(path)==hashes[path.name], 'SOURCE_PREDICTION_HASH_CHANGED'
            raw=load(path)
            assert raw['model']==model and raw['request_id']==rid and raw['stage']=='setup_v1'
            s=score_v2(raw,gold[rid]); strict=s['strict']; semantic=s['semantic']; audit=s['audit']
            legacy=old_scores[model,rid]
            for key in ['schema_valid','json_valid','correct']:
                assert strict[key]==(legacy[key]=='True'), 'LEGACY_SCORE_REPLAY_MISMATCH'
            assert strict['status']==legacy['status']
            records.append(dict(analysis_run_id=cfg['run_id'],source_run_id=raw['run_id'],model=model,
                request_id=rid,world_id=request['group_id'],level='SETUP_ONLY',condition=request['condition'],
                interface=gold[rid]['schema']['kind'],expected=gold[rid]['expected'],raw_response=raw['raw_response'],
                strict_status=strict['status'],strict_schema_valid=strict['schema_valid'],
                original_json_valid=strict['json_valid'],strict_correct=strict['correct'],
                semantic_status=semantic['status'],extractable_valid=semantic['schema_valid'],
                semantic_correct=semantic['correct'],semantic_pred=semantic['pred'],
                normalization=audit['normalization'],original_object=audit.get('original_object'),
                canonical_object=audit.get('canonical_object'),wrong_keys=strict.get('wrong_keys'),
                truncated=raw.get('truncated',False),infrastructure_error=raw.get('infrastructure_error'),
                scorer_version=VERSION,raw_path=str(path),raw_sha256=sha(path)))
            rendered=source/'rendered/setup_v1'/model/(rid+'.json')
            index.append(dict(analysis_run_id=cfg['run_id'],source_run_id=raw['run_id'],model=model,request_id=rid,
                stage='SOURCE_SETUP_V1_REUSED_READ_ONLY',new_generation=False,**entry(path),
                rendered_path=str(rendered),rendered_sha256=sha(rendered)))
    csvsave(out/'setup_interface_calibration.csv',records)
    csvsave(out/'tables/format_repair_rows.csv',records)
    save(out/'raw_predictions_index.jsonl',index,'jsonl')
    checks=[]
    for model in cfg['models']:
        for interface in ['ALL','value','joint','action','verdict']:
            rr=[r for r in records if r['model']==model and (interface=='ALL' or r['interface']==interface)]
            n=len(rr); strict=sum(r['strict_correct'] for r in rr); sem=sum(r['semantic_correct'] for r in rr)
            validity=sum(r['extractable_valid'] for r in rr)/n
            stable_seed=cfg['seed']+int(hashlib.sha256(interface.encode()).hexdigest()[:8],16)
            checks.append(dict(model=model,interface=interface,level='SETUP_ONLY',requests=n,
                synthetic_worlds=len({r['world_id'] for r in rr}),
                strict_correct=strict,semantic_correct=sem,strict_accuracy=strict/n,semantic_accuracy=sem/n,
                strict_schema_validity=sum(r['strict_schema_valid'] for r in rr)/n,
                extractable_validity=validity,original_json_validity=sum(r['original_json_valid'] for r in rr)/n,
                alias_normalized=sum(r['normalization']=='ALIAS_QUERY_VALUE_TO_VALUE' for r in rr),
                null=sum(r['semantic_status']=='NULL' for r in rr),invalid=sum(not r['extractable_valid'] for r in rr),
                rescued=sum(not r['strict_correct'] and r['semantic_correct'] for r in rr),
                harmed=sum(r['strict_correct'] and not r['semantic_correct'] for r in rr),
                status='PASS' if validity>=cfg['schema_gate_minimum'] else 'FAIL',
                **cluster_cis(rr,stable_seed,cfg['bootstrap_repetitions'])))
    csvsave(out/'tables/setup_format_comparison.csv',checks)
    save(out/'reports/setup_format_comparison.json',checks)
    passed=all(c['status']=='PASS' for c in checks)
    acceptance=dict(status='PASS' if passed else 'FAIL',checks=checks,scorer_tests=tests,
        original_strict_gate='FAIL_UNCHANGED',gate_definition=cfg['schema_gate_scope'],
        source_scope='EXISTING_142_SETUP_REQUESTS_PER_MODEL_14_SYNTHETIC_WORLDS',
        posthoc_setup_reanalysis=True,independent_confirmatory_evidence=False,new_predictions=0,
        task_accuracy_not_gate=True,no_real_world_predictions_scored=True)
    save(out/'reports/setup_calibration_acceptance.json',acceptance,frozen=True)
    phase_a=list(rows(source/'manifest/phase_a_files_before.jsonl'))
    changed=[e['path'] for e in phase_a+before if not Path(e['path']).is_file() or sha(e['path'])!=e['sha256']]
    preservation=dict(status='PASS' if not changed else 'FAIL',phase_a_files_checked=len(phase_a),
        source_a1_files_checked=len(before),changed_files=changed,
        source_a1_baseline_sha256=sha(out/'manifest/source_a1_files_before.jsonl'),
        scope='Original Phase A preserved without rescoring; A1 v1 predictions and scores retained')
    save(out/'phase_a_preservation_check.json',preservation,frozen=True)
    if changed: raise ValueError('HISTORY_PRESERVATION_FAILED')
    save(out/'protocol_lock_a1.json',dict(status='FORMAT_ADAPTER_FROZEN_AWAITING_DERIVED_REVIEW',
        parser_version=VERSION,policy_lock_sha256=sha(out/'manifest/format_policy_lock.json'),
        gate_pass=passed,core_frozen=False,core_inference_authorized=False,
        source_prompt_version_unchanged=cfg['prompt_version'],setup_reanalysis_not_new_inference=True))
    # Preserve all prior candidate rows; none become measured failures or VERIFIED here.
    shutil.copy2(source/'tables/a1_failure_matrix.csv',out/'tables/a1_failure_matrix.csv')
    save(out/'a1_panel_manifest.jsonl',[],'jsonl')
    save(out/'next_stage_decision.json',dict(status='FORMAT_REPAIR_COMPLETE_MAIN_A1_INCOMPLETE',
        primary_candidate='UNRESOLVED_NO_VERIFIED_MECHANISM_RESPONSES',recommended_phase_b='NONE',
        reasons=['Proceed with input review; no mechanism conclusion from synthetic format calibration.'],
        do_not_auto_execute=True))
    lines=['# Phase A.1 输出格式修复 v2（主机制实验未完成）','',
        '这是对已完成 setup 回答的显式测量修复，不是新生成、独立确认或全量 benchmark 分数。',
        '原 Phase A 与 A1 v1 raw/gold/scorer/评分表均保留，旧严格 gate 仍为 FAIL；本目录使用明确版本化的解析契约。','',
        '## 修复规则','',
        '唯一单值字段 query_value 可确定性改名为 value。没有改值、补值、根据 gold 选字段、数值字符串强制转换或自由文本猜测。'
        '冲突/重复/额外字段仍拒绝；截断沿用只评分完整保留字段的规则。所有模型采用相同规则。','',
        '## 实际结果','',
        '| 模型 | 请求 / 合成 world | 原严格准确率 | 语义准确率 | 严格格式合规 | 可提取率 | 语义准确率 95% CI |',
        '|---|---|---|---|---|---|---|']
    for x in [x for x in checks if x['interface']=='ALL']:
        lo,hi=x['semantic_accuracy_ci95']
        lines.append(f"| {x['model']} | {x['requests']} / {x['synthetic_worlds']} | {x['strict_accuracy']:.2%} | {x['semantic_accuracy']:.2%} | {x['strict_schema_validity']:.2%} | {x['extractable_validity']:.2%} | [{lo:.2%}, {hi:.2%}] |")
    lines += ['',f"解析契约 gate：{'PASS' if passed else 'FAIL'}，逐模型逐接口族仍要求至少 95% 可提取率。正确率不是放行标准。",
        'CI 为固定 seed 的 2,000 次 world-cluster bootstrap；只有 14 个合成 world，结果属 exploratory。'
        '同一组响应的严格/语义差是解析处理差异，不是模型能力提升；退化 CI 不证明无不确定性。','',
        '## 验收与边界','',f"- 新 adapter 测试 {tests['new_tests']} 项、原 scorer 测试 {tests['legacy_tests']} 项 PASS。",
        f"- Phase A {len(phase_a)} 个文件与 A1 v1 {len(before)} 个文件校验未变；426 条来源 raw 全部校验。",
        '- 新 GPU 生成 0 条；无提示修改，无样本选择，无重试选优。',
        '- 真实 L4/L1 机制测量均为 NOT_RUN，尚无 VERIFIED world，不应选择某个机制进入下一阶段。',
        '- 已排除的是本次明确字段别名造成的解析阻塞，不是排除了视觉、action、POST、binding 或 comparison 等竞争解释。','',
        '## 可追溯材料','',
        '- manifest/format_policy_lock.json：代码、配置与唯一别名规则。',
        '- tables/format_repair_rows.csv：逐样本原文、严格结果、归一化结果与来源 SHA256。',
        '- tables/setup_format_comparison.csv：逐接口族结果、world 数、CI、rescue/harm。',
        '- raw_predictions_index.jsonl：索引到原始回答与实际渲染提示，未伪装成新预测。',
        '- phase_a_preservation_check.json：两层历史保护。',
        '- 下一步仅生成全部固定候选的派生输入复核包；未审核不能写 VERIFIED。']
    report='\n'.join(lines)+'\n'
    save(out/'format_repair_report_cn.md',report,'text')
    save(out/'phase_a1_report_cn.md',report,'text')
    save(out/'LIVE_STATUS.json',dict(status='FORMAT_GATE_PASS_AWAITING_DERIVED_REVIEW' if passed else 'FORMAT_GATE_FAIL',
        source_responses=426,new_generated_responses=0,mechanism_responses=0,verified_worlds=0,complete=False))
    print(json.dumps(dict(status=acceptance['status'],source_responses=len(records),new_predictions=0,
        models=[c for c in checks if c['interface']=='ALL'],preservation=preservation)),flush=True)
    if not passed: raise ValueError('NORMALIZED_INTERFACE_GATE_FAILED')


if __name__=='__main__': main()
