"""Frozen B0 descriptive candidates and conservative STOP decision; no execution."""
from collections import defaultdict,Counter
from b0common import *
stats=import_file(A1CODE/'analysis_v1/cluster_stats.py','b0_decision_stats')


def finalized_metric(rs,key,c,cohort):
    return stats.estimate([(r['underlying_world_id'],int(bool(r[key])),1) for r in rs if r.get(key) is not None],cohort,c['seed'],c['bootstrap_repetitions'])


def finalize(c,root,panels,all_rows,claimrows,pairs,factorial,counts,summary,claims_summary,matched_summary):
    rules=load(CODE/'analysis_rules.json'); matrix=[]; future=[]
    for model in c['models']:
        for p in panels:
            w=p['underlying_world_id']; rs=[r for r in all_rows if r['model']==model and r['underlying_world_id']==w]
            cc=[r for r in claimrows if r['model']==model and r['underlying_world_id']==w]
            mm=[r for r in pairs if r['model']==model and r['underlying_world_id']==w]
            ff=[r for r in factorial if r['model']==model and r['underlying_world_id']==w]
            tags={
                'PRE_FACT_FAILURE':any(r['condition']=='FACT_NEUTRAL' and r['target']=='PRE' and r.get('fact_present') and r.get('fact_correct') is False for r in rs),
                'POST_UPDATE_OR_RECOUNT_FAILURE':any(r['condition']=='FACT_NEUTRAL' and r['target']=='POST' and r.get('fact_present') and r.get('fact_correct') is False for r in rs),
                'CLAIM_CONDITIONED_FACT_SHIFT':any(r.get('fact_corruption') for r in cc),
                'FACT_TO_VERDICT_UTILIZATION_GAP':any(r.get('controlled_utilization_case') for r in cc),
                'SELF_CONSISTENCY_VIOLATION':any(r.get('self_consistency_violation') for r in rs),
                'INTERVENTION_CONTEXT_CONTAMINATION':any(r['comparison']=='NO_INTERVENTION_TO_INTERVENTION' and r['harm'] and r['base_status']!='INVALID' and r['control_status']!='INVALID' for r in mm),
                'MISSING_EVIDENCE_SENSITIVITY':any(r['complete_core_narrative_correct'] and r['missing_core_narrative_correct'] is False for r in ff),
                'PROMPT_ORGANIZATION_SENSITIVITY':any(r['missing_core_narrative_correct'] is not None and r['missing_independent_table_correct'] is not None and r['missing_core_narrative_correct']!=r['missing_independent_table_correct'] for r in ff),
                'GENERAL_RECOUNT_INSTABILITY':any(r['comparison']=='NEUTRAL_RECOUNT_REPEAT' and r.get('fact_shift') for r in mm),
            }
            bins=defaultdict(list)
            for r in rs:
                if r['condition']=='VERDICT_ONLY' and r['claim_type']!='target_match' and r.get('verdict_present'):
                    bins[r['target'],r['context'],r['wording']].append(r)
            tags['NUMERIC_OFFSET_SENSITIVITY']=any(len({r['delta'] for r in b})>=2 and len({r['verdict_correct'] for r in b})==2 for b in bins.values())
            tags['STABLE_CORRECT']=all(r.get('correct') is True for r in rs)
            tags['MIXED_OR_UNRESOLVED']=sum(v for k,v in tags.items() if k!='STABLE_CORRECT')!=1 and not tags['STABLE_CORRECT']
            evidence={
                'same_run_fact_correct_verdict_wrong':[r['request_id'] for r in rs if r.get('same_run_fact_correct_verdict_wrong')],
                'self_consistency_violation':[r['request_id'] for r in rs if r.get('self_consistency_violation')],
                'fact_corruption':[r['claim_fact_request_id'] for r in cc if r.get('fact_corruption')],
                'stable_fact_wrong_verdict':[r['verdict_request_id'] for r in cc if r.get('stable_fact_wrong_verdict')],
                'neutral_recount_changes':[r['match_id'] for r in mm if r['comparison']=='NEUTRAL_RECOUNT_REPEAT' and r.get('fact_shift')],
                'successful_requests':[r['request_id'] for r in rs if r.get('correct') is True],
                'invalid_requests':[r['request_id'] for r in rs if r['status']=='INVALID'],
                'null_requests':[r['request_id'] for r in rs if r.get('null_fact')],
                'not_run_requests':[r['request_id'] for r in rs if r['status']=='NOT_RUN'],
            }
            matrix.append(dict(model=model,underlying_world_id=w,cohort=p['cohort'],category=p['category'],operation=p['operation'],
                PRE=p['values']['PRE'],POST=p['values']['POST'],requests=len(rs),responses=sum(r['response_available'] for r in rs),
                complete=all(r['response_available'] for r in rs),failure_tags=[k for k,v in tags.items() if v],**tags,
                evidence=evidence,competing_explanations_remaining=['VISUAL_EVIDENCE_SUFFICIENCY','AUTOREGRESSIVE_OUTPUT_INFLUENCE','LIMITED_WORDING_CONTROL','FINITE_RECOUNT_REPEATS','SOURCE_CONTROLLED_EXTENSION_DOMAIN']))
            for r in cc:
                if r.get('controlled_utilization_case') or r.get('controlled_attraction_case'):
                    future.append(dict(world_id=w,model=model,clean_request_id=r['neutral_request_id'],corrupt_request_id=r['claim_fact_request_id'],
                        same_run_request_id=r['joint_request_id'],matched_fields=['media','target','scope','category','intervention','wording'],changed_variable='candidate_claim_presence',
                        behavior_pattern='FACT_TO_VERDICT_UTILIZATION_GAP' if r.get('controlled_utilization_case') else 'CLAIM_CONDITIONED_FACT_SHIFT',
                        eligibility_reason='BEHAVIORAL_CANDIDATE_ONLY_REQUIRES_RESEARCHER_DECISION',execute_whitebox=False))
    union_csv(root/'tables/b0_world_failure_matrix.csv',matrix)
    candidate_summary=[]
    for model in c['models']:
        for cohort in ['B0_A','B0_B','ALL']:
            mm=[r for r in matrix if r['model']==model and (cohort=='ALL' or r['cohort']==cohort)]
            worlds={r['underlying_world_id'] for r in mm}
            for tag in tags:
                est=stats.estimate([(r['underlying_world_id'],int(r[tag]),1) for r in mm if r['complete']],worlds,c['seed'],c['bootstrap_repetitions'])
                candidate_summary.append(dict(model=model,cohort=cohort,candidate=tag,**est,
                    supporting_worlds=[r['underlying_world_id'] for r in mm if r[tag]],interpretation='NONEXCLUSIVE_DESCRIPTIVE_WORLD_FLAG_NOT_MECHANISM_FRACTION'))
    union_csv(root/'tables/b0_candidate_summary.csv',candidate_summary)
    save(root/'future_whitebox_pair_candidates.jsonl',future,'jsonl')
    primary=c['primary_model']; worlds={p['underlying_world_id'] for p in panels}
    primary_claim=[r for r in claimrows if r['model']==primary and r['claim_type']!='target_match' and r['context']=='I1' and r['wording']=='W0']
    primary_joint=[r for r in all_rows if r['model']==primary and r['condition']=='FACT_VERDICT' and r['context']=='I1' and r['wording']=='W0']
    rates={k:finalized_metric(primary_claim,k,c,worlds) for k in ['claim_fact_shift','claim_attraction','fact_corruption','stable_fact_wrong_verdict','neutral_repeat_shift','controlled_utilization_case','controlled_attraction_case']}
    rates.update({k:finalized_metric(primary_joint,k,c,worlds) for k in ['same_run_fact_correct_verdict_wrong','self_consistency_violation']})
    order_pairs=[r for r in pairs if r['model']==primary and r['comparison']=='FACT_FIRST_TO_VERDICT_FIRST' and r['context']=='I1' and r['wording']=='W0']
    order_rates={k:finalized_metric(order_pairs,k,c,worlds) for k in ['actual_order_pair_compliant','actual_order_fact_shift','actual_order_verdict_flip']}
    intervention_pairs=[r for r in pairs if r['model']==primary and r['comparison']=='NO_INTERVENTION_TO_INTERVENTION' and r['wording']=='W0']
    intervention_rates={k:finalized_metric(intervention_pairs,k,c,worlds) for k in ['harm','rescue','fact_shift','verdict_flip']}
    intervention_rates['net_accuracy_delta']=stats.estimate([(r['underlying_world_id'],r['net_accuracy_delta'],1) for r in intervention_pairs if r['net_accuracy_delta'] is not None],worlds,c['seed'],c['bootstrap_repetitions'])
    ff=[r for r in factorial if r['model']==primary]
    factorial_rates={k:stats.estimate([(r['underlying_world_id'],r[k],1) for r in ff if r[k] is not None],worlds,c['seed'],c['bootstrap_repetitions']) for k in ['narrative_missing_penalty','table_missing_penalty','missing_table_rescue','table_by_missing_interaction']}
    coverage=counts[primary]['responses']/counts[primary]['planned']
    robust={}; findings={}
    for metric,label in [('controlled_utilization_case','FACT_TO_VERDICT_UTILIZATION'),('controlled_attraction_case','CLAIM_CONDITIONED_FACT_SHIFT')]:
        cc=[r for r in claimrows if r['model']==primary and r.get(metric)]
        grouped=defaultdict(list)
        for r in cc: grouped[r['underlying_world_id'],r['target'],r['claim_value'],r['context']].append(r)
        both=[r for rs in grouped.values() if {x['wording'] for x in rs}=={'W0','W1'} for r in rs]
        unique={r['underlying_world_id'] for r in both}; new={r['underlying_world_id'] for r in both if r['cohort']=='B0_B'}
        checks=dict(multiple_worlds=len(unique)>=3,new_worlds=len(new)>=2,categories=len({r['category'] for r in both})>=2,
            both_operations={r['operation'] for r in both}=={'ADD','REMOVE'},non_1_to_0=any((r['source_values']['PRE'],r['source_values']['POST'])!=(1,0) for r in both),
            multiple_offsets=len({r['delta'] for r in both})>=2,pre_without_intervention=any(r['context']=='I0' for r in both),
            stable_neutral_repeats=bool(both) and all(r['neutral_repeat_stable_correct'] for r in both),
            positive_primary_lower_ci=(rates[metric]['ci95_low'] or 0)>0,complete_response_coverage=coverage==1)
        robust[label]=dict(checks=checks,all_pass=all(checks.values()),worlds=sorted(unique),extension_worlds=sorted(new),
                           supporting_cases=len(cc),matched_both_wording_cases=len(both))
        findings[label]='SUPPORTED' if all(checks.values()) else 'WEAK' if cc else 'NOT_SUPPORTED' if coverage>=.95 else 'UNRESOLVED'
    recommendation=next((label for label in ['FACT_TO_VERDICT_UTILIZATION','CLAIM_CONDITIONED_FACT_SHIFT'] if robust[label]['all_pass']),'NONE')
    primary_matrix=[r for r in matrix if r['model']==primary]
    intervention_cases=sum(r['INTERVENTION_CONTEXT_CONTAMINATION'] for r in primary_matrix)
    organization_cases=sum(r['PROMPT_ORGANIZATION_SENSITIVITY'] for r in primary_matrix)
    decision=dict(status='STOP_AFTER_B0',execution_status='COMPLETE' if all(x['not_run']==0 and x['infrastructure']==0 for x in counts.values()) else 'PARTIAL_RETAIN_UNRUN',
        primary_behavioral_finding=recommendation if recommendation!='NONE' else 'MIXED_OR_UNRESOLVED',
        secondary_findings=[tag for tag in ['INTERVENTION_CONTEXT_CONTAMINATION','PROMPT_ORGANIZATION_SENSITIVITY','GENERAL_RECOUNT_INSTABILITY'] if any(r[tag] for r in primary_matrix)],
        claim_conditioned_fact_shift=findings['CLAIM_CONDITIONED_FACT_SHIFT'],fact_to_verdict_utilization_gap=findings['FACT_TO_VERDICT_UTILIZATION'],
        intervention_context_effect='WEAK' if intervention_cases else 'NOT_SUPPORTED' if coverage>=.95 else 'UNRESOLVED',
        missing_target_prompt_effect='WEAK' if organization_cases else 'NOT_SUPPORTED' if coverage>=.95 else 'UNRESOLVED',
        template_confound_remaining=recommendation=='NONE',independent_worlds=len(worlds),
        original_worlds=sum(p['cohort']=='B0_A' for p in panels),new_worlds=sum(p['cohort']=='B0_B' for p in panels),
        recommended_whitebox=recommendation,primary_model=primary,models=c['models'],counts=counts,primary_rates=rates,robust_route_checks=robust,
        order_rates=order_rates,intervention_rates=intervention_rates,missing_factorial_rates=factorial_rates,
        reasons=['Only finite dev/discovery behavior is measured; no neural mechanism established.',
                 'B0_B has automatic source/proof/processor checks, not a fabricated new human review.',
                 'Pragmatic prospective gate criteria and all failed gates are disclosed.',
                 'Two deterministic neutral repeats do not exhaust all recount/noise explanations.'],
        do_not_auto_execute_whitebox=True,allow_training=False,allow_confirmation=False,allow_test=False,
        evidence=dict(matrix='tables/b0_world_failure_matrix.csv',all_responses='03_B0_RAW_RESPONSES_WITH_PROMPTS.csv',matched='tables/b0_matched_controls.csv',rules='manifest/analysis_rules.json'))
    save(root/'B0_NEXT_STAGE_DECISION.json',decision)
    def rate_text(m):
        if m['estimate'] is None: return f"无可测分母（cohort {m['cohort_worlds']} world）"
        return f"{m['numerator']:g}/{m['denominator']:g} = {m['estimate']:.1%}；95% world CI {m['ci95_low']:.1%}–{m['ci95_high']:.1%}；贡献 {m['contributing_worlds']} world"
    jointworlds={r['underlying_world_id'] for r in primary_joint if r.get('same_run_fact_correct_verdict_wrong')}
    op_counts=Counter(p['operation'] for p in panels); transitions=Counter(f"{p['values']['PRE']}→{p['values']['POST']}" for p in panels)
    support_ops=sorted({r['operation'] for r in primary_joint if r.get('same_run_fact_correct_verdict_wrong')})
    support_offsets=sorted({r['delta'] for r in primary_joint if r.get('same_run_fact_correct_verdict_wrong')})
    support_counts=sorted({r['fact_gold'] for r in primary_joint if r.get('same_run_fact_correct_verdict_wrong')})
    report='# SpaceConflict B0 定向行为复现报告\n\n'
    report+=f"状态：{decision['execution_status']} / STOP_AFTER_B0。主分析 Qwen3.5-9B；4B/27B 为同请求对照。共 {len(worlds)} 个独立 L4 count world，B0-A {decision['original_worlds']}、B0-B {decision['new_worlds']}。不混入 A.1 的 L1 控制，不代表全量 benchmark。\n\n"
    report+='## 1. 实际执行与冻结\n\n| 模型 | 计划 | 实际响应 | INVALID | null fact | INFRA | 未运行 |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for model,x in counts.items(): report+=f"| {model} | {x['planned']} | {x['responses']} | {x['invalid']} | {x['null_fact']} | {x['infrastructure']} | {x['not_run']} |\n"
    report+='\n模型 revision、媒体 hash、请求、两种问法、两次 neutral 重复、解析与统计规则在 core 前冻结；greedy、thinking=false、最多 512 个新 token。不按成绩重试、不补全截断字段、不按 9B 错题挑 27B。same-run 指同一次自回归生成，不是一次内部 transformer forward 或已知内部事实。\n'
    report+='\n## 2. 结构覆盖与限制\n\n'
    report+=f"ADD/REMOVE：{dict(op_counts)}。PRE→POST 分布：{dict(transitions)}。新 world 只来自 dev 且属于既有 discovery 分区，未打开 sealed confirmation 或构造 test 推理。来源筛选及结构短缺见 manifest/source_inventory.json，非法负 offset 见 tables/not_applicable_offsets.csv。\n\n"
    report+='B0-A 沿用已确认的媒体；B0-B 只声明自动来源真值、双引擎与实际 processor 完整性检查，不冒充人工 VERIFIED。图片可解码、hash 一致不等于整个场景计数一定对模型可见；视觉证据充分性仍是竞争解释。新增 controlled world 的覆盖不代表来源分布完全平衡。\n'
    report+='\n冻结前另行核查全部 29 个未纳入的 dev/discovery native pair：均非 COUNT，见 reports/native_extension_source_audit.json 与 tables/native_extension_source_audit.csv。当前符合条件的新 world 只有 5 个，未达到约 12 个目标，明确保留 INSUFFICIENT_ELIGIBLE_WORLDS；不外推为整个来源库永远无法扩展。\n'
    report+='\n## 3. 主指标（9B，I1，W0）\n\nworld 为 cluster；2,000 次配对 bootstrap，seed=20260908。条件可测性分母明确保留，null/INVALID/未运行不伪造为数值 shift；组内相关请求不是独立 world。退化区间不表示真实不确定性为零。\n\n'
    for metric,value in rates.items(): report+=f"- `{metric}`：{rate_text(value)}。\n"
    report+='\n逐响应证据见 [完整回答与提示](03_B0_RAW_RESPONSES_WITH_PROMPTS.csv)，逐 world 成功/失败/null/INVALID/反例索引见 [诊断矩阵](tables/b0_world_failure_matrix.csv)。\n'
    report+='\n## 4. 指南十问\n\n'
    report+=f"1. same-run fact 正确、verdict 错：{rate_text(rates['same_run_fact_correct_verdict_wrong'])}；只计字段有效且 fact 为整数的实际输出。\n"
    report+=f"2. 上述主条件涉及 {len(jointworlds)}/{len(worlds)} 个独立 world：{', '.join(sorted(jointworlds)) or '无观察到的案例'}。\n"
    report+=f"3. 两个请求均遵循分配顺序：{rate_text(order_rates['actual_order_pair_compliant'])}；在实际顺序合规的配对中，fact shift：{rate_text(order_rates['actual_order_fact_shift'])}，verdict flip：{rate_text(order_rates['actual_order_verdict_flip'])}。分配条件差异与实际顺序效应分开。\n"
    report+=f"4. false claim 吸引事实报告：{rate_text(rates['claim_attraction'])}；neutral 与 false claim 相等时不进入该条件分母。\n"
    report+=f"5. 事实仍正确、独立 verdict 错：{rate_text(rates['stable_fact_wrong_verdict'])}；此跨请求指标不能替代 same-run 证据。\n"
    report+=f"6. same-run 分离主条件覆盖操作 {support_ops}；总体操作分布 {dict(op_counts)}，不可将零案例等同于不能发生。\n"
    report+=f"7. same-run 分离主条件的 target count 为 {support_counts}，claim delta 为 {support_offsets}；全量分组与 CI 见 b0_numeric_offset_summary.csv。\n"
    report+=f"8. 去除 intervention 的匹配结果中，{intervention_cases}/{len(worlds)} world 有加入上下文后的破坏性案例；同时报告救回、破坏、净差和 CI，不仅挑恢复例。详见 b0_intervention_ablation.csv 与匹配汇总。\n"
    report+=f"   9B/W0 全部预先固定 PRE 接口，I0→I1 的 harm：{rate_text(intervention_rates['harm'])}；rescue：{rate_text(intervention_rates['rescue'])}；准确率净差（I1−I0）：{rate_text(intervention_rates['net_accuracy_delta'])}。\n"
    report+=f"9. missing-target 2×2 中，{organization_cases}/{len(worlds)} world 的 missing 正确性随组织方式变化。COMPLETE/MISSING 与两种组织方式的逐格值、null、借值及 CI 见 b0_missing_target_factorial.csv 和 b0_missing_target_summary.csv；不把支线自动升级为主机制。\n"
    report+=f"   9B、全部 PRE/POST：叙述组织的缺失损失（complete−missing）：{rate_text(factorial_rates['narrative_missing_penalty'])}；表格组织的缺失损失：{rate_text(factorial_rates['table_missing_penalty'])}；组织×缺失交互（正值表示表格相对减轻缺失损失）：{rate_text(factorial_rates['table_by_missing_interaction'])}。\n"
    report+=f"10. 当前建议 `{recommendation}`；完整规则逐项通过/失败见 [下一阶段决策](B0_NEXT_STAGE_DECISION.json)。没有满足全部筛选条件时保持 MIXED_OR_UNRESOLVED，不进入白盒。\n"
    report+='\n## 5. 竞争解释与下一步边界\n\n'
    report+='已控制：三模型共同 world/请求、同源媒体、输出字段独立评分、实际 key order、合法正负 offset、PRE intervention ablation、两种固定问法、两次 neutral 重复、missing 2×2 同契约。控制已运行并不意味着该解释已被排除；应按上述匹配结果判断。仍未普遍排除：视觉证据充分性、未测措辞、更多重复下的数值不稳定、自回归输出前缀影响，以及有限类别/来源的分布限制。\n\n'
    report+='breadth 盘点与 B0 机制实验完全分开；它只记录已存在的评测单元与预测可用性，不补跑全量。future_whitebox_pair_candidates.jsonl 仅是建议索引，包含行为候选而非已获准实验。\n'
    report+='\n## 6. 验收与复现\n\n[协议锁](01_B0_PROTOCOL_LOCK.json)、[审核输入](review/processor_checks.csv)、[复现说明](REPRODUCE.md)。最终文件与历史保护验收见 reports/final_acceptance.json。完整 raw/token 留在 raw/，原始响应汇总索引见 manifest/raw_response_index.json。\n\nSTOP：不启动 hidden-state、probe、activation patching、训练、confirmation/test 或新增模型。\n'
    save(root/'00_B0_REPORT_CN.md',report,'text')
    save(root/'LIVE_STATUS.json',dict(status='ANALYSIS_WRITTEN_AWAITING_FINAL_INTEGRITY',counts=counts,decision=str(root/'B0_NEXT_STAGE_DECISION.json'),report=str(root/'00_B0_REPORT_CN.md'),stop_after_b0=True),frozen=False)


if __name__=='__main__':
    p=arguments(__doc__); p.parse_args(); raise SystemExit('Invoked by analyze.py; no standalone model operation')
