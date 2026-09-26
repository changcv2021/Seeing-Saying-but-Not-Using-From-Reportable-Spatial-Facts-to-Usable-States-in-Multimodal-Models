"""Predeclared descriptive analyses, including null and counterexample cases.

Only completely executed model panels enter these statistics. No selection or
inference code imports this module; the analyses cannot change the panel.
"""
from metrics import *


def matched_rows(base, intervention, name):
    """Match the same group/target/claim, preserving invalid completed answers."""
    def key(r): return (r['model'], r['group_id'], r['target'], r['claim_id'])
    left = {key(r): r for r in base}
    right = {key(r): r for r in intervention}
    if len(left) != len(base) or len(right) != len(intervention):
        raise ValueError('DUPLICATE_MATCH_KEY:' + name)
    result = []
    for k in sorted(left.keys() & right.keys(), key=str):
        a, b = left[k], right[k]
        if a['correct'] is None or b['correct'] is None:
            raise ValueError('UNEXECUTED_MATCH_MEMBER:' + name)
        answer = lambda r: r['gold'].get('value') if r['gold']['kind'] == 'value' else r['gold'].get('label')
        if answer(a) != answer(b): raise ValueError('UNMATCHED_GOLD:' + name)
        result.append(dict(model=k[0], group_id=k[1], cluster_id=a['cluster_id'], target=k[2], claim_id=k[3],
            comparison=name, base_condition=a['condition'], intervention_condition=b['condition'],
            base_variant=a['variant'], intervention_variant=b['variant'], base_request_id=a['request_id'], intervention_request_id=b['request_id'],
            base_raw_path=a['raw_path'], intervention_raw_path=b['raw_path'],
            source=a['source'], level=a['level'], state_dimension=a['state_dimension'],
            base_provenance=a['provenance_type'], intervention_provenance=b['provenance_type'],
            base_oracle=a['is_oracle'], intervention_oracle=b['is_oracle'],
            base_correct=a['correct'], intervention_correct=b['correct'],
            base_error=not a['correct'], base_success=a['correct'],
            rescue=not a['correct'] and b['correct'], harm=a['correct'] and not b['correct'],
            net=int(b['correct'])-int(a['correct']), review='DERIVED_PROVISIONAL'))
    return result


def intervention_summary(records, cfg):
    out = []
    strata = [('ALL', 'ALL')] + [(field, val) for field in ['source', 'level', 'state_dimension']
        for val in sorted({r[field] for r in records}, key=str)]
    for field, value in strata:
        rr = records if field == 'ALL' else [r for r in records if r[field] == value]
        if not rr: continue
        effect = paired_cluster_effect([(r['cluster_id'], int(r['intervention_correct']), int(r['base_correct'])) for r in rr],
            repetitions=cfg['bootstrap_repetitions'], seed=cfg['seed'])
        out.append(dict(model=rr[0]['model'], comparison=rr[0]['comparison'], group_key=field, group_value=value,
            net=effect, rescue=estimate(rr, 'rescue', cfg['bootstrap_repetitions']), harm=estimate(rr, 'harm', cfg['bootstrap_repetitions']),
            rescue_given_base_error=conditional_estimate(rr, 'rescue', 'base_error', cfg['bootstrap_repetitions'], cfg['seed']),
            harm_given_base_success=conditional_estimate(rr, 'harm', 'base_success', cfg['bootstrap_repetitions'], cfg['seed']),
            base_provenance=rr[0]['base_provenance'], intervention_provenance=rr[0]['intervention_provenance'],
            warning='Matched descriptive intervention, not additive causal fractions; new derivative review PROVISIONAL'))
    return out


def original_statistics(rr, cfg):
    """Original pair units are distinct from target-switch pairs."""
    pairs = collections.defaultdict(list)
    confusion = collections.Counter((r['gold']['label'], r['prediction'].get('label', 'INVALID')) for r in rr)
    for r in rr:
        if r['gold'].get('pair_id'): pairs[r['gold']['pair_id']].append(r)
    pr = []
    for pid, pair in pairs.items():
        if len(pair) != 2 or {r['gold']['label'] for r in pair} != set(LABELS[:2]):
            raise ValueError('ORIGINAL_PAIR_INCOMPLETE:' + pid)
        pr.append(dict(pair_id=pid, cluster_id=pair[0]['cluster_id'], correct=all(r['correct'] for r in pair),
            request_ids=[r['request_id'] for r in pair]))
    unknown = [r for r in rr if r['gold']['label'] == 'UNKNOWN']
    binary = [r for r in rr if r['gold']['label'] in LABELS[:2]]
    # UNKNOWN recall on its challenge is meaningful; precision/F1 on only that
    # challenge is not. The union panel has an intentionally sampled prevalence.
    tp = len([r for r in unknown if r['prediction'].get('label') == 'UNKNOWN'])
    fp = len([r for r in binary if r['prediction'].get('label') == 'UNKNOWN'])
    fn = len(unknown)-tp
    return dict(OriginalClaimAcc=estimate(rr, repetitions=cfg['bootstrap_repetitions']),
        OriginalBinaryClaimAcc=estimate(binary, repetitions=cfg['bootstrap_repetitions']),
        OriginalPairAcc=estimate(pr, repetitions=cfg['bootstrap_repetitions']),
        UnknownRecall=estimate(unknown, repetitions=cfg['bootstrap_repetitions']),
        unknown_precision_micro=tp/(tp+fp) if tp+fp else None,
        unknown_f1_micro=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
        unknown_f1_scope='DESCRIPTIVE_SELECTED_UNION_PREVALENCE_NOT_RELEASE_METRIC',
        confusion=[dict(gold=g, predicted=p, n=confusion[g,p]) for g in LABELS for p in OUTCOMES], pairs=pr)


def supplemental(cfg, root, per, factmatrix, switches, complete_models):
    """Return structured evidence for the report and write traceable tables."""
    complete = [r for r in per if r['model'] in complete_models]
    groups = unique(rows(root/'manifest/discovery/state_group_manifest.jsonl'), 'group_id') if complete else {}
    lookup = {(f['model'], f['group_id']): f for f in factmatrix}
    all_three = set(complete_models) == set(cfg['models'])
    common_fact = {gid for gid in groups if all_three and all(lookup.get((m,gid), {}).get('SeparateAllStatesCorrect') is True for m in cfg['models'])}
    common_joint = {gid for gid in groups if all_three and all(lookup.get((m,gid), {}).get('JointStateMapExact') is True for m in cfg['models'])}
    selection = []; joint_rows = []; role_rows = []; action_rows = []; original = {}; matches = []; contrasts = []; tracking = []; value_switch = []
    for model in complete_models:
        mr = [r for r in complete if r['model'] == model]
        original[model] = original_statistics([r for r in mr if r['condition'] == 'D_ORIG'], cfg)
        pick = lambda condition, variant='base': [r for r in mr if r['condition'] == condition and r['variant'] == variant]
        specs = [
            ('SELECT_VALUE', 'G_MULTI_VALUE', 'base', 'SELECT_to_MULTI'),
            ('SELECT_VALUE', 'G_TARGET_VALUE', 'base', 'SELECT_to_TARGET'),
            ('SELECT_VALUE', 'G_LOCAL', 'base', 'SELECT_to_LOCAL'),
            ('G_LOCAL', 'G_TARGET_VALUE', 'base', 'LOCAL_to_TARGET'),
            ('G_MULTI_VALUE', 'G_SHAM_VALUE', 'base', 'MULTI_to_SHAM'),
            ('G_MULTI_VALUE', 'G_TARGET_VALUE', 'base', 'MULTI_to_TARGET'),
            ('STATE_VERDICT', 'G_MULTI_VERDICT', 'base', 'VERDICT_to_MULTI'),
            ('STATE_VERDICT', 'G_TARGET_VERDICT', 'base', 'VERDICT_to_TARGET'),
            ('G_MULTI_VERDICT', 'G_SHAM_VERDICT', 'base', 'MULTI_VERDICT_to_SHAM'),
            ('G_MULTI_VALUE', 'G_MULTI_VALUE', 'renamed_reversed', 'MULTI_alias_plus_order'),
            ('G_SHAM_VALUE', 'G_SHAM_VALUE', 'renamed_reversed', 'SHAM_alias_plus_order'),
            ('STATE_VERDICT', 'LABEL_INTERFACE_CONTROL', 'ABC', 'VERDICT_to_ABC'),
            ('STATE_VERDICT', 'LABEL_INTERFACE_CONTROL', 'semantic', 'VERDICT_to_semantic')]
        for left, right, variant, name in specs:
            mm = matched_rows(pick(left), pick(right, variant), name)
            matches.extend(mm); contrasts.extend(intervention_summary(mm, cfg))
        for r in mr:
            gid = r['group_id']; f = lookup.get((model,gid), {})
            if r['condition'] == 'SELECT_VALUE':
                row = dict(model=model, group_id=gid, cluster_id=r['cluster_id'], source=r['source'], level=r['level'], state_dimension=r['state_dimension'],
                    request_id=r['request_id'], correct=r['correct'], SeparateAllStatesCorrect=f.get('SeparateAllStatesCorrect'),
                    JointStateMapExact=f.get('JointStateMapExact'), AllThreeSeparateCorrect=gid in common_fact if all_three else None,
                    AllThreeJointCorrect=gid in common_joint if all_three else None)
                selection.append(row)
            if r['condition'] == 'FACT_JOINT':
                cl = r['prediction'].get('classifier')
                joint_rows.append(dict(model=model, group_id=gid, cluster_id=r['cluster_id'], classifier=cl,
                    correct=r['correct'], binding_swap=cl=='VALUES_RIGHT_BINDING_WRONG', value_error=cl=='VALUE_ERROR',
                    incomplete=cl=='INCOMPLETE_OR_INVALID', request_id=r['request_id']))
            if r['condition'] == 'FACT_SEPARATE':
                state = next(s for s in groups[gid]['states'] if s['alias']==r['target'])
                role_rows.append(dict(model=model, group_id=gid, cluster_id=r['cluster_id'], role=state['role'],
                    condition='FACT_SEPARATE', state_dimension=r['state_dimension'], source=r['source'], level=r['level'],
                    correct=r['correct'], status=r['prediction']['status'], request_id=r['request_id']))
            if r['condition'] == 'ACTION_PARSE':
                pp = r['prediction']
                action_rows.append(dict(model=model, group_id=gid, cluster_id=r['cluster_id'], request_id=r['request_id'],
                    correct=r['correct'], operation_correct=bool(pp.get('operation_correct')),
                    target_lexical_correct=bool(pp.get('target_correct')), scope_correct=bool(pp.get('scope_correct')),
                    target_metric='LEXICAL_AUXILIARY_NOT_FULL_SEMANTIC_ACTION_TRUTH'))
        by_group = collections.defaultdict(list)
        for r in mr: by_group[r['group_id']].append(r)
        for gid, gr in by_group.items():
            sp = [r for r in gr if r['condition']=='G_DISTRACTOR_SWAP']
            if sp:
                if len(sp)!=2 or {r['variant'] for r in sp}!={'d1','d2'}: raise ValueError('SWAP_PAIR_INCOMPLETE')
                aa, bb = sorted(sp, key=lambda r:r['variant'])
                vt, d1, d2 = aa['gold']['value'], aa['gold']['distractor_value'], bb['gold']['distractor_value']
                if len({vt,d1,d2})!=3 or bb['gold']['value']!=vt: raise ValueError('SWAP_NOT_IDENTIFIABLE')
                hit=lambda r,d:r['prediction']['status']=='VALUE' and r['prediction'].get('value')==d
                tracking.append(dict(model=model, group_id=gid, cluster_id=aa['cluster_id'], correct=hit(aa,d1) and hit(bb,d2),
                    target_value=vt, distractor1=d1, distractor2=d2, request_d1=aa['request_id'], request_d2=bb['request_id'],
                    provenance='SYMBOLIC_CONTROL_ONLY'))
            sp=[r for r in gr if r['condition']=='SELECT_VALUE']
            if sp:
                if len(sp)!=2: raise ValueError('VALUE_TARGET_PAIR_INCOMPLETE')
                aa,bb=sp
                valid=all(r['prediction']['status']=='VALUE' for r in sp)
                same=valid and aa['prediction'].get('value')==bb['prediction'].get('value')
                value_switch.append(dict(model=model,group_id=gid,cluster_id=aa['cluster_id'],correct=all(r['correct'] for r in sp),
                    target_insensitive=same,valid_value_pair=valid,request_a=aa['request_id'],request_b=bb['request_id'],
                    state_dimension=aa['state_dimension']))
                if same:
                    for r in sp: r['label_evidence'].append('TARGET_INSENSITIVE_RESPONSE')
            # Behavioral gap across independent requests, never an internal readout claim.
            for r in gr:
                if r['condition']=='STATE_VERDICT' and r['correct'] is False:
                    select=next((s for s in sp if s['target']==r['target']),None)
                    if select and select['correct']: r['label_evidence'].append('REPORT_VERDICT_GAP')
    aggregates=[]
    for model in complete_models:
        for predicate in ['ALL','SeparateAllStatesCorrect','JointStateMapExact','AllThreeSeparateCorrect','AllThreeJointCorrect']:
            rr=[r for r in selection if r['model']==model]
            e=conditional_estimate(rr,'correct',predicate,cfg['bootstrap_repetitions'],cfg['seed'])
            aggregates.append(dict(model=model,metric='SelectValueAcc',conditional_on=predicate,**e))
        for predicate,common in [('AllThreeSeparateCorrect',common_fact),('AllThreeJointCorrect',common_joint)]:
            rr=[dict(r,common_eligible=r['group_id'] in common if all_three else None) for r in switches if r['model']==model and not r['invariant']]
            aggregates.append(dict(model=model,metric='SSA',conditional_on=predicate,
                **conditional_estimate(rr,'correct','common_eligible',cfg['bootstrap_repetitions'],cfg['seed'])))
    summary=dict(status='COMPLETE_PROVISIONAL' if all_three else 'PARTIAL_OR_NOT_RUN',complete_models=list(complete_models),
        common_fact_groups=len(common_fact) if all_three else None,common_joint_groups=len(common_joint) if all_three else None,
        common_fact_cluster_ids=sorted({groups[g]['cluster_id'] for g in common_fact}) if all_three else [],
        original=original,interventions=contrasts,conditional_selection=aggregates,joint={},facts={},fact_status_counts={},action={},tracking={},value_switch={},
        AllRequiredFactsCorrect=dict(status='NOT_APPLICABLE',reason='No complete per-premise query-to-certificate coverage adapter; PRE query is not automatically all required premises.'),
        review='PROVISIONAL',mechanism_proven=False)
    for model in complete_models:
        rr=[r for r in joint_rows if r['model']==model]
        summary['joint'][model]={k:estimate(rr,k,cfg['bootstrap_repetitions']) for k in ['correct','binding_swap','value_error','incomplete']}
        rr=[r for r in role_rows if r['model']==model]
        summary['facts'][model]={role:estimate([r for r in rr if r['role']==role],repetitions=cfg['bootstrap_repetitions']) for role in sorted({r['role'] for r in rr})}
        summary['fact_status_counts'][model]={role:dict(collections.Counter(r['status'] for r in rr if r['role']==role)) for role in sorted({r['role'] for r in rr})}
        summary['action'][model]={k:estimate([r for r in action_rows if r['model']==model],k,cfg['bootstrap_repetitions']) for k in ['correct','operation_correct','target_lexical_correct','scope_correct']}
        summary['tracking'][model]=estimate([r for r in tracking if r['model']==model],repetitions=cfg['bootstrap_repetitions'])
        summary['value_switch'][model]={k:estimate([r for r in value_switch if r['model']==model],k,cfg['bootstrap_repetitions']) for k in ['correct','target_insensitive','valid_value_pair']}
    for name, data in [('all_matched_controls',matches),('selection_conditionals',aggregates),('joint_classification',joint_rows),
            ('fact_report_by_state_role',role_rows),('action_parse_components',action_rows),('distractor_tracking',tracking),('value_target_switch',value_switch)]:
        csvwrite(root/'tables'/(name+'.csv'),data)
    write(root/'scores/supplemental_analyses.json',summary)
    return summary, matches


def metric_text(e):
    if not e or e.get('estimate') is None: return 'NOT_RUN/N/A（无合格分母）'
    text=f"{e['numerator']}/{e['denominator']} 观测单位（{e['clusters']} worlds），world-macro={e['estimate']:.4f}，95% CI={e['ci95']}"
    if e.get('zero_event_cluster_upper95') is not None:
        text+=f"；零事件的退化区间不表示零风险，额外独立 world 伯努利假设下事件上界={e['zero_event_cluster_upper95']:.4f}"
    return text


def completed_answers(cfg, root, supplement, comparisons, switch_aggregates):
    """Ten answers with explicit scope/evidence; no preordained mechanism verdict."""
    out={}
    out[1]='原资产哈希检查和当前接口验收见 acceptance_checks.json；原数据审核按用户声明记录 PASS，派生问题/实际图像呈现仍为 PROVISIONAL。模型完整执行不等于已排除标注或观察条件问题。原题指标（仅冻结 discovery 的 D_ORIG，不是全 release）：'
    for m, rec in supplement['original'].items():
        out[1]+=f"\n   {m}: ClaimAcc {metric_text(rec['OriginalClaimAcc'])}；OriginalPairAcc {metric_text(rec['OriginalPairAcc'])}；UNKNOWN recall {metric_text(rec['UnknownRecall'])}。"
    out[1]+=' 证据 scores/supplemental_analyses.json/original 和逐请求 gold/raw 路径；接口反例包括保留的 v2.3 27B 非标量响应，详见 examples_cn.md。'
    plan=load(root/'manifest/discovery/request_plan.json')
    out[2]=f"冻结 {plan['group_count']} 组/{plan['group_clusters']} worlds；原题覆盖 {plan['coverage_pairs']} 对。机制适配仅 PRE_POST 与 OBJECT_ARGUMENT；后者是 L1 数量对象控制，不能冒充 L3/L4 状态推理。L3 当前无经验证适配。每组来源、维度、父 ID 见 manifest/discovery/state_group_manifest.jsonl；排除原因见 reports/l3_feasibility.json。确定性构造计数无抽样 CI。"
    out[3]='独立 FACT_SEPARATE 的状态角色分组：'
    for m, dd in supplement['facts'].items():
        out[3]+='\n   '+m+'：'+'；'.join(k+' '+metric_text(v) for k,v in dd.items())+'。'
    out[3]+=' PRE/对象数量的独立报告与 POST 推导结果不可合并称局部感知准确率。主分母保留 INVALID 和 UNDETERMINED，它们不自动成为事实内容错误；状态分布见 supplemental_analyses.json/fact_status_counts。完整充分前提适配 N/A，不能以一个 PRE 答对认定所有前提已正确提取；ACTION_PARSE 目标字段只有词汇辅助评分。证据 tables/fact_report_by_state_role.csv、tables/action_parse_components.csv。'
    out[4]='FACT_JOINT 完整映射、值错和归属交换分开：'
    for m, dd in supplement['joint'].items():
        out[4]+='\n   '+m+'：'+'；'.join(k+' '+metric_text(v) for k,v in dd.items())+'。'
    out[4]+=' 证据 tables/joint_classification.csv；缺字段/不确定不是“值对但归属错”。案例类别即使未发生也保留 NOT_OBSERVED。'
    out[5]='TARGET-only SELECT_VALUE 两次均正确以及恒值响应：'
    for m, dd in supplement['value_switch'].items():
        out[5]+='\n   '+m+'：PairValueAcc '+metric_text(dd['correct'])+'；恒值率 '+metric_text(dd['target_insensitive'])+'。'
    for e in switch_aggregates:
        if e['conditional_on']=='ALL': out[5]+=f"\n   {e['model']} {e['metric']}：{metric_text(e)}。"
    out[5]+=' 证据 tables/value_target_switch.csv、tables/state_switch_metrics.csv；恒标签/二元反转是响应模式，不是机制证据。不变控制为预证 C/C 命题，不冒称不受动作影响的物理事实。'
    out[6]='正确事实子集的选择差距（独立请求的行为关系，不是内部中介）：'
    for e in supplement['conditional_selection']:
        if e['conditional_on'] in ['SeparateAllStatesCorrect','AllThreeSeparateCorrect']:
            out[6]+=f"\n   {e['model']} {e['metric']} | {e['conditional_on']}：{metric_text(e)}；cohort worlds={e['cohort_clusters']}，bootstrap 空分母比例={e['zero_denominator_bootstrap_fraction']}。"
    out[6]+=' 证据 tables/selection_conditionals.csv、tables/conditional_metrics.csv；资格率和共同子集小的限制必须保留。'
    out[7]='主对比仅非退化整数值域、固定目标与不同干扰值的 G_MULTI/G_SHAM，全部 eligible 请求为分母：'
    for e in comparisons:
        out[7]+=f"\n   {e['model']} {e['contrast']}={e['effect']}，95% CI={e['ci95']}，{e['n_rows']} 匹配请求/{e['n_clusters']} worlds。"
    out[7]+=' 范围是来源真值构成的 oracle 文本任务，不等于视觉机制发生率。证据 scores/primary_comparisons.json、tables/primary_matched_controls.csv。二元关系只描述，标签 WSA 不提供识别力；零事件 [0,0] 不等于零风险。'
    scoped=root/'scores/primary_comparisons_by_scope.json'
    if scoped.exists():
        for e in load(scoped):
            if e['model']=='qwen35_9b' and e['group_key']=='state_dimension':
                out[7]+=f"\n   9B 分维度 {e['group_value']} / {e['contrast']}={e['effect']}，95% CI={e['ci95']}，{e['n_rows']} 对/{e['n_clusters']} worlds；L1 对象控制与 L4 PRE_POST 不互相替代。"
    out[8]='所有 oracle 层级和接口报告完整配对救回、破坏、净差及条件分母；不把 oracle 提升相加为原因比例。别名和顺序同时变化，是联合扰动，不能单独识别位置效应。主要 9B 结果：'
    for e in supplement['interventions']:
        if e['model']=='qwen35_9b' and e['group_key']=='ALL':
            net=e['net']; out[8]+=f"\n   {e['comparison']}：净差={net['effect']}，95% CI={net['ci95']}，{net['n_rows']} 对/{net['n_clusters']} worlds；救回 {metric_text(e['rescue'])}；破坏 {metric_text(e['harm'])}。"
    out[8]+=' 证据 tables/all_matched_controls.csv、scores/supplemental_analyses.json/interventions；全部三模型/分组均保留。'
    for m,e in supplement['tracking'].items():
        out[8]+=f"\n   {m} 固定目标、替换非目标值的 DistractorTrackingRate（SYMBOLIC_CONTROL_ONLY）：{metric_text(e)}；证据 tables/distractor_tracking.csv。"
    out[9]=f"三模型使用相同预选共同核心，未按小模型失败选 27B；共同 SeparateAllStatesCorrect 子集={supplement['common_fact_groups']} worlds，共同 JointStateMapExact 子集={supplement['common_joint_groups']} worlds。各自子集与共同子集必须区分。27B 的事实/状态和干扰指标见第 3–7 项，所有大模型答对的小模型反例也按固定种子保留。相同 discovery world 上的尺度差异不是独立确认，也不是参数量的因果效应。证据 tables/selection_conditionals.csv、examples_cn.md。"
    decision=load(root/'next_stage_decision.json'); invalid=decision['core_output_contract_invalid']
    out[10]=f"当前候选标签：{decision['candidate']}；下一步检查优先级：{decision['priority']}。9B 共同核心严格输出契约无效为 {invalid['n']}/{invalid['denominator']} 请求，涉及 {invalid['worlds']} worlds（描述性计数，逐行证据在 next_stage_decision.json）；报告归属交换涉及 {decision['observed_report_binding_swap_worlds']} worlds。候选规则仅看预先指定的 9B 主对比，不从多个子组挑显著结果。新增派生呈现尚未独立人工复核，且完整充分前提查询适配不足，不能以统计关联宣布神经机制。若匹配 SHAM 同样容易命中干扰值，则削弱定向非目标干扰；若另行验证的统一接口消除差距，则削弱状态机制解释；若正确前提子集 worlds 太少，则不能区分计算与输入。见 next_stage_decision.json 和 examples_cn.md 的反例；本轮到此停止，不自动启动下一阶段。"
    return out
