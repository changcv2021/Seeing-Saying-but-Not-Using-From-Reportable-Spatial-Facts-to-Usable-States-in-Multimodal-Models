"""Honest pre-core handoff and semantic/smoke collection; never invent mechanism measurements."""
from collections import Counter
from v3common import *
from score_v3 import score


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('PLANNED: collect actual precore outputs; pending core stays NOT_RUN'); return
    compute()
    if any((root/'raw/core').glob('*/*.json')):
        raise ValueError('CORE_RESPONSES_PRESENT_REQUIRES_FULL_SCIENTIFIC_ANALYSIS_NOT_PENDING_REPORT')
    out=root/'handoff'; requests=list(rows(root/'inputs/precore/requests.jsonl'))
    gold={g['request_id']:g for g in rows(root/'private_gold/precore.jsonl')}
    records=[]; smoke=[]; expected=[]
    for model in c['models']:
        for r in requests:
            path=root/'raw/precore'/model/(r['request_id']+'.json')
            raw=load(path) if path.is_file() else None
            rendered=load(root/'review/rendered'/model/(r['request_id']+'.json'))
            score_result=score(raw,gold[r['request_id']])
            row=dict(model=model,request_id=r['request_id'],parent_request_id=r['parent_request_id'],
                     group_id=r['group_id'],underlying_world_id=r['underlying_world_id'],
                     stage=r['stage'],condition=r['condition'],naming=r['variant'],target=r['target'],
                     actual_rendered_prompt=rendered['rendered_prompt'],gold=gold[r['request_id']],
                     raw_response=raw.get('raw_response') if raw else None,score=score_result,
                     execution_status='INFRA_FAILURE' if raw and raw.get('infrastructure_error') else 'SCORED' if raw else 'NOT_RUN',
                     raw_path=str(path) if raw else None,raw_sha256=sha(path) if raw else None,raw_record=raw)
            if r['stage']=='semantic_bridge': records.append(row)
            else: smoke.append(row)
            expected.append(row)
    csvsave(out/'07_SEMANTIC_BRIDGE_RESPONSES.csv',records,frozen=False)
    csvsave(out/'smoke_responses.csv',smoke,frozen=False)
    counts={m:dict(planned=82,generated=sum(r['raw_record'] is not None and not r['raw_record'].get('infrastructure_error') for r in expected if r['model']==m),
                   infra=sum(r['execution_status']=='INFRA_FAILURE' for r in expected if r['model']==m),
                   semantic_responses=sum(r['execution_status']=='SCORED' for r in records if r['model']==m),
                   smoke_responses=sum(r['execution_status']=='SCORED' for r in smoke if r['model']==m)) for m in c['models']}
    gpu_pass=all(counts[m]['smoke_responses']==6 for m in c['models'])
    save(root/'reports/gpu_engineering.json',dict(status='PASS' if gpu_pass else 'NOT_RUN_OR_INCOMPLETE',per_model=counts,
         criterion='SIX_FIXED_MEDIA_SMOKE_REQUESTS_PER_MODEL_WITHOUT_INFRA_ERROR; correctness/individual INVALID not gate',
         parser_statuses=dict(Counter(r['score']['status'] for r in smoke)),scientific_core_responses=0),frozen=False)
    review=csvrows(root/'review/researcher_records.csv')
    csvsave(out/'05_DERIVED_INPUT_REVIEW.csv',review,frozen=False)
    cards=list(rows(root/'review/candidate_panel.jsonl')); byid={r['group_id']:r for r in review}
    with (Path(c['package'])/'templates/a1_failure_matrix_HEADER_ONLY.csv').open(encoding='utf-8-sig',newline='') as f:
        fields=next(csv.reader(f))
    matrix=[]
    for model in c['models']:
        for card in cards:
            r={field:None for field in fields}
            r.update(model=model,group_id=card['group_id'],underlying_world_id=card['underlying_world_id'],
                     source_world_aliases_json=[card['world_id'],card['cluster_id']],level=card['level'],source=card['source'],
                     stratum=card['stratum'],review_status=byid[card['group_id']]['new_review_status'],
                     category=card.get('category'),count_scope=card.get('count_scope'),
                     failure_candidate_tags_json=['NOT_RUN_NO_MECHANISM_ATTRIBUTION'],
                     competing_explanations_json=['PRE','ACTION','UPDATE','SELECTION','COMPARISON','INTERFACE'],
                     notes='All prediction/correctness fields remain empty: real A.1 core NOT_RUN. L1 has no PRE/POST gold.')
            if card['stratum']=='L4_COUNT_PRIMARY':
                r.update(pre_gold=card['values']['PRE'],post_gold=card['values']['POST'],neither_claim_value=max(card['values'].values())+1)
            matrix.append(r)
    csvsave(out/'02_A1_FAILURE_MATRIX.csv',matrix,fields,frozen=False)
    csvsave(out/'03_CORE_RESPONSES_WITH_PROMPTS.csv',[],['model','request_id','group_id','underlying_world_id','condition','actual_rendered_prompt','raw_response','score','execution_status'],frozen=False)
    matches=list(rows(root/'review/matched_controls.jsonl'))
    controls=[dict(model=m,**r,base_status='NOT_RUN',control_status='NOT_RUN',rescue=None,harm=None,net=None) for m in c['models'] for r in matches]
    csvsave(out/'04_MATCHED_CONTROLS.csv',controls,frozen=False)
    verified=[r for r in review if r['new_review_status']=='VERIFIED_FOR_A1']
    auth=root/'resources/precore_authorization.json'
    gates=dict(G0=load(root/'reports/history_protection.json'),G1=dict(status='BLOCKED_REVIEW',recorded_verified=len(verified)),
               G2_CPU=load(root/'reports/processor_checks.json'),G2_GPU=load(root/'reports/gpu_engineering.json'),
               G3=dict(status='NOT_FROZEN_PENDING_REVIEW_AND_RESOURCE_MEASUREMENT'),G4=dict(status='NOT_RUN',core_generated=0),
               GPU_AUTHORIZATION=load(auth) if auth.is_file() else dict(approved=False,status='AWAITING_CURRENT_RUN_BUDGET_CONFIRMATION'))
    save(out/'06_ACCEPTANCE_AND_PROTOCOL.json',gates,frozen=False)
    decision=dict(stage='PHASE_A1_CORE_V3',execution_status='PARTIAL_BLOCKED_REVIEW',
                  scientific_status='MIXED_OR_UNRESOLVED',generated_core_responses=0,
                  verified_l4_count_worlds=sum(r['stratum']=='L4_COUNT_PRIMARY' for r in verified),
                  verified_l1_control_worlds=sum(r['stratum']=='L1_OBJECT_ARGUMENT_CONTROL' for r in verified),
                  primary_model='qwen35_9b',candidate_routes=[],remaining_competing_explanations=['PRE','ACTION','POST_UPDATE','MEDIA_SELECTION','EXPLICIT_SELECTION','COMPARISON','INTERFACE'],
                  evidence_request_ids=[],counterexample_request_ids=[],recommendation='WAIT_FOR_RESEARCHER_REVIEW',
                  mechanism_proven=False,auto_execute_phase_b=False)
    save(out/'08_NEXT_STAGE_DECISION.json',decision,frozen=False)
    summary=[]
    for m in c['models']:
        for cond in ['TARGET_PRESENT','TARGET_MISSING','NULL_COPY','MISSING_TARGET_VERDICT']:
            rr=[r for r in records if r['model']==m and r['condition']==cond]
            got=[r for r in rr if r['execution_status']=='SCORED']
            summary.append(dict(model=m,condition=cond,planned=len(rr),responses=len(got),not_run=sum(r['execution_status']=='NOT_RUN' for r in rr),
                                correct=sum(r['score']['correct'] is True for r in got) if got else None,
                                null=sum(r['score']['status']=='NULL' for r in got),invalid=sum(r['score']['status']=='INVALID' for r in got),
                                status='DESCRIPTIVE_FIXED_ONE_PASS_NOT_MECHANISM_EVIDENCE'))
    csvsave(out/'semantic_bridge_summary.csv',summary,frozen=False)
    sourcefiles=[root/'current_state_inventory.json',root/'protocol_amendments.json',root/'manifest/precore_lock.json',
                 root/'review/review_bundle_manifest.json',root/'review/researcher_records.csv',root/'manifest/build_inventory.json']
    csvsave(out/'SOURCE_INDEX.csv',[entry(p) for p in sourcefiles],frozen=False)
    report='# A.1 core v3 当前执行报告（未完成真实核心）\n\n'
    report+='状态：PARTIAL_BLOCKED_REVIEW。真实核心响应 0；下面是已实施的前置工作，不是机制实验完成。\n\n'
    report+='已完成：新命名空间、历史保护、319 条真实核心输入草案/模型、固定 76 条语义补测与 6 条独立 setup 媒体 smoke/模型；共享纯视觉 hash 与 CPU/解析器测试、实际 processor 呈现及人工审核页面。\n\n'
    report+='SELECT_MEDIA 与 ORACLE_MULTI 分开。完整/缺失值均 nullable；别名 query_value→value 保留。二元关系 4 world 暂缓；7 个 L4 count 与 5 个 L1 控制等待实际研究者审核。POST_NO_MEDIA 的两种补全另须研究者确认，否则排除此条件；不猜无图 gold。\n\n'
    report+='| 模型 | 语义补测已返回/76 | 媒体 smoke 已返回/6 | 基础设施失败 |\n|---|---:|---:|---:|\n'
    for m,n in counts.items(): report+=f'| {m} | {n["semantic_responses"]}/76 | {n["smoke_responses"]}/6 | {n["infra"]} |\n'
    report+='\n合成语义分数不作放行条件；每个请求只执行一次正常生成，不按错误或 null 重试。全部响应、未运行与基础设施失败见 [补测逐样本表](07_SEMANTIC_BRIDGE_RESPONSES.csv) 和 [smoke 表](smoke_responses.csv)。\n\n'
    report+='[诊断矩阵](02_A1_FAILURE_MATRIX.csv) 当前是明确 NOT_RUN 的候选占位表，预测/正确性为空；[匹配控制](04_MATCHED_CONTROLS.csv) 同样没有虚构效果。没有真实样本测量，因此不提供假的 core 准确率或 CI，下一阶段候选均 UNRESOLVED。\n\n'
    report+='研究者入口（仅服务器路径）：'+str(root/'review/index.html')+'\n\n填写并保存 '+str(root/'review/researcher_records.csv')+'；不得把代理判断当人工审核。GPU 前置预算未批准时不提交；真实 core 预算必须在 smoke 测量后另行冻结。本轮没有重跑旧 Phase A/旧 setup，也未进入白盒、训练、confirmation 或 test。\n\n'
    report+='CPU 呈现检查 PASS 不等于 GPU 端到端已 PASS，具体状态见 [验收](06_ACCEPTANCE_AND_PROTOCOL.json)。完成审核后还需冻结合格共同面板、资源和匹配关系，然后运行真实核心并补齐正式统计与报告；当前不能宣称任务完成。\n'
    save(out/'01_A1_CORE_REPORT_CN.md',report,'text',frozen=False)
    save(out/'00_README_CN.md','# A.1 core v3 前置交接\n\n先读 [当前报告](01_A1_CORE_REPORT_CN.md)。这是未完成真实核心的真实状态快照。\n\n仅服务器审核页面：'+str(root/'review/index.html')+'\n\n包内矩阵的 NOT_RUN 不是错误，渲染数不是预测数。所有主要文件见报告链接。源码与实际命令见服务器代码目录 '+str(CODE)+'。\n','text',frozen=False)
    files=sorted(p for p in out.iterdir() if p.is_file() and p.name!='SHA256SUMS.txt')
    save(out/'SHA256SUMS.txt',''.join(sha(p)+'  '+p.name+'\n' for p in files),'text',frozen=False)
    checked=check_entries(list(rows(root/'manifest/history_before.jsonl')))
    save(root/'reports/post_prepare_history_check.json',dict(status='PASS',files_checked=checked,changed_files=[]),frozen=False)
    save(root/'LIVE_STATUS.json',dict(status='PARTIAL_BLOCKED_REVIEW',core_responses=0,precore=counts,verified_worlds=len(verified),
         processor_status='PASS',gpu_end_to_end_status='PASS' if gpu_pass else 'NOT_RUN_OR_INCOMPLETE',
         gpu_precore_authorized=auth.is_file() and load(auth).get('approved',False),
         review_page=str(root/'review/index.html'),handoff_report=str(out/'01_A1_CORE_REPORT_CN.md')),frozen=False)
    print(json.dumps(load(root/'LIVE_STATUS.json')))


if __name__=='__main__': main()
