"""Record the actual chat attestation, lock reviewed membership, and report pending gates.

No prediction-based sample selection. No automatic GPU submission or budget approval.
This additive module does not change the frozen precore runner or templates.
"""
import math
import subprocess
from collections import Counter
from v3common import *


def review_plan(c, root, a):
    attestation = load(root/'review/user_chat_confirmation_20260908.json')
    if attestation['verification_basis'] != 'RESEARCHER_GLOBAL_CHAT_ATTESTATION_TRANSCRIBED_BY_CODEX':
        raise ValueError('RESEARCHER_ATTESTATION_MISSING')
    check_entries(load(root/'manifest/precore_lock.json')['code'])
    cmd = [sys.executable, str(CODE/'freeze_v3.py'), '--config', str(a.config),
           '--run-id', a.run_id, '--seed', str(a.seed), '--resume', '--dry-run']
    probe = subprocess.run(cmd, text=True, capture_output=True, check=True)
    checked = json.loads(probe.stdout)
    review = csvrows(root/'review/researcher_records.csv')
    accepted = {r['group_id']:r for r in review if r['new_review_status']=='VERIFIED_FOR_A1'}
    if set(accepted) != set(attestation['reviewer_attested_groups']):
        raise ValueError('ATTESTED_GROUPS_DO_NOT_MATCH_REVIEW')
    req = list(rows(root/'review/draft_requests.jsonl'))
    eligible = []
    eligibility = []
    for r in req:
        rr = accepted.get(r['group_id'])
        excluded = set(rr['conditions_not_eligible'].split(';')) if rr else set()
        ok = rr is not None and r['condition'] not in excluded
        eligibility.append(dict(request_id=r['request_id'], group_id=r['group_id'],
            condition=r['condition'], condition_eligible=ok,
            reason='RESEARCHER_GLOBAL_ATTESTATION' if ok else 'POST_NO_MEDIA_WITNESSES_NOT_SEPARATELY_ATTESTED' if r['condition']=='POST_NO_MEDIA' else 'WORLD_NOT_VERIFIED'))
        if ok:
            if r['models'] != c['models']: raise ValueError('MODEL_PANEL_MISMATCH')
            eligible.append(r)
    if checked['worlds']!=len(accepted) or checked['requests_per_model']!=len(eligible):
        raise ValueError('FREEZE_PROBE_AND_PLAN_DISAGREE')
    if len(eligible)!=312 or len(accepted)!=12:
        raise ValueError('UNEXPECTED_CURRENT_ATTESTATION_SCOPE')
    for gid, rr in accepted.items():
        group = [r for r in eligible if r['group_id']==gid]
        counts = Counter(r['condition'] for r in group)
        required = ({'JOINT_STATE':2, 'SELECT_MEDIA':2, 'CLAIM_MEDIA':6,
                     'CLAIM_ORACLE':6, 'ACTION_PARSE':1, 'PRE_VALUE':1, 'POST_VALUE':1,
                     'TEXT_STATE_UPDATE':1, 'ORACLE_MULTI_ORDER':2, 'SYMBOLIC_D2_MULTI':2,
                     'SYMBOLIC_D2_SHAM':2, 'ORACLE_MISSING_VALUE':2, 'CLAIM_ORACLE_MISSING':2}
                    if rr['level']=='L4' else {'OBJECT_VALUE':2, 'JOINT_OBJECT':2, 'SELECT_MEDIA_OBJECT':2})
        required.update(ORACLE_SINGLE=2, ORACLE_MULTI=2, ORACLE_SHAM=2)
        if counts != Counter(required): raise ValueError('INCOMPLETE_MATCHED_WORLD:'+gid)
    selected_ids = {r['request_id'] for r in eligible}
    matches = list(rows(root/'review/matched_controls.jsonl'))
    if any(m['base_request_id'] not in selected_ids or m['control_request_id'] not in selected_ids for m in matches):
        raise ValueError('PARTIAL_MATCH_AFTER_REVIEW')
    manifest = load(root/'review/review_bundle_manifest.json')
    plan = dict(status='REVIEWED_MEMBERSHIP_LOCKED_NOT_GPU_CORE_LOCK', run_id=c['run_id'],
        selection='REVIEW_ONLY_BEFORE_ANY_CURRENT_RUN_MODEL_RESPONSES',
        models=c['models'], requests_per_model=len(eligible), core_requests_total=len(eligible)*len(c['models']),
        verified_l4_worlds=sum(r['level']=='L4' for r in accepted.values()),
        verified_l1_worlds=sum(r['level']=='L1' for r in accepted.values()),
        verified_underlying_worlds=sorted({r['underlying_world_id'] for r in accepted.values()}),
        group_ids=sorted(accepted), request_ids=[r['request_id'] for r in eligible],
        condition_counts=dict(Counter(r['condition'] for r in eligible)),
        matches=len(matches), optional_excluded_conditions={'POST_NO_MEDIA':7},
        deferred_groups=attestation['deferred_groups'],
        review_sha256=sha(root/'review/researcher_records.csv'),
        attestation_sha256=sha(root/'review/user_chat_confirmation_20260908.json'),
        review_manifest_sha256=sha(root/'review/review_bundle_manifest.json'),
        draft_requests_sha256=manifest['request_file_sha256'],
        private_gold_sha256=manifest['private_gold_sha256'],
        final_core_lock_created=False, gpu_authorization=False)
    return plan, review, eligibility, matches, checked


def resource_measurement(c, root, plan):
    """Use only request lengths/timings, not answers or scores, to estimate cost."""
    specs = {j['model']:j for j in load(root/'resources/precore_authorization.json')['jobs']}
    gpu = load(root/'reports/gpu_engineering.json')
    result = dict(status='WAITING_PRECORE_MEASUREMENTS', approved=False,
                  run_id=c['run_id'], stage='core', models=c['models'],
                  requests_per_model=plan['requests_per_model'], automatic_retries=0,
                  submit_automatically=False, estimates=[])
    if gpu['status']!='PASS' or any(n['generated']!=82 or n['infra'] for n in gpu['per_model'].values()):
        return result
    precore = list(rows(root/'inputs/precore/requests.jsonl'))
    drafts = {r['request_id']:r for r in rows(root/'review/draft_requests.jsonl')}
    for model in c['models']:
        raw = []
        for req in precore:
            p = root/'raw/precore'/model/(req['request_id']+'.json')
            if p.is_file():
                d = load(p)
                if not d.get('infrastructure_error') and isinstance(d.get('generation_seconds'),(int,float)):
                    raw.append((req,d))
        bykind = {True:[],False:[]}
        for req,d in raw: bykind[bool(req['payload']['media'])].append(d)
        if any(not values for values in bykind.values()): return result
        load_seconds = max(load(d['environment_path'])['load_seconds'] for _,d in raw)
        estimated = load_seconds
        input_ranges = {}
        for media, observed in bykind.items():
            candidates = [drafts[i] for i in plan['request_ids'] if bool(drafts[i]['payload']['media'])==media]
            sizes = [load(root/'review/rendered'/model/(r['request_id']+'.json'))['input_tokens'] for r in candidates]
            ref_tokens = max(d['input_tokens'] for d in observed)
            observed_max_wall = max(d['wall_seconds'] for d in observed)
            # Conservative planning heuristic, not a measured core runtime or upper bound.
            subtotal = sum(observed_max_wall*max(1.0,n/ref_tokens) for n in sizes)
            estimated += subtotal
            input_ranges['media' if media else 'text'] = dict(n=len(sizes),
                core_max_input_tokens=max(sizes), precore_max_input_tokens=ref_tokens,
                observed_max_request_wall_seconds=observed_max_wall, estimated_seconds=subtotal)
        seconds = max(300, int(math.ceil(2.0*estimated/300))*300)
        if seconds>172800: raise ValueError('ESTIMATED_CORE_WALLTIME_EXCEEDS_VERIFIED_LIMIT')
        hours, rem = divmod(seconds,3600); minutes, secs = divmod(rem,60)
        wall = f'{hours:02d}:{minutes:02d}:{secs:02d}'
        spec = specs[model]
        command = (f"sbatch --parsable -p gpu -A YOUR_ACCOUNT --qos=allocated -N 1 -n 1 -c {spec['cpus']} "
                   f"--mem={spec['mem']} --gpus-per-node={spec['gpus']} -t {wall} --no-requeue "
                   f"--job-name=sca1c3_core_{model} -o '{root}/logs/core_{model}_%j.out' "
                   f"-e '{root}/logs/core_{model}_%j.err' '{CODE}/job.sh' core {model}")
        result['estimates'].append(dict(model=model, cpus=spec['cpus'], mem=spec['mem'],
            gpus=spec['gpus'], walltime=wall, allocated_gpu_hours=spec['gpus']*seconds/3600,
            observed_model_load_seconds=load_seconds, measured_precore_responses=len(raw),
            input_groups=input_ranges, estimation='2x(load + max observed per-kind wall scaled by longer input); not a guarantee for core or 512-token worst case',
            command=command))
    result.update(status='PROPOSED_FROM_PRECORE_REQUIRES_USER_BUDGET_APPROVAL',
                  max_allocated_gpu_hours=sum(r['allocated_gpu_hours'] for r in result['estimates']))
    return result


def main():
    p=arguments(__doc__); p.add_argument('--after-precore',action='store_true')
    a=p.parse_args(); c,root=setup(a)
    if a.dry_run:
        print('PLANNED: validate attested review and shared membership; no model calls or GPU submission')
        return
    compute()
    plan,review,eligibility,matches,probe = review_plan(c,root,a)
    save(root/'manifest/reviewed_core_plan.json',plan)
    save(root/'manifest/reviewed_condition_eligibility.jsonl',eligibility,'jsonl')
    save(root/'manifest/reviewed_matched_controls.jsonl',matches,'jsonl')
    acceptance = dict(status='PASS_RESEARCHER_CHAT_ATTESTATION',run_id=c['run_id'],
        verified_worlds=12, verified_l4_count_worlds=7, verified_l1_control_worlds=5,
        reviewer='anonymous', attestation_file=str(root/'review/user_chat_confirmation_20260908.json'),
        review_sha256=plan['review_sha256'], plan_sha256=sha(root/'manifest/reviewed_core_plan.json'),
        technical_scope_probe=probe, optional_post_no_media='NOT_SEPARATELY_ATTESTED_EXCLUDED',
        no_independent_agent_or_second_human_review_claimed=True)
    save(root/'reports/researcher_review_acceptance.json',acceptance)
    proposal=resource_measurement(c,root,plan)
    save(root/'resources/core_resource_proposal.json',proposal,frozen=False)
    if any((root/'raw/core').glob('*/a1c3_*.json')):
        raise ValueError('CORE_ALREADY_STARTED_USE_FULL_SCIENTIFIC_COLLECTOR')
    gpu=load(root/'reports/gpu_engineering.json')
    state='PARTIAL_WAITING_PRECORE_GPU'
    if proposal['status']=='PROPOSED_FROM_PRECORE_REQUIRES_USER_BUDGET_APPROVAL':
        state='PARTIAL_AWAITING_CORE_BUDGET_APPROVAL'
    elif a.after_precore:
        state='PARTIAL_BLOCKED_PRECORE_INCOMPLETE_OR_INFRA'
    live=load(root/'LIVE_STATUS.json')
    live.update(status=state, verified_worlds=12, verified_l4_worlds=7, verified_l1_worlds=5,
        planned_core_requests_per_model=312, planned_core_requests_total=936,
        review_status=acceptance['status'], gpu_end_to_end_status=gpu['status'],
        core_budget_approved=False, core_responses=0, updated_at_utc=now(),
        review_attestation=str(root/'review/user_chat_confirmation_20260908.json'),
        reviewed_plan=str(root/'manifest/reviewed_core_plan.json'))
    save(root/'reports'/f'review_progress_{os.environ["SLURM_JOB_ID"]}.json',live)
    save(root/'LIVE_STATUS.json',live,frozen=False)
    gates=load(root/'handoff/06_ACCEPTANCE_AND_PROTOCOL.json')
    gates.update(G1=acceptance,G2_GPU=gpu,G3=dict(status='MEMBERSHIP_LOCKED_PENDING_GPU_AND_BUDGET',
                 requests_per_model=312, shared_worlds=12, matched_comparisons=len(matches)))
    save(root/'handoff/06_ACCEPTANCE_AND_PROTOCOL.json',gates,frozen=False)
    csvsave(root/'handoff/05_DERIVED_INPUT_REVIEW.csv',review,frozen=False)
    matrix=csvrows(root/'handoff/02_A1_FAILURE_MATRIX.csv')
    byid={r['group_id']:r for r in review}
    for row in matrix: row['review_status']=byid[row['group_id']]['new_review_status']
    csvsave(root/'handoff/02_A1_FAILURE_MATRIX.csv',matrix,frozen=False)
    decision=load(root/'handoff/08_NEXT_STAGE_DECISION.json')
    decision.update(execution_status=state, verified_l4_count_worlds=7,verified_l1_control_worlds=5,
                    recommendation='REQUEST_MEASURED_CORE_BUDGET' if state=='PARTIAL_AWAITING_CORE_BUDGET_APPROVAL' else 'INSPECT_PRECORE_COMPLETION_AND_RESOURCE_MEASUREMENT')
    save(root/'handoff/08_NEXT_STAGE_DECISION.json',decision,frozen=False)
    report='# A.1 core v3 当前执行报告（真实核心尚未运行）\n\n'
    report+=f'状态：{state}。真实核心生成 0 条。人工审核已经通过，不再列为阻塞。\n\n'
    report+='用户明确确认「我看过了我觉得没问题 你进行下一步把」。记录为研究者 anonymous 的整体聊天确认，由 Codex 转录；没有伪称第二审核者、逐框点击或独立人工复核。时间是确认记录时间，不是测得的审核时长。原始话语与原审核表保存在服务器 review/user_chat_confirmation_20260908.json。\n\n'
    report+='审核通过 7 个 L4 count、5 个 L1 object world；4 个二元关系继续暂缓。POST_NO_MEDIA 的额外两补全适用性没有单独确认，7 条均 NOT_ELIGIBLE，未修改 gold；其他核心和全部匹配组保留。共同面板固定为 312 条/模型，三模型共 936 条；当前只锁定审核资格与题目集合，尚不是 GPU core 最终运行锁。\n\n'
    report+='| 模型 | 语义补测已返回/76 | 媒体 smoke 已返回/6 | 基础设施失败 |\n|---|---:|---:|---:|\n'
    for model,n in gpu['per_model'].items():
        report+=f'| {model} | {n["semantic_responses"]}/76 | {n["smoke_responses"]}/6 | {n["infra"]} |\n'
    report+='\n前置 GPU 作业为 8169708、8169709、8169710；原汇总 8169711。以 Slurm 为实时状态依据，不把已提交当完成。一次固定语义补测，不因错误/null/INVALID 重试，不以正确率放行。SELECT_MEDIA 与 ORACLE_MULTI 始终分开。\n\n'
    report+='CPU 已通过 1,203 次 processor 呈现和 39 组媒体 target-only 检查，原 6,639 个历史文件保护检查通过。这些是输入/工程检查，不是生成数或机制证据。\n\n'
    report+='GPU 工程通过后按实际媒体/文本长度、加载和逐请求时间生成资源提案；提案不是授权。上一笔 1.5 GPU·小时只覆盖前置，不自动扩展。取得覆盖真实 core 的授权并完成最终冻结后，才运行三模型共同题目。\n\n'
    report+='[审核记录](05_DERIVED_INPUT_REVIEW.csv)、[验收](06_ACCEPTANCE_AND_PROTOCOL.json)、[补测原始响应表](07_SEMANTIC_BRIDGE_RESPONSES.csv)、[逐 world 矩阵](02_A1_FAILURE_MATRIX.csv)、[匹配控制](04_MATCHED_CONTROLS.csv)、[下一步](08_NEXT_STAGE_DECISION.json)。矩阵预测栏仍为未运行，不填假准确率或 CI，也尚不能判定哪个 failure 最值得进入下一阶段。\n\n'
    report+='服务器来源：'+str(root)+'。本轮完成真实 core 后必须补齐逐请求评分、世界聚类 CI、反例和正式诊断报告；不启动白盒/训练/confirmation/test/新模型。\n'
    save(root/'handoff/01_A1_CORE_REPORT_CN.md',report,'text',frozen=False)
    source=csvrows(root/'handoff/SOURCE_INDEX.csv')
    indexed={r['path']:r for r in source}
    for path in [root/'review/user_chat_confirmation_20260908.json',root/'review/researcher_records.csv',
                 root/'manifest/reviewed_core_plan.json',root/'manifest/reviewed_matched_controls.jsonl',
                 root/'resources/core_resource_proposal.json',root/'reports/researcher_review_acceptance.json',
                 CODE/'review_gate_v3.py',CODE/'review_gate_job.sh']:
        indexed[str(path)]=entry(path)
    csvsave(root/'handoff/SOURCE_INDEX.csv',list(indexed.values()),frozen=False)
    out=root/'handoff'
    save(out/'SHA256SUMS.txt',''.join(sha(q)+'  '+q.name+'\n' for q in sorted(out.iterdir()) if q.is_file() and q.name!='SHA256SUMS.txt'),'text',frozen=False)
    print(json.dumps(live,ensure_ascii=False))


if __name__=='__main__': main()
