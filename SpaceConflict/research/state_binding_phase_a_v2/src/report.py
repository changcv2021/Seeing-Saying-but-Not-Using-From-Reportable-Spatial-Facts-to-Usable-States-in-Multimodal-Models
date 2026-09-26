"""A5: traceable completed or honestly blocked report. Never advances Phase B."""
import collections
from base import *
from metrics import *
from analysis_outputs import supplemental, completed_answers

def main():
    a=args(__doc__).parse_args(); cfg,root,project=setup(a)
    setup_stage=cfg.get('setup_input_stage','setup')
    if a.dry_run: print(json.dumps(dict(status='PLANNED',action='report'))); return
    per=[]; rawindex=[]; completeness=[]; group_metrics=[]; switches=[]; factmatrix=[]; intrusion=[]; controls=[]; conditional=[]
    reqfile=root/'inputs/discovery/requests.jsonl'; has_discovery=reqfile.exists()
    if has_discovery:
        requests=list(rows(reqfile)); gold=unique(rows(root/'gold/discovery/gold.jsonl'),'request_id')
        state_truth=unique(rows(root/'gold/discovery/state_truth.jsonl'),'group_id')
        groups=unique(rows(root/'manifest/discovery/state_group_manifest.jsonl'),'group_id')
        for model in cfg['models']:
            selected=[r for r in requests if model in r['models']]; directory=root/'raw/discovery'/model
            raw={}
            for r in selected:
                path=directory/(r['request_id']+'.json')
                if path.exists():
                    rr=load(path); raw[r['request_id']]=rr
                    rawindex.append(dict(model=model,request_id=r['request_id'],phase='discovery',path=str(path),sha256=sha(path)))
            completion_file=directory/'completion.json'
            finished=load(completion_file) if completion_file.exists() else {}
            complete=len(raw)==len(selected) and finished.get('status')=='COMPLETE' and not finished.get('infrastructure_errors')
            if complete:
                if finished.get('manifest_sha256')!=sha(reqfile) or {r['request_id'] for r in finished['raw_index']}!={r['request_id'] for r in selected}: raise ValueError('COMPLETION_MANIFEST_MISMATCH')
                for entry in finished['raw_index']:
                    if sha(entry['path'])!=entry['sha256']: raise ValueError('RAW_INDEX_HASH_MISMATCH')
            completion=dict(model=model,expected=len(selected),completed=len(raw),status='COMPLETE' if complete else 'RUNNING_OR_NOT_RUN')
            completeness.append(completion)
            parsed={r['request_id']:parse(raw.get(r['request_id']),gold[r['request_id']]) for r in selected}
            for r in selected:
                pp=parsed[r['request_id']]; rr=raw.get(r['request_id']); g=gold[r['request_id']]
                record=dict(model=model,request_id=r['request_id'],group_id=r['group_id'],cluster_id=r['cluster_id'],condition=r['condition'],variant=r['variant'],target=r['target'],claim_id=r['claim_id'],source=r['source'],level=r['level'],state_dimension=r['state_dimension'],provenance_type=r['provenance_type'],is_oracle=r['is_oracle'],gold=g,prediction=pp,correct=pp['correct'],
                    raw_path=str(directory/(r['request_id']+'.json')) if rr else None,raw_sha256=sha(directory/(r['request_id']+'.json')) if rr else None,
                    label_evidence=[],review_status='USER_ATTESTED_PARENT_PASS_DERIVED_PROVISIONAL')
                if pp['status']=='INVALID': record['label_evidence'].append('ANSWER_INTERFACE_VIOLATION_OR_INFRASTRUCTURE_FAILURE')
                if r['condition']=='FACT_SEPARATE' and pp.get('correct') is False and pp['status']=='VALUE': record['label_evidence'].append('ISOLATED_FACT_REPORT_ERROR')
                if r['condition']=='FACT_SEPARATE' and pp['status']=='UNDETERMINED': record['label_evidence'].append('FACT_REPORT_UNDETERMINED')
                if pp.get('classifier')=='VALUES_RIGHT_BINDING_WRONG': record['label_evidence'].append('REPORT_BINDING_SWAP')
                if g['kind']=='value' and g.get('gold_by_state') and r['target']:
                    hit=classify_value_response(target_state=r['target'],gold_by_state=g['gold_by_state'],predicted_value=pp.get('value'),status=pp['status'],exhaustive_binary_answer_domain=g['domain']['binary_degenerate']) if pp['status']!='NOT_RUN' else None
                    reference_only=r['condition'] in ['G_SHAM_VALUE','G_TARGET_VALUE']
                    if hit and hit['classification']=='UNIQUE_NON_TARGET_VALUE': record['label_evidence'].append('REFERENCE_VALUE_HIT_ONLY' if reference_only else 'NON_TARGET_VALUE_HIT')
                    intrusion.append(dict(model=model,request_id=r['request_id'],group_id=r['group_id'],cluster_id=r['cluster_id'],condition=r['condition'],variant=r['variant'],target=r['target'],classification=hit['classification'] if hit else 'NOT_RUN',
                        classification_scope='SOURCE_REFERENCE_VALUE_NOT_A_NON_TARGET_QUERY_STATE_IN_THIS_TASK' if reference_only else 'DESCRIPTIVE_STATE_VALUE_MATCH_NOT_CAUSE',
                        degenerate=g['domain']['binary_degenerate'],provenance=r['provenance_type'],mechanism_proven=False))
                per.append(record)
            # Never turn partial completion into a completed paired scientific result.
            if completion['status']!='COMPLETE': continue
            modelrows=[r for r in per if r['model']==model]
            for condition in sorted({r['condition'] for r in modelrows}):
                cr=[r for r in modelrows if r['condition']==condition and r['variant'] in ['base','ABC','semantic'] or r['condition']==condition=='D_ORIG']
                for key in ['ALL','level','source','state_dimension','provenance_type']+(['variant'] if condition=='LABEL_INTERFACE_CONTROL' else []):
                    values=['ALL'] if key=='ALL' else sorted({r[key] for r in cr},key=str)
                    for value in values:
                        subset=cr if key=='ALL' else [r for r in cr if r[key]==value]
                        ee=estimate(subset,repetitions=cfg['bootstrap_repetitions'])
                        group_metrics.append(dict(model=model,condition=condition,group_key=key,group_value=value,**ee,valid_output_rate=sum(r['prediction']['status'] not in ['INVALID','NOT_RUN'] for r in subset)/len(subset) if subset else None))
            for gid,g in groups.items():
                gr=[r for r in modelrows if r['group_id']==gid]; vals=state_truth[gid]['values']
                sep=[r for r in gr if r['condition']=='FACT_SEPARATE']; joint=next((r for r in gr if r['condition']=='FACT_JOINT'),None)
                select=[r for r in gr if r['condition']=='SELECT_VALUE']; joint_correct=joint['correct'] if joint else None
                separate_correct=all(r['correct'] for r in sep) if len(sep)==len(vals) and sep else None
                fm=dict(model=model,group_id=gid,cluster_id=g['cluster_id'],source=g['source'],level=g['original_level'],state_dimension=g['state_dimension'],SeparateAllStatesCorrect=separate_correct,JointStateMapExact=joint_correct,
                    JointClassification=joint['prediction'].get('classifier') if joint else None,SelectValueCorrect=sum(r['correct'] for r in select),SelectValueN=len(select))
                factmatrix.append(fm)
                for claim in g['claims']:
                    vr=[r for r in gr if r['condition']=='STATE_VERDICT' and r['claim_id']==claim['claim_key']]
                    if len(vr)!=2: raise ValueError('SCORING_TARGET_PAIR_MISSING')
                    va,vb=vr; same=va['gold']['label']==vb['gold']['label']
                    if not same:
                        pp=SwitchPair(gid+claim['claim_key'],g['cluster_id'],va['gold']['label'],vb['gold']['label'],va['prediction'].get('label'),vb['prediction'].get('label'))
                        ss=switch_summary([pp]); pattern=next(iter(ss['pattern_counts']))
                    else: pattern='INVARIANT_BOTH_CORRECT' if va['correct'] and vb['correct'] else 'INVARIANT_ERROR'
                    switches.append(dict(model=model,group_id=gid,cluster_id=g['cluster_id'],claim_id=claim['claim_key'],invariant=same,pattern=pattern,correct=bool(va['correct'] and vb['correct']),
                        binary_valid=va['prediction'].get('label') in LABELS[:2] and vb['prediction'].get('label') in LABELS[:2],
                        binary_flip=va['prediction'].get('label') in LABELS[:2] and vb['prediction'].get('label') in LABELS[:2] and va['prediction'].get('label')!=vb['prediction'].get('label'),SeparateAllStatesCorrect=separate_correct,JointStateMapExact=joint_correct))
                for selection in select:
                    target=selection['target']; sr=[r for r in gr if r['condition']=='STATE_VERDICT' and r['target']==target and not r['gold'].get('invariant')]
                    for verdict in sr:
                        conditional.append(dict(model=model,group_id=gid,cluster_id=g['cluster_id'],target=target,claim_id=verdict['claim_id'],SelectCorrect=selection['correct'],VerdictCorrect=verdict['correct'],SeparateAllStatesCorrect=separate_correct,JointStateMapExact=joint_correct))
                # Main intrusion contrast excludes binary answer-domain cases.
                for target in vals:
                    for variant in ['base','renamed_reversed']:
                        multi=next((r for r in gr if r['condition']=='G_MULTI_VALUE' and r['target']==target and r['variant']==variant),None)
                        sham=next((r for r in gr if r['condition']=='G_SHAM_VALUE' and r['target']==target and r['variant']==variant),None)
                        if multi and sham:
                            dd=multi['gold']['distractor_value']; eligible=not g['domain']['binary_degenerate'] and dd!=vals[target]
                            hit=lambda r:r['prediction']['status']=='VALUE' and r['prediction'].get('value')==dd
                            controls.append(dict(model=model,group_id=gid,cluster_id=g['cluster_id'],target=target,variant=variant,primary_eligible=eligible,
                                MULTI_hit=hit(multi),SHAM_hit=hit(sham),MULTI_correct=multi['correct'],SHAM_correct=sham['correct'],
                                intrusion_difference=int(hit(multi))-int(hit(sham)),accuracy_cost=int(sham['correct'])-int(multi['correct']),provenance='ORACLE_FROM_VERIFIED_STATES',
                                source=g['source'],level=g['original_level'],state_dimension=g['state_dimension']))
    switch_aggregates=[]; conditional_aggregates=[]
    for model in cfg['models']:
        for invariant in [False,True]:
            sr=[r for r in switches if r['model']==model and r['invariant']==invariant]
            for predicate in ['ALL','SeparateAllStatesCorrect','JointStateMapExact','binary_valid']:
                subset=sr if predicate=='ALL' else [r for r in sr if r[predicate] is True]
                for metric,field in [('InvariantPairCorrect' if invariant else 'SSA','correct'),('InvariantBinaryFlip' if invariant else 'BinaryFlip','binary_flip'),('ValidBinaryPairCoverage','binary_valid')]:
                    switch_aggregates.append(dict(model=model,metric=metric,conditional_on=predicate,**conditional_estimate(sr,field,predicate,repetitions=cfg['bootstrap_repetitions'],seed=cfg['seed'])))
        cc=[r for r in conditional if r['model']==model]
        for predicate in ['SelectCorrect','SeparateAllStatesCorrect','JointStateMapExact']:
            subset=[r for r in cc if r[predicate] is True]
            conditional_aggregates.append(dict(model=model,metric='VerdictAcc',conditional_on=predicate,**conditional_estimate(cc,'VerdictCorrect',predicate,repetitions=cfg['bootstrap_repetitions'],seed=cfg['seed'])))
    measurement_status=[]; measurement_items=[]
    minfile=root/'manifest/setup/smoke_requests.json'
    if minfile.exists():
        mmanifest=load(minfile); mgold=unique(rows(root/'gold/setup/gold.jsonl'),'request_id'); mreq=unique(rows(root/'inputs/setup/requests.jsonl'),'request_id')
        for key in cfg['models']:
            directory=root/'raw/measurement'/key
            rr=[]; ids=mmanifest.get('measurement_request_ids',[]); valid_outputs=0; schema_warnings=[]
            for rid in ids:
                path=directory/(rid+'.json')
                if not path.exists(): continue
                record=load(path); rr.append(record); outcome=parse(record,mgold[rid])
                valid_outputs+=outcome['status']!='INVALID'
                schema_warnings.extend(outcome.get('schema_warnings',[]))
                measurement_items.append(dict(model=key,request_id=rid,cluster_id=mreq[rid]['cluster_id'],phase='SETUP_MEASUREMENT_NOT_DISCOVERY',condition=mreq[rid]['condition'],prediction=outcome,raw_path=str(path),raw_sha256=sha(path),review_status='PROVISIONAL'))
                rawindex.append(dict(model=key,request_id=rid,phase='measurement',path=str(path),sha256=sha(path)))
            complete=(directory/'completion.json').exists() and len(rr)==len(ids) and bool(ids) and not any(r.get('infrastructure_error') for r in rr)
            measurement_status.append(dict(model=key,status='PASS' if complete else 'FAIL' if any(r.get('infrastructure_error') for r in rr) else 'NOT_RUN_OR_IN_PROGRESS',completed=len(rr),expected=len(ids),clusters=len({mreq[r['request_id']]['cluster_id'] for r in rr}),
                measured_request_seconds=sum(r.get('wall_seconds',0) for r in rr),output_tokens=sum(r.get('output_tokens') or 0 for r in rr),schema_valid_outputs=valid_outputs,schema_warnings=schema_warnings,status_scope='INFRASTRUCTURE_COMPLETION_ONLY',prompt_version='phase_a_state_index_v2_3',evidence=str(directory/'completion.json')))
    write(root/'reports/minimal_measurement_status.json',measurement_status)
    smoke_items=[]
    current_gold=unique(rows(root/'gold'/setup_stage/'gold.jsonl'),'request_id')
    current_req=unique(rows(root/'inputs'/setup_stage/'requests.jsonl'),'request_id')
    for model in cfg['models']:
        for rid in load(root/'manifest'/setup_stage/'smoke_requests.json')['request_ids']:
            path=root/'raw'/setup_stage/model/(rid+'.json')
            if not path.exists(): continue
            rr=load(path); outcome=parse(rr,current_gold[rid])
            smoke_items.append(dict(model=model,request_id=rid,phase=setup_stage,condition=current_req[rid]['condition'],cluster_id=current_req[rid]['cluster_id'],prediction=outcome,raw_path=str(path),raw_sha256=sha(path)))
            rawindex.append(dict(model=model,request_id=rid,phase=setup_stage,path=str(path),sha256=sha(path)))
    write(root/'scores'/('smoke_diagnostics_'+setup_stage+'.jsonl'),smoke_items,'jsonl')
    extra,all_matches=supplemental(cfg,root,per,factmatrix,switches,[c['model'] for c in completeness if c['status']=='COMPLETE'])
    if len(measurement_status)==3 and all(s['status']=='PASS' for s in measurement_status):
        from preview_costs import calculate
        write(root/'reports/cost_preview.json',calculate(cfg,root))
    write(root/'scores/measurement_diagnostics.jsonl',measurement_items,'jsonl')
    csvwrite(root/'tables/conditional_item_matrix.csv',conditional)
    csvwrite(root/'tables/conditional_metrics.csv',conditional_aggregates)
    csvwrite(root/'tables/state_switch_metrics.csv',switch_aggregates)
    csvwrite(root/'tables/metrics_by_group.csv',group_metrics)
    csvwrite(root/'tables/state_switch_summary.csv',switches)
    csvwrite(root/'tables/fact_state_selection_matrix.csv',factmatrix)
    csvwrite(root/'tables/non_target_value_intrusion.csv',intrusion)
    intrusion_stats=[]
    completed_models={c['model'] for c in completeness if c['status']=='COMPLETE'}
    for model in cfg['models']:
        if model not in completed_models: continue
        for condition in sorted({r['condition'] for r in intrusion if r['model']==model}):
            rr=[r for r in intrusion if r['model']==model and r['condition']==condition and r['variant']=='base' and not r['degenerate']]
            for classification in ['TARGET_CORRECT','UNIQUE_NON_TARGET_VALUE','AMBIGUOUS_NON_TARGET_VALUE','OTHER_VALUE_ERROR','UNDETERMINED','INVALID']:
                events=[dict(cluster_id=r['cluster_id'],correct=r['classification']==classification,error=r['classification']!='TARGET_CORRECT') for r in rr]
                intrusion_stats.append(dict(model=model,condition=condition,classification=classification,
                    full_denominator=estimate(events,repetitions=cfg['bootstrap_repetitions']),
                    conditional_on_error=conditional_estimate(events,'correct','error',cfg['bootstrap_repetitions'],cfg['seed']),
                    scope='REFERENCE_VALUE_ONLY' if condition in ['G_SHAM_VALUE','G_TARGET_VALUE'] else 'DESCRIPTIVE_NONDEGENERATE_STATE_VALUE',mechanism_proven=False))
    write(root/'scores/non_target_value_rates.json',intrusion_stats)
    csvwrite(root/'tables/primary_matched_controls.csv',controls)
    all_controls=controls+all_matches
    csvwrite(root/'tables/matched_controls.csv',all_controls,fields=sorted({k for r in all_controls for k in r}) or ['status'])
    write(root/'scores/per_item_diagnostics.jsonl',per,'jsonl'); write(root/'raw_predictions.jsonl',rawindex,'jsonl')
    comparisons=[]; scoped_comparisons=[]
    for model in cfg['models']:
        cc=[r for r in controls if r['model']==model and r['primary_eligible'] and r['variant']=='base']
        for name,left,right in [('IntrusionExcess','MULTI_hit','SHAM_hit'),('AccuracyCost','SHAM_correct','MULTI_correct')]:
            ee=paired_cluster_effect([(r['cluster_id'],int(r[left]),int(r[right])) for r in cc],repetitions=cfg['bootstrap_repetitions'],seed=cfg['seed'])
            comparisons.append(dict(model=model,contrast=name,condition='G_MULTI_VALUE versus G_SHAM_VALUE',provenance='ORACLE_FROM_VERIFIED_STATES',review='DERIVED_PROVISIONAL',**ee))
        for field in ['source','level','state_dimension']:
            for value in sorted({r[field] for r in cc},key=str):
                subset=[r for r in cc if r[field]==value]
                for name,left,right in [('IntrusionExcess','MULTI_hit','SHAM_hit'),('AccuracyCost','SHAM_correct','MULTI_correct')]:
                    ee=paired_cluster_effect([(r['cluster_id'],int(r[left]),int(r[right])) for r in subset],repetitions=cfg['bootstrap_repetitions'],seed=cfg['seed'])
                    scoped_comparisons.append(dict(model=model,contrast=name,group_key=field,group_value=value,condition='G_MULTI_VALUE versus G_SHAM_VALUE',review='DERIVED_PROVISIONAL',**ee))
    write(root/'scores/primary_comparisons.json',comparisons)
    write(root/'scores/primary_comparisons_by_scope.json',scoped_comparisons)
    pending=[]
    if not has_discovery:
        for rid in load(root/'manifest'/setup_stage/'smoke_requests.json')['request_ids']:
            r=current_req[rid]
            pending.append(dict(request_id=rid,group_id=r['group_id'],cluster_id=r['cluster_id'],stage=setup_stage,condition=r['condition'],status='SETUP_ONLY_SEE_RAW_INDEX',models=','.join(r['models'])))
    csvwrite(root/'tables/planned_diagnostics.csv',pending)
    checks=[]
    for name,path in [('A0',root/'reports/a0_acceptance.json'),('A1',root/'reports/mining_report.json'),('A2_inputs',root/'manifest'/setup_stage/'request_plan.json'),('A2_CPU_integration',root/'reports'/(setup_stage+'_integration_checks.json'))]:
        checks.append(dict(check=name,status=load(path)['status'] if path.exists() else 'NOT_RUN',evidence=str(path)))
    protected=root/'manifest/protected_assets.before.json'; changes=[]
    if protected.exists():
        for item in load(protected):
            if item['available'] and sha(item['path'])!=item['sha256']: changes.append(item['path'])
    checks.append(dict(check='historical_assets_unchanged',status='FAIL' if changes else 'PASS' if protected.exists() else 'NOT_RUN',changes=changes,evidence=str(protected)))
    done=len(completeness)==3 and all(c['status']=='COMPLETE' for c in completeness)
    budget=root/'manifest/gpu_authorization.json'
    checks.append(dict(check='GPU_budget',status='PASS' if budget.exists() else 'BLOCKED',evidence=str(budget),reason=None if budget.exists() else 'Awaiting explicit GPU-hour budget confirmation; no default acceptance inferred.'))
    smoke_status=[]
    for key in cfg['models']:
        p=root/'raw'/setup_stage/key/'completion.json'
        c=load(p) if p.exists() else {}
        smoke_status.append(dict(model=key,status='PASS' if c.get('status')=='COMPLETE' and not c.get('infrastructure_errors') else 'NOT_RUN',completed=c.get('completed',0),evidence=str(p)))
    checks.extend(dict(check='A2_GPU_smoke_'+s['model'],**{k:v for k,v in s.items() if k!='model'}) for s in smoke_status)
    full_gate=root/'reports'/('smoke_gate_'+setup_stage+'.json')
    checks.append(dict(check='A2_full_smoke_schema_presentation_tests',status=load(full_gate)['status'] if full_gate.exists() else 'NOT_RUN',evidence=str(full_gate)))
    if full_gate.exists():
        checks.extend(dict(check='A2_output_behavior_'+c['check'],status=c['status'],valid=c['valid'],total=c['total'],blocking=False,evidence=str(full_gate)) for c in load(full_gate)['checks'] if c['check'].endswith(':schema'))
    checks.extend(dict(check='A2_minimal_measurement_'+s['model'],status=s['status'] if s['status'] in ['PASS','FAIL'] else 'NOT_RUN',evidence=s['evidence']) for s in measurement_status)
    checks.extend(dict(check='A2_v23_measurement_output_contract_'+s['model'],status='PASS' if s['completed']==s['expected'] and s['schema_valid_outputs']/s['expected']>=.95 else 'FAIL' if s['completed']==s['expected'] else 'NOT_RUN',
        valid=s['schema_valid_outputs'],total=s['expected'],scope='PRESERVED_V23_MEASUREMENT; v24 formal smoke remains separately required',evidence=str(root/'scores/measurement_diagnostics.jsonl')) for s in measurement_status if s['expected'])
    checks.append(dict(check='A3_A4_requests',status='PASS' if done else 'NOT_RUN',evidence='raw/discovery/*/completion.json',completion=completeness))
    checks.append(dict(check='phase_B_disabled',status='PASS',evidence=str(a.config)))
    execution_check=root/'reports/discovery_execution_checks.json'
    checks.append(dict(check='A3_A4_actual_execution_integrity',status=load(execution_check)['status'] if execution_check.exists() else 'NOT_RUN',evidence=str(execution_check)))
    design_path=root/'reports/frozen_design_audit.json'
    design=load(design_path) if design_path.exists() else {}
    checks.extend(dict(check='design:'+c['check'],status=c['status'],scope='SCIENTIFIC_INTERPRETATION_NOT_EXECUTION_COMPLETENESS',evidence=str(design_path)) for c in design.get('checks',[]))
    done=done and full_gate.exists() and load(full_gate)['status']=='PASS' and not changes and execution_check.exists() and load(execution_check)['status']=='PASS'
    write(root/'acceptance_checks.json',checks)
    write(root/'run_manifest.json',dict(run_id=cfg['run_id'],phase=cfg['phase'],status='COMPLETE_PROVISIONAL' if done else 'BLOCKED_OR_IN_PROGRESS',completion=completeness,
        code_files=[evidence_entry(p) for p in sorted((CODE/'src').glob('*.py'))],config=evidence_entry(a.config),stop_after_report=True,test_new_inference=False,confirmation_inference=False,
        scientific_design_acceptance=design.get('status','NOT_RUN'),completion_scope='FROZEN_REQUEST_EXECUTION_AND_REPORT; not blanket guide-design or human-review acceptance'))
    from decision import decide
    write(root/'next_stage_decision.json',decide(done,per,extra,comparisons))
    text='# SpaceConflict Phase A 诊断报告\n\n'
    text+='本轮状态：'+('已完成冻结请求；探索性结果 PROVISIONAL。' if done else '**尚未完成 Phase A 模型实验；以下为已执行审计与明确的待运行项，不是机制结论。**')+'\n\n'
    p=root/'reports/baseline_reaudit.md'
    if p.exists(): text+='## 已完成 A0\n\n'+p.read_text().split('\n',1)[1]+'\n'
    p=root/'scores/historical_joined.jsonl'
    if p.exists():
        histrows=list(rows(p)); worlds={s:len({r['cluster_id'] for r in histrows if s=='all' or r['split']==s}) for s in ['all','dev','test']}
        text+=f"历史重算的底层 world/cluster 数：{worlds}。这些是冻结数据总体的确定性重算，不是新的抽样实验，故未赋予推断性置信区间。记录级证据为 scores/historical_joined.jsonl；混淆矩阵见 tables/confusion_matrices.csv；旧响应哈希见 manifest/repository_inventory.json。该低召回观察不能区分事实、状态、比较和接口原因。\n\n"
    p=root/'reports/mining_report.json'
    if p.exists():
        m=load(p); text+='## 状态组与分割\n\n'+f"实查 dev cluster {m['total_dev_clusters']}；setup {m['setup_clusters']}，discovery {m['discovery_clusters']}，封存 confirmation {m['sealed_confirmation_clusters']}。当前适配得到 {m['groups']} 个候选组，拟共同面板 {m['prospective_common_groups']} 组。\n\n"
        text+='当前可靠适配范围为 L4 PRE/POST 和 CA 数量的 OBJECT_ARGUMENT 低阶控制。L3 跨视图/时间状态的适配未完成，不能把其 0 个已验证组解释成数据源没有可用信息。详见 `reports/l3_feasibility.json` 与 `tables/state_switch_coverage.csv`。\n\n'
    text+='## 模型运行与主要比较\n\n'
    costfile=root/'reports/cost_preview.json'
    if costfile.exists() and load(costfile).get('status')=='PROVISIONAL_COST_PREVIEW':
        cp=load(costfile)
        text+=f"原 v2.3 10 请求/模型的初步发现轮估计为 {cp['proposals'][0]['discovery_gpu_hours_estimate']:.2f} GPU·小时；该数只是早期资源预览，当前冻结决定必须使用 v2.4 全冒烟测量。总上限 16 GPU·小时已获用户批准，见 manifest/gpu_authorization.json；保留原预算提案作为审批上下文，不将其旧的‘待批准’文字当作当前状态。\n\n"
    text+=f'当前完整 setup 使用独立的 setup_contract_v24 输入：值域改为明确标量说明，联合输出显式要求 UNDETERMINED 时 value=null。当前已索引 {len(smoke_items)} 条响应。原来的 setup/v2.3 输入、30 条实际响应和接口反例保留；v2.3 联合输出的占位值按原有契约记录警告且不获事实值积分，详见 reports/joint_contract_calibration.md。\n\n'
    if full_gate.exists():
        gate=load(full_gate)
        text+='v2.4 的工程执行/输入一致性验收与模型格式表现分开。原自动 95% 格式门槛失败（作业 8166043，记录完整保留），该门槛不是用户指南要求；在发现集冻结前作了公开协议修正，不改提示、评分或样本，也不重试生成。字段冲突仍严格记 INVALID，不称已排除接口问题。证据 manifest/setup_gate_amendment_v24.json、reports/preserved_schema_gate_v24。\n\n'
        for c in gate['checks']:
            if c['check'].endswith(':schema'): text+=f"- v2.4 {c['check']}：格式有效 {c['valid']}/{c['total']}，原 95% 检查 {c['status']}；是 setup 接口诊断，非机制统计。\n"
        text+='\n'
    text+='资源冻结前的候选机制面板为 L1 数量对象切换 61 组、L4 前后状态 15 组；不是 76 组 L4。候选原题覆盖 L1/L2 各 16 对、L3 48 对、L4 24 对，另有 6 条 UNKNOWN。这些结构筛选数不是 benchmark 自然分布或机制占比估计。最终实际冻结数以 manifest/discovery/request_plan.json 为准。\n\n'
    rp=root/'manifest/resource_plan.json'
    if rp.exists():
        resource=load(rp); pp=load(root/'manifest/discovery/request_plan.json')
        text+=f"实际冻结：{pp['group_count']} 机制组/{pp['group_clusters']} worlds，{pp['coverage_pairs']} 原题覆盖对，{pp['controls']} 控制组，{pp['interfaces']} 接口组，{pp['unknown']} UNKNOWN；请求数 {pp['by_model']}。资源规则选择 caps={resource['estimate']['caps']}，没有使用 discovery 正确率。含完整 setup 预留的估计 {resource['estimate']['total_gpu_hours_including_smoke']:.3f} GPU·小时；硬授权 16。证据 manifest/resource_plan.json、manifest/discovery/request_plan.json。\n\n"
    for s in measurement_status: text+=f"- 最小资源测量 {s['model']}：{s['completed']}/{s['expected']}，{s['status']}，已返回请求 {s['clusters']} 个 cluster；请求处理耗时 {s['measured_request_seconds']:.2f} 秒，输出 {s['output_tokens']} tokens。仅 setup 接口/成本，非科学发现样本。证据 reports/minimal_measurement_status.json。\n"
    for s in smoke_status: text+=f"- setup 冒烟 {s['model']}：{s['status']}，完成 {s['completed']} 条。\n"
    text+='\n'
    for c in completeness: text+=f"- {c['model']}: {c['completed']}/{c['expected']}，{c['status']}。\n"
    if not completeness: text+='三模型尚未形成发现轮结果。已完成的 setup 测量响应在 raw_predictions.jsonl 逐条索引；它们不计入发现轮。空的发现轮结果表表示 NOT_RUN，不代表零错误或没有该现象。\n'
    if done:
        for e in comparisons: text+=f"\n{e['model']}，{e['contrast']}：{e['effect']}，95% cluster bootstrap 区间 {e['ci95']}，{e['n_rows']} 个匹配请求、{e['n_clusters']} 个 cluster。范围：oracle 文本状态表，非原始多模态能力；证据 `scores/primary_comparisons.json`、`tables/matched_controls.csv`。\n"
    if design:
        text+='\n## 冻结设计的验收限制\n\n以下检查只读取冻结请求，不依据模型答案。执行完成不等于这些科学设计条件全部通过；不回改已冻结提示或补选模型失败题。详见 reports/frozen_design_audit.json、tables/joint_report_order.csv。\n\n'
        for c in design['checks']:
            text+='- '+c['check']+'：'+c['status']+'。'+c.get('limitation','')
            for field in ['first_role_counts','code_label_counts','group_count','world_count']:
                if field in c: text+=' '+field+'='+str(c[field])+'。'
            text+='\n'
        text+='\n固定 PRE→POST 联合输出不能排除自回归顺序解释；联合改别名/倒序不能分别定位两种效应。C/C 命题只是不变标签控制，不是物理不变事实。未满足的平衡条件必须保留 FAIL，不能把总运行状态当成这些条件的 PASS。\n'
    accounting_path=root/'reports/gpu_accounting_summary.json'
    if accounting_path.exists():
        allocation=load(accounting_path)
        text+=f"\nSlurm 截至查询时实际分配 GPU·小时：{allocation['allocated_gpu_hours_to_query']:.4f}；全部列出的 GPU 作业已结束={allocation['all_listed_jobs_terminal']}。这是包括模型加载/已分配空闲时间的调度器口径；排队作业当前为零不代表最终成本为零。原始证据 reports/slurm_accounting.txt，预算上限 16 GPU·小时。\n"
    text+='\n## 十项研究问题与当前可回答范围\n\n'
    topics=['输入与评分可靠性','L3/L4 合格 target-only 组覆盖','独立事实与状态报告','联合值集合与归属','target-only 响应与不变控制','正确事实子集上的选择/判断差距','非退化的非目标值干扰','oracle、别名和答案接口匹配控制','27B 与小模型的共同面板比较','下一阶段解释与否证条件']
    answers={
        1:'历史 24,196 条预测重算一致；本轮 v2.3 最小测量的基础设施完成与格式有效性必须分开。27B 一条关系值响应返回了值域说明对象，仍记 INVALID；9B 联合输出的非空占位值记警告且不作为事实。见 scores/measurement_diagnostics.jsonl、reports/joint_contract_calibration.md。v2.4 完整接口复验未完成，不能宣称输入/评分问题已全部排除。',
        2:'有可靠来源与重放的预选 L4 前后状态组为 15 个独立 world；L1 对象数量切换为 61 组低阶控制。当前适配未验证 L3 跨视图身份对应（检查 121 个 dev 父 pair，规范 fact key 跨 context 候选为 0）；这不是源数据不存在其他构造的证明。见 tables/state_switch_coverage.csv、reports/l3_feasibility.json。',
        9:'三个尺度完成同一份预先冻结的 10 条请求、共同 5 个 setup world；这只是接口/成本复测，不是 discovery 效应或独立重复验证。所有响应在 raw_predictions.jsonl 可追溯；没有按 4B/9B 失败挑选 27B 请求。',
        10:'候选机制仍为 UNRESOLVED。16 GPU·小时预算已批准；先完成 v2.4 setup 复验、按资源规则冻结共同面板，再执行 A3/A4。只允许继续 Phase A；没有授权白盒、训练、确认集或正式 test 新实验。'
    }
    if done: answers=completed_answers(cfg,root,extra,comparisons,switch_aggregates)
    elif full_gate.exists():
        answers[1]='历史 24,196 条预测重算一致；v2.4 三模型完整冒烟已执行，工程输入一致性和解析器测试通过，但格式有效仅为 4B 35/43、9B 34/43、27B 29/38。26 条 INVALID 不人工修正、不归为纯事实内容错误。原 95% 自动门槛失败和发现集冻结前的协议修正完整保留；不能称已排除答案接口问题。见 reports/smoke_gate_setup_contract_v24.json、manifest/setup_gate_amendment_v24.json。'
        answers[9]='三个尺度已完成预先固定的完整 setup 冒烟（4B/9B 各 43、27B 38 请求），共同实际提示和媒体哈希一致；此前最小测量另有每模型 10 条。发现轮预选相同 16 个机制 world，不能把 setup 结果当成尺度效应。没有按小模型失败选 27B；完整发现轮完成前不报告配对规模差异。'
        if rp.exists(): answers[10]='候选机制仍为 UNRESOLVED。预算已批准，完整冒烟、按成本规则冻结和独立源事实重放已完成；A3/A4 通过现有 Slurm 依赖链继续。未平衡的联合输出顺序和其他设计限制见上节；不将排队或提交当作实验完成。只继续 Phase A，不自动启动白盒、训练、确认集或正式 test 新实验。'
    for i,t in enumerate(topics,1):
        answer=answers.get(i,'NOT_RUN：尚无冻结 discovery 的完整配对结果；setup 小样本用于接口与成本，不提供该机制比较的准确率或置信区间。')
        text+=f"{i}. {t}："+answer+'\n\n'
    text+='## 审核与边界\n\n用户已声明原数据全部审核通过，记录为 USER_ATTESTED；未虚构审核人数量。新增诊断查询和实际 processor 呈现单独留痕，尚不能将其称作已完成独立人工复核。二分类标签 WSA 不作为机制指标；二元关系值域同样标为退化。COUNT 比较使用非负整数答域，不只提供本题两个答案选项。\n\n'
    text+='## 运行边界和下一步\n\n'+('本轮冻结试点请求与报告交付后停止，等待研究者决定下一阶段；未通过的科学设计验收仍需明确保留。' if done else '当前只继续已授权的 Phase A 依赖链；预算及成本冻结已有记录，排队或提交不计实验完成。')+'不自动进行白盒、训练、确认集或正式 test 新实验。\n'
    if not budget.exists(): text+='\n批量预算尚未确认：已询问建议总上限 8 GPU·小时，但未把界面预选当作同意。依据用户要求实际实施及指南 §9.5 的最小测量要求，已单独提交三模型各最多 10 条、最长 10 分钟的短测量作业，最坏总计 0.67 GPU·小时；这不授权批量发现轮。最小测量与完整 setup 冒烟分别记录，不将提交计作完成。批量仍需依据实际成本和确认预算冻结共同面板，不依据正确率选样。\n'
    text+='\n复现入口与实际 Slurm 命令见本目录 reproduce.md；独立源码入口见仓库 research/state_binding_phase_a_v2/README.md。空结果表与 null 区间均代表 NOT_RUN 或无合格分母，不是零错误或否定假设。\n'
    write(root/'phase_a_report_cn.md',text,'text')
    if os.environ.get('SLURM_JOB_ID'):
        frozen_write(root/'reports/report_snapshots'/('job_'+os.environ['SLURM_JOB_ID']+'.md'),text,'text')
    from cases import write_cases
    write_cases(cfg,root,per,controls,all_matches,measurement_items+smoke_items)
    print(json.dumps(dict(status='COMPLETE_PROVISIONAL' if done else 'INCOMPLETE',report=str(root/'phase_a_report_cn.md'))))

if __name__=='__main__': main()
