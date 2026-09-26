"""Interim GPT progress brief: immutable published aggregates, no new inference."""
import csv
import re
import shutil
import subprocess
import zipfile
from common_auto_v2 import *

NAME = 'SpaceConflict_SWS_Progress_Brief_20260910_v1'
MODULES = [
 ('E0','全 benchmark','主三模型完成','24,196 输入/模型；4,284 world；扩展主评分完成 10/13','部分扩展推理和解释 judge 未完成'),
 ('E1','多视图状态形成','合格子集执行完成，覆盖不完整','38 world，523 请求/模型；置换、冗余及参考证据移除','真正单视图不足而联合足够的认证 world 为 0'),
 ('E2','候选影响','已运行并评分','计数批次及 112-world 非计数扩展，neutral/true/false/sham','非计数多对象保护事实不足；不能预设污染成立'),
 ('E3','信息角色','部分完成','候选/假设干预/基态/保护事实','真实新增观察角色未补齐'),
 ('E4','TARGET/frame/time','部分完成','同一分支描述下 TARGET 切换','原生 time/frame 完整覆盖不足'),
 ('E5','更新与局部性','计数合格分支完成','新增 80 world；逆动作、两步更新；480 请求/模型','来源支持的可控数量分支，不等同原生动态 L4；非计数动作不足'),
 ('E6','fact/verdict 分离','预选条件执行完成','FACT_ONLY/VERDICT_ONLY/FACT_FIRST/VERDICT_FIRST','跨模块综合解释尚未完成，不能当内部计算先后证据'),
 ('E7','状态报告与顺序暴露','新增批次执行评分完成','88 world；新增 680 请求/模型','目标 96 world 尚差 8；新增 4B/9B 有 11/12 条规范化后不合规'),
 ('E8','L1–L4 功能定位','合格条件完成','320 level-world 锚点，313 独立 world；1,764 请求/模型','222 条条件级缺项；不是全部中间环节已可诊断'),
 ('E9','竞争解释控制','固定有界控制完成','原 768 + 新 216 = 984 请求/模型；24 符号 world','符号/非空间控制不能填补真实空间 world 配额'),
 ('M0','白盒工具等价性','有限验收完成','9B，4 请求、2 world，hook/cache 技术验收 PASS','工具可用不是内部机制成立'),
 ('M1','内部表示读出','部分完成','9B，20 world；14 train/6 validation；18 留出请求','仅 information_role；另外五个变量 PROBE_UNDERPOWERED'),
 ('M2','内部因果干预','未运行','没有可报告的 activation intervention 效应','缺完整 donor/recipient 干预清单及预定对照'),
 ('C1','新行为留出验证','未运行','资产扫描完成，不等于留出划分完成','148,708 未解析 locator；新全局留出未冻结'),
 ('C2','内部留出验证','未运行','无 MECHANISM_LOCK','真实依赖尚未满足'),
 ('FINAL','统一报告及正式证据包','尚未完成','本包仅为用户要求的阶段汇报','不是旧指南第23节的 raw-closed 最终 REVIEW 包'),
]


def main():
    a = arguments(__doc__).parse_args(); c, root = setup(a)
    if a.dry_run:
        print('Read completed aggregate CSV/acceptance only; build interim brief; no model calls.'); return
    phase = CODE.parent
    dest = root / 'progress_briefs' / NAME
    export = phase / NAME
    if dest.exists() or export.exists(): raise ValueError('NEW_NAMESPACE_ALREADY_EXISTS_PRESERVE_IT')
    dest.mkdir(parents=True)
    sources = {}; statistics = []; execution = []; metadata_warnings = []
    def ref(path):
        path = Path(path)
        if str(path) not in sources: sources[str(path)] = entry(path)
        return sources[str(path)]
    def read(path):
        ref(path); return load(path)
    def stats(path, case, model, version):
        path = Path(path); source = ref(path)
        with path.open() as f: records = list(csv.DictReader(f))
        for line, record in enumerate(records, 2):
            statistics.append(dict(brief_evidence_id=f'S{len(statistics)+1:05d}', brief_case=case,
                brief_model=model, brief_version=version, brief_source_path=str(path), brief_source_sha256=source['sha256'],
                brief_source_line=line, **record))
    index = read(root / 'rescoring/interface_v3_20260910/ACTIVE_SCORING_INDEX.json')
    snapshots = []
    for x in sorted(index['cases'], key=lambda x:(x['case'], x['model'])):
        ap = Path(x['acceptance']['path']); ac = read(ap)
        if ref(ap)['sha256'] != x['acceptance']['sha256']: raise ValueError('ACTIVE_ACCEPTANCE_HASH_CHANGED')
        snapshots.append((x['case'], x['model'], ap.parent, 'SWS_INTERFACE_V3_OLD_BATCH'))
    for batch in ('e5_sequence_supplement_v1_20260910','e7_typed_expansion_v1_20260910','e9c_controls_v1_20260910'):
        for model in c['models']:
            found = list((root/'rescoring/coverage_supplement_interface_v3'/batch/batch/model).glob('snapshot_*'))
            if len(found) != 1: raise ValueError('AMBIGUOUS_SUPPLEMENT_SNAPSHOT')
            snapshots.append((batch, model, found[0], 'SWS_INTERFACE_V3_TYPED_SUPPLEMENT'))
    for case, model, p, version in snapshots:
        ac = read(p/'RESCORE_ACCEPTANCE.json')
        if ac['status'] != 'COMPLETE' or ac['planned'] != ac['returned']: raise ValueError('INCOMPLETE_BATCH:'+case+model)
        row = dict(case=case,model=model,version=version,status=ac['status'],planned=ac['planned'],returned=ac['returned'],
                   worlds=ac['worlds'],normalized_invalid=ac['normalized_invalid'],score_job=ac['job_id'],acceptance_path=str(p/'RESCORE_ACCEPTANCE.json'))
        norm = p/'normalized'
        scoreac = norm/'SCORE_ACCEPTANCE.json'
        if scoreac.exists():
            sa = read(scoreac)
            if sa.get('worlds') is not None and sa['worlds'] != ac['worlds']:
                metadata_warnings.append(dict(case=case,model=model,field='worlds',rescore=ac['worlds'],normalized_score_acceptance=sa['worlds'],
                    interpretation='Report coverage from RESCORE_ACCEPTANCE and compiled manifest; retain older metadata discrepancy; not corrected in source.'))
        for filename in ('primary_statistics.csv','grouped_statistics.csv'):
            if (norm/filename).exists(): stats(norm/filename,case,model,version)
        if (p/'supplement_world_paired_statistics.csv').exists(): stats(p/'supplement_world_paired_statistics.csv',case,model,version)
        if (p/'SUPPLEMENT_ANALYSIS_ACCEPTANCE.json').exists(): row['analysis_status']=read(p/'SUPPLEMENT_ANALYSIS_ACCEPTANCE.json')['status']
        execution.append(row)
    if len(execution)!=36 or sum(x['returned'] for x in execution)!=28449: raise ValueError('EXPECTED_COMPLETED_BATCH_UNIVERSE_CHANGED')
    e0root=root/'e0_refresh_20260910_v3_1'
    e0=read(e0root/'acceptance.json')
    for filename in ('primary_statistics_ci.csv','primary_metrics.csv','common_model_transitions.csv'):
        stats(e0root/'tables'/filename,'E0','AS_RECORDED','E0_RETAINED_PREFIX_512_V1')
    stats(root/'whitebox/M1_role_probe_v1_20260910/world_paired_statistics.csv','M1_ROLE','qwen35_9b','M1_ROLE_ONLY')
    m0=read(root/'whitebox/M0_v1/M0_ACCEPTANCE.json')
    m1=read(root/'whitebox/M1_role_probe_v1_20260910/ACCEPTANCE.json')
    assets=read(root/'preparation/global_assets_breadth_v1_20260910/ACCEPTANCE.json')
    # Freeze policy and source-compilation acceptance, not multi-GB raw data.
    for path in [Path(__file__),CODE/'job_progress_brief_v1.sh',a.config,
                 phase/'ACTIVE_SWS_EXECUTION_POLICY_CN.md',phase/'ACTIVE_SWS_SCORING_V3_CN.md',
                 root/'preparation/coverage_supplement_v1_20260910/ACCEPTANCE.json',
                 root/'preparation/breadth_v1_20260910/ACCEPTANCE.json']:
        ref(path)
    csvsave(dest/'02_MODULE_PROGRESS.csv',[dict(module=m,name=n,status=s,completed=d,gaps=g) for m,n,s,d,g in MODULES])
    csvsave(dest/'03_ALL_AGGREGATE_STATISTICS.csv',statistics)
    csvsave(dest/'04_EXECUTION_AND_INTERFACE.csv',execution)
    e0levels=phase/'E0_results_20260910/tables/all_models_l1_l4_scores.csv'
    ref(e0levels); save(dest/'06_E0_L1_L4.csv',e0levels.read_text(),'text')
    e0report=phase/'E0_results_20260910/E0_Full_Benchmark_Results_v2_CN.md'
    ref(e0report)
    save(dest/'05_E0_FULL_RESULTS_CN.md',e0report.read_text().replace('(tables/all_models_l1_l4_scores.csv)','(06_E0_L1_L4.csv)'),'text')
    report=make_report(statistics,execution,e0,metadata_warnings)
    save(dest/'01_REPORT_CN.md',report,'text')
    save(dest/'00_START_HERE_CN.md',START,'text')
    command=['sacct','-X','-j',','.join(sorted({str(x['score_job']) for x in execution}|{'8197104','8196562','8179069'})),
             '--format=JobID,JobName%40,State,Elapsed,ExitCode','-P']
    proc=subprocess.run(command,text=True,capture_output=True,timeout=30)
    provenance=dict(package_type='INTERIM_PROGRESS_BRIEF_NOT_SECTION23_FINAL_REVIEW',created_at=now(),job_id=os.environ['SLURM_JOB_ID'],
        source_refs=list(sources.values()),E0_snapshot=e0,M0=m0,M1=m1,global_asset_audit=assets,
        metadata_discrepancies=metadata_warnings,slurm_query=dict(command=command,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr),
        supplied='ALL_ROWS_FROM_ENUMERATED_AGGREGATE_TABLES_NOT_SELECTED_SIGNIFICANT_RESULTS',
        not_supplied=['raw model responses','images/videos','activation tensors','all per-world diagnosis matrices','scorer source code'],
        raw_closure=False,new_model_calls=0,source_scores_modified=False,
        review_status='HUMAN_REVIEW_WAIVED_BY_RESEARCHER',scientific_grade='AUTO_ONLY_PROVISIONAL')
    save(dest/'07_PROVENANCE_AND_LIMITS.json',provenance)
    for source in sources.values():
        if sha(source['path'])!=source['sha256']: raise ValueError('SOURCE_CHANGED_DURING_PACKAGING')
    ids={x['brief_evidence_id'] for x in statistics}
    mentioned=set(re.findall(r'\bS\d{5}\b',report))
    if not mentioned<=ids: raise ValueError('AGGREGATE_REFERENCE_NOT_CLOSED')
    save(dest/'PACKAGE_ACCEPTANCE.json',dict(status='PASS_INTERIM_BRIEF',source_files_checked=len(sources),aggregate_rows=len(statistics),
        execution_cells=len(execution),returned_sws_responses=sum(x['returned'] for x in execution),
        named_statistic_references=len(mentioned),aggregate_reference_closure=True,raw_reference_closure=False,
        section23_final_package=False,source_hashes_unchanged=True,metadata_discrepancies=metadata_warnings,new_model_calls=0))
    files=sorted(p for p in dest.iterdir() if p.is_file())
    save(dest/'SHA256SUMS.txt',''.join(f'{sha(p)}  {p.name}\n' for p in files),'text')
    archive=dest.parent/(NAME+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(dest.iterdir()): z.write(p,p.name)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None: raise ValueError('ZIP_CRC_FAILED')
        for p in files:
            if hashlib.sha256(z.read(p.name)).hexdigest()!=sha(p): raise ValueError('ZIP_CONTENT_MISMATCH')
    shutil.copytree(dest,export)
    localzip=phase/(NAME+'.zip')
    if localzip.exists():raise ValueError('EXISTING_LOCAL_ZIP_PRESERVED')
    shutil.copyfile(archive,localzip)
    if sha(localzip)!=sha(archive):raise ValueError('EXPORT_HASH_MISMATCH')
    for p in dest.iterdir():
        if p.is_file() and sha(p)!=sha(export/p.name):raise ValueError('EXPORTED_FILE_MISMATCH')
    print(json.dumps(dict(status='PASS_INTERIM_BRIEF_ZIP_VERIFIED',archive=str(localzip),bytes=localzip.stat().st_size,
                         report=str(export/'01_REPORT_CN.md'),aggregate_rows=len(statistics),sources=len(sources))),flush=True)


def make_report(stats,execution,e0,warnings):
    def pct(x):return 'N/A' if x in ('',None) else f'{100*float(x):.2f}%'
    def ci(r):return f"{pct(r.get('estimate'))} [{pct(r.get('ci95_low'))}, {pct(r.get('ci95_high'))}]"
    def evidence(r):return r['brief_evidence_id']
    text=['# SpaceConflict：旧版 SWS 框架阶段汇报', '',f'汇总时间：{now()}。本轮仅整理已有结果，不新跑模型。', '',
          '## 1. 项目与当前结论', '',
          'SpaceConflict 是 L1–L4 空间矛盾 benchmark；本轮按旧 SWS v1 框架研究事实形成、候选陈述影响、信息角色、状态索引、更新局部性和答案接口。目标是区分竞争解释，不预设 Wrong-State Selection、污染或内部状态改写必须存在。主分析为 Qwen3.5-9B，4B/27B 使用预先冻结的共同请求作对照。', '',
          '**目前有完整 E0 主结果和大量已评分探索性行为数据，但没有完整的内部因果与新留出证据链。** 执行完成、测量有效、科学主张成立是三个不同状态。M2/C1/C2 未运行，最终第23节证据包未完成。', '',
          '## 2. 按旧指南逐模块的进度', '', '| 模块 | 状态 | 已完成范围 | 尚缺/解释限制 |','|---|---|---|---|']
    text += [f'| {m} {n} | {s} | {d} | {g} |' for m,n,s,d,g in MODULES]
    text += ['',f"原 27 个批次×模型单元 24,321 响应，加新增 E5/E7/E9c 的 4,128 响应，合计 **28,449 条已评分 SWS 响应**（不含 E0、setup、M0/M1）。36 个单元均 planned=returned。不同条件/批次不可合成一个总准确率；world 有重叠，不相加。详见 04_EXECUTION_AND_INTERFACE.csv。",'',
             '主研究面板目前为 200 个 discovery world：80 COUNT、80 NONCOUNT_RELATION、40 VIEW_FRAME_IDENTITY，原生 TIME_BRANCH 仍缺。不是完整 480-world 规划已完成；E8 的 313 world 是另一诊断抽样集合，不能直接相加补配额。', '',
             '## 3. E0 主成绩与跨模型比较', '',
             '每模型 24,196 条输入，共同 4,284 world。全量 all-split 是描述性全覆盖；已有 test-only 独立列出，不能拿全量总分当独立测试分数。原输出预算 512 tokens，保留前缀评分，截断本身不自动无效。', '',
             '| 模型 | 全量 ClaimAcc [95% CI] | 已有 test-only ClaimAcc [95% CI] |', '|---|---|---|']
    for m in ('qwen35_4b','qwen35_9b','qwen35_27b'):
        def find(dim,s):return next(r for r in stats if r['brief_case']=='E0' and r.get('model_id')==m and r.get('metric')=='ClaimAcc' and r.get('dimension')==dim and r.get('stratum')==s)
        full,test=find('OVERALL','ALL'),find('SOURCE_SPLIT','test')
        text.append(f'| {m} | {ci(full)} ({evidence(full)}) | {ci(test)} ({evidence(test)}) |')
    text += ['', 'test-only N=5,608；27B 并非所有分项均优于 9B。扩展模型 10 个完成主评测、8 个完成辅助 judge；所有 L1–L4 分层主分和已有解释分见 05/06。E0 使用 label/confidence/reason 原解析器，不能混用 SWS value/facts v3。', '',
             '## 4. 行为结果：固定端点全集，不筛显著项', '',
             '以下表格只作探索性描述。95% CI 沿用各源表的 5,000 次 world 聚类 bootstrap；不在本包重新估计、不因结果改提示。所有模型、全部聚合端点和零/负效应保存在 03_ALL_AGGREGATE_STATISTICS.csv。S 编号是该文件中的唯一证据行 ID，可追到源路径、hash、行号；不是原始响应 ID。', '',
             '### 4.1 9B：错误候选相对匹配 sham 的额外正→错变化', '',
             '完整列出各批次、来源 family 和措辞下的 WORLD_MACRO_CORRECT_TO_WRONG_EXCESS。正值表示错误候选比 sham 造成更多正→错变化；这不是总错误率，也不自动证明内部污染。批次/family 分母不同，不直接合并。', '',
             '| 批次 | family / wording | worlds / matched blocks | 差值 [95% CI] | 证据 |','|---|---|---:|---|---|']
    for r in stats:
        if r['brief_model']=='qwen35_9b' and r.get('metric')=='WORLD_MACRO_CORRECT_TO_WRONG_EXCESS':
            text.append(f"| {r['brief_case']} / {r.get('experiment')} | {r.get('sample_family')} / {r.get('wording')} / {r.get('condition')} | {r.get('worlds')} / {r.get('matched_blocks')} | {ci(r)} | {evidence(r)} |")
    text += ['', '差值列单位为百分点（例如 5% 表示 +5 pp），不是相对百分比。CI 包含 0 时不能当作稳定的非零效应；二元关系退化问题仍存在。', '',
             '### 4.2 E5：逆动作/两步更新后的 target、base、保护事实同时正确', '',
             '来源支持的可控数量分支；discovery，各条件 80 world/80 匹配组，每组 3 条查询。报告三事实联合准确率，不把单独 POST 对当更新成功。', '',
             '| 模型 | 条件 | 联合准确率 [95% CI] | 证据 |', '|---|---|---|---|']
    for r in stats:
        if r['brief_case'].startswith('e5_sequence') and r.get('group'):
            group=json.loads(r['group']);text.append(f"| {r['brief_model']} | {group[1]} | {ci(r)} | {evidence(r)} |")
    text += ['', '9B 逆动作联合准确率 20%（CI 11.25–28.75%），两步为 5%（CI 1.25–10%）。这说明此接口下联合任务困难，但当前还不能把错误唯一归因于状态更新：PRE 提取、动作理解、保护事实保持和输出接口仍需对齐分析。', '',
             '### 4.3 E7：显式自生成报告/顺序暴露的配对差异', '',
             '新 typed expansion 单独分析，不与旧提示批次混算。COUNT 80 world，NONCOUNT_RELATION 8 world。NEUTRAL_PARENT_MINUS_EXPOSED_PARENT 比较先生成 neutral 自报告与先受候选暴露；OWN_FEEDBACK_MINUS_READONLY 比较是否回填自生成状态；READONLY_MINUS_ONESHOT 比较只读序列与一次性重算。仅是外显报告/上下文行为，不证明过去视觉 token 被改写。', '',
             '| 模型 | family / 配对条件 | worlds | 差值 [95% CI] | 证据 |','|---|---|---:|---|---|']
    for r in stats:
        if r['brief_case'].startswith('e7_typed') and r.get('metric')=='PAIRED_JOINT_ACCURACY_DIFFERENCE':
            text.append(f"| {r['brief_model']} | {r.get('family')} / {r.get('condition')} | {r.get('worlds')} | {ci(r)} | {evidence(r)} |")
    text += ['', '9B COUNT 的 neutral-parent 与 exposed-parent 差值为 0，CI −6.25～6.25 pp，不能支持稳定的方向性效应。自反馈与只读序列差值为 +15 pp，CI +6.25～23.75 pp，但这不是内部机制因果证明。所有相反/零效应也在上表保留。', '',
             '### 4.4 E8/E9 与 M1：现有结果能说明什么', '',
             'E8 三模型所有原生 L1–L4 合格诊断端点在 03 中（brief_case=E8）；同一 Level 仍按 source family/condition 分开。尚缺真值的条件不补 gold，不把 oracle 差值加成 100% 的故障占比。E9 原有符号控制和新增长度/标签控制也完整收录，不能据此称“空间特有”。', '',
             'M1 仅 information_role：9B，20 world，14 train/6 held-out world，18 validation 请求。首/中/末层固定位置及全部随机标签、文本、候选、位置/长度基线共 79 行收录在 03（brief_case=M1_ROLE）。隐藏表示在 answer_start 的角色读出可达 100%，文本词袋也为 100%；这是显式角色可读性，不是空间真值被正确表示或被实际利用。其他五个变量仍 PROBE_UNDERPOWERED。', '',
             '## 5. 测量问题与未完成项目', '',
             '- 旧批次 v3 重评分后不合规从 100 降到 10；这些剩余记录含负计数。新增 E7 还有 4B 11、9B 12、27B 0 条规范化后不合规。均保留，不强改为正确值；不能将运行成功等同于每条测量均有效。',
             '- Qwen3-VL-2B-Thinking 在 E0 512-token 契约下有大量未给出可评分标签的回答，其低分是端到端结果，不能当纯空间能力。详见 05。',
             '- 真正需要多视图的 pixel-complete 认证目前为 0；原生 TIME_BRANCH 和真实新增观察未补齐。',
             '- 全局已登记资产核对完成：37,945 个已解析文件，148,708 个 locator 未解析；global_holdout_frozen=false。不能将它解释为当前运行的输入缺图。',
             '- E7 部分旧 normalized/SCORE_ACCEPTANCE 的 worlds 字段仍为 20，与补充编译及 RESCORE_ACCEPTANCE 的 88 不一致。包内覆盖数采用后者及统计表的 80+8，并保留差异清单，不就地修改旧记录。',
             '- E9c 有零宽 CI；这是当前 world/模板重复结构下的原统计，不应解读成无不确定性。需在下一轮方法核对中检查有效独立性，不能据此作强结论。',
             '- M2 无结果；C1/C2 未运行。人工审核门槛已由研究者移除，记录为 HUMAN_REVIEW_WAIVED_BY_RESEARCHER / AUTO_ONLY_PROVISIONAL，不能伪装人工 VERIFIED。', '',
             '## 6. 请 ChatGPT 协助判断', '',
             '1. 根据全部正、负、零效应，哪些结论目前只能称行为现象，哪些竞争解释仍不能区分？',
             '2. 优先核对 E5 联合保持、E7 提示/上下文效应还是 E2 false–sham 差异？请引用证据行，不因“像某个故事”而选方向。',
             '3. 要进入 M2，哪些 donor/recipient 配对、保护事实与负对照必须先准备？哪些缺口属于测量不足而非模型没有该机制？',
             '4. C1 的数据去重/未暴露资格怎样闭合？哪些领域覆盖缺口会限制论文主张？',
             '5. 建议下一阶段最小必要工作，但不要建议按小模型失败选 27B、根据 test 调提示、改 gold、选择性报告或重新跑全部 benchmark。', '',
             '本包不是最终证据闭合包，未含逐 world 全矩阵、原始响应、实际媒体与 activation。收到者不能仅凭本包进行像素真实性、parser 或内部因果复核；需要时按 07 的路径索取对应证据。', '']
    role_refs=[r['brief_evidence_id'] for r in stats if r['brief_case']=='M1_ROLE' and
               (r.get('analysis')=='TEXT_BAG_OF_WORDS' or (r.get('analysis')=='HIDDEN_ROLE_PROBE' and r.get('position')=='answer_start'))]
    text += ['M1 上述固定三层 answer_start 及文本基线对应聚合证据：'+', '.join(role_refs)+'。', '']
    return '\n'.join(text)


START = '''# 给 ChatGPT 的阶段汇报包

请先阅读 [01_REPORT_CN.md](01_REPORT_CN.md)，再按需要核对 [03_ALL_AGGREGATE_STATISTICS.csv](03_ALL_AGGREGATE_STATISTICS.csv)。

这是旧版 SpaceConflict SWS v1 研究的阶段汇报，不是最终研究完成报告。目标是区分事实提取、角色理解、状态更新/绑定、claim 比较和答案接口，不预设 Wrong-State Selection 或内部污染必然存在。

## 文件用途

- 01_REPORT_CN.md：项目背景、旧框架完成情况、带 CI 的代表端点全集、反例与下一阶段问题。
- 02_MODULE_PROGRESS.csv：E0–E9、M0–M2、C1/C2 逐模块状态。
- 03_ALL_AGGREGATE_STATISTICS.csv：所有选定批次的完整聚合统计，含零/负效应与所有模型。brief_case/brief_version 不同的行不能直接合并；brief_evidence_id 唯一。
- 04_EXECUTION_AND_INTERFACE.csv：36 个完成的 SWS 批次×模型单元、分母及不合规数。
- 05_E0_FULL_RESULTS_CN.md / 06_E0_L1_L4.csv：全 benchmark 及所有完整模型的四级结果。全量与已有 test-only 分开。
- 07_PROVENANCE_AND_LIMITS.json：源文件路径/hash、验收、队列快照、已知 metadata 差异和省略材料。
- PACKAGE_ACCEPTANCE.json / SHA256SUMS.txt：本汇报包的统计引用与文件验收。

## 必须保留的边界

本包为 INTERIM_PROGRESS_BRIEF，不是旧指南第23节最终 REVIEW ZIP。为便于汇报，不包含大体积原始响应、图片/视频、activation 或全部逐 world 诊断。聚合统计有源路径/hash，但这不等于原始证据在包内闭合。

未完成 M2/C1/C2；没有可宣称的内部因果机制结论。E0 与 SWS 输出 schema/评分器不同；非 count、可控 count、符号 world 和真正多视图证据必须区分。E7 老批次与新 typed 提示分表，不按结果混池。CI 大多是探索性 world bootstrap，不是确认检验。

请给出：当前最稳妥的结论、最重要反例、还未排除的解释和优先级明确的下一步。引用 S 开头的聚合证据行；若需要媒体/raw 才能判断，请明确说明，不能补猜。
'''


if __name__ == '__main__': main()
