"""Read-only evidence export; no inference, gold editing, or primary metric replacement."""
from collections import Counter, defaultdict
import gzip
import shutil
import zipfile
from bc_common import *

MODELS = ['qwen35_4b', 'qwen35_9b', 'qwen35_27b']
BATCH_NAMES = ['e5_measurement_v1', 'native_e8_measurement_v1', 'c1_count_v1']
H1 = {'false_wrong', 'sham_wrong', 'false_minus_sham', 'candidate_attraction'}

def unpack(row):
    ans = {}
    for k, v in row.items():
        if isinstance(v, str) and v.startswith(('{', '[')):
            try: v = json.loads(v)
            except ValueError: pass
        ans[k] = v
    return ans

def percent(v):
    return 'N/A' if v in (None, '') else f'{100 * float(v):.2f}%'

def interval(r):
    if r.get('estimate') in (None, ''): return 'N/A（条件分母为 0）'
    lo, hi = r.get('ci95_low'), r.get('ci95_high')
    ci = '' if lo in (None, '') else f' [{percent(lo)}, {percent(hi)}]'
    mark = '†' if lo not in (None, '') and float(lo) == float(hi) else ''
    return percent(r['estimate']) + ci + mark

def table(headers, data):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(str(x).replace('|', '/') for x in r) + ' |' for r in data])

def main():
    args = cli(__doc__).parse_args()
    config, sws, root = context(args)
    if args.dry_run: print('Read-only frozen evidence export; no model calls.'); return
    import numpy as np
    dest = root / 'report_exports/gpt_results_20260910_v1'
    if dest.exists(): raise RuntimeError('NEW_EXPORT_ALREADY_EXISTS: protect existing export')
    dest.mkdir(parents=True)
    sources = {}
    def src(path):
        path = Path(path); ref = entry(path); sources[str(path)] = ref; return path
    def csvread(path): return csvrows(src(path))
    def jsonread(path): return load(src(path))
    stats, diagnostic, prompts, responses, acceptance, endpoint_index = [], [], [], [], [], {}
    def endpoint_refs(x):
        if isinstance(x, dict):
            if x.get('raw_path'):
                endpoint_index[(x['raw_path'], x.get('raw_sha256'))] = {k: x.get(k) for k in ('request_id', 'raw_path', 'raw_sha256')}
            for v in x.values(): endpoint_refs(v)
        elif isinstance(x, list):
            for v in x: endpoint_refs(v)
    def add_diag(path, tag):
        rr = [unpack(r) for r in csvread(path)]
        for r in rr:
            endpoint_refs(r.get('endpoints', {}))
            diagnostic.append(dict(export_module=tag, source_matrix=str(path), **r))
        return rr
    original = csvread(root / 'P8/primary_statistics.csv')
    for r in original:
        if r['module'] in ('E2', 'E8'):
            stats.append(dict(scope='ORIGINAL_DISCOVERY', **r))
    e2 = add_diag(root / 'P1_E2/matrix.csv', 'E2_DISCOVERY')
    e8 = add_diag(root / 'P3_E8/matrix.csv', 'E8_EXISTING')
    overlay = csvread(root / 'quality_audit_v1/e8_missing_panel_overlay.csv')
    csvsave(dest / '08_E8_UNCOMPILED_ANCHORS.csv', overlay)
    new_matrices = {}
    for b in BATCH_NAMES:
        base = root / 'batches' / b
        reqs = list(rows(src(base / 'public_inputs/requests.jsonl')))
        lock = jsonread(base / 'manifest/REQUEST_LOCK.json')
        prompts += [dict(batch=b, **r) for r in reqs]
        byid = {r['request_id']: r for r in reqs}
        assert len(byid) == len(reqs)
        assert all(set(r['models']) == set(MODELS) for r in reqs)
        assert all(r['requested_tokens'] == 512 for r in reqs)
        for m in MODELS:
            score_dirs = list((base / 'scores' / m).glob('snapshot_*'))
            assert len(score_dirs) == 1, score_dirs
            folder = score_dirs[0]
            ac = jsonread(folder / 'SCORE_ACCEPTANCE.json')
            assert ac['status'] == 'COMPLETE' and ac['not_run'] == 0 and ac['invalid'] == 0
            for k in ('normalization', 'scores', 'raw_index'):
                check(ac[k]); src(ac[k]['path'])
            views = list(rows(ac['normalization']['path']))
            sc = {r['request_id']: unpack(r) for r in csvread(ac['scores']['path'])}
            assert len(sc) == len(views) == len(reqs) and set(sc) == set(byid)
            counts = Counter()
            for v in views:
                r = sc[v['request_id']]; n = v['normalization']; components = n['normalized']['component_values']
                counts['strict_invalid'] += n['strict']['status'] != 'VALID'
                counts['normalized_invalid'] += n['normalized']['status'] != 'VALID'
                counts['changed'] += bool(n['changed'])
                counts['null_response'] += any(x is None for x in components.values())
                counts['truncated'] += bool(v['truncated'])
                counts['correct'] += r['content_correct'] == 'True'
                responses.append(dict(batch=b, model=m, request_id=v['request_id'], world_cluster_id=v['world_cluster_id'],
                    condition=byid[v['request_id']]['condition'], raw_response=v['raw_response'], normalized=components,
                    expected=r['expected'], content_correct=r['content_correct'], strict_status=n['strict']['status'],
                    normalized_status=n['normalized']['status'], normalization_operations=n['operations'],
                    output_tokens=v['output_tokens'], truncated=v['truncated'], raw_path=v['raw']['path'], raw_sha256=v['raw']['sha256']))
            acceptance.append(dict(batch=b, model=m, planned=len(reqs), returned=len(views), worlds=len({v['world_cluster_id'] for v in views}),
                                   **dict(counts), score_acceptance=str(folder / 'SCORE_ACCEPTANCE.json')))
            folder2 = root / ('updated_analysis_v2' if b == 'e5_measurement_v1' else 'updated_analysis') / b / m
            rr = add_diag(folder2 / 'world_diagnostics.csv', b)
            new_matrices[(b,m)] = rr
            metric_path = folder2 / ('statistics_v1/conditional_statistics.csv' if b == 'c1_count_v1' else 'conditional_statistics.csv')
            for r in csvread(metric_path):
                # Historical union CSV includes metric columns irrelevant to the other hypothesis group.
                applicable = b != 'c1_count_v1' or ((r['group'] == 'H1') == (r['metric'] in H1))
                stats.append(dict(scope='ORIGINAL_NEW_MEASUREMENT', batch=b, applicable=applicable, **{k:v for k,v in r.items() if k != 'batch'}))
            ac2 = jsonread(folder2 / 'ACCEPTANCE.json')
            if 'matrix' in ac2: check(ac2['matrix'])
    assert len(responses) == 4221 and len(prompts) == 1407
    # Explicit report-only secondary summaries. No hypothesis/prompt/model selection.
    def extra_stat(module, model, group, metric, data, planned, split):
        ww = defaultdict(list)
        for w, value in data:
            if value is not None: ww[w].append(float(value))
        n = sum(map(len, ww.values())); k = sum(map(sum, ww.values()))
        est = lo = hi = None
        if n:
            xx = np.array([[sum(v), len(v)] for _, v in sorted(ww.items())]); rng = np.random.default_rng(20260909)
            ii = rng.integers(0, len(xx), size=(5000, len(xx))); bb = xx[ii].sum(axis=1); bb = bb[:,0] / bb[:,1]
            est = k/n; lo,hi = map(float,np.quantile(bb,[.025,.975]))
        r = dict(scope='REPORT_ONLY_POSTHOC_SECONDARY_NOT_PRIMARY', module=module, model=model, group=group, metric=metric,
                 numerator=k, denominator=n, worlds=len(ww), planned_worlds=planned, estimate=est, ci95_low=lo, ci95_high=hi,
                 status='ESTIMATED' if n else 'NOT_ESTIMABLE', split=split, method='WORLD_CLUSTER_BOOTSTRAP_5000', seed=20260909)
        stats.append(r); return r
    e2group = defaultdict(list)
    for r in e2: e2group[(r['model'],r['source_family'],r['wording'])].append(r)
    for (m, family, wording), rr in sorted(e2group.items()):
        data=[]
        for r in rr:
            ep=r['endpoints']; ok=ep['neutral']['correct'] is True and all(ep[k]['correct'] is not None for k in ('false','sham'))
            data.append((r['world_cluster_id'], int(not ep['false']['correct'])-int(not ep['sham']['correct']) if ok else None))
        extra_stat('E2_POOLED',m,f'{family}/{wording}','FALSE_MINUS_SHAM_GIVEN_NEUTRAL_CORRECT',data,len({r['world_cluster_id'] for r in rr}),'discovery')
    protection=[]
    for (b,m), rr in new_matrices.items():
        if b == 'native_e8_measurement_v1': continue
        groups=defaultdict(list)
        for r in rr:
            if b == 'c1_count_v1' and r['hypothesis']=='H1': continue
            groups[r.get('sequence') or r.get('hypothesis')].append(r)
        for group, rs in groups.items():
            data=[]
            for r in rs:
                ep=r['endpoints']; pre,post,target=('PROTECTED_PRE','PROTECTED_AFTER','TARGET_SA') if b=='c1_count_v1' else ('initial_protected','PROTECTED','TARGET')
                assert pre in ep and post in ep and target in ep, (b, list(ep))
                ok=ep[pre]['correct'] is True and ep[target]['correct'] is True and ep[post]['correct'] is not None
                data.append((r['world_cluster_id'],not ep[post]['correct'] if ok else None))
            protection.append(extra_stat(b,m,group,'PROTECTED_DAMAGE_GIVEN_PROTECTED_PRE_AND_TARGET_CORRECT',data,len(rs),rs[0]['split']))
    save(dest/'04_NEW_PROMPTS.jsonl',prompts,'jsonl')
    csvsave(dest/'05_NEW_RAW_RESPONSES.csv',responses)
    save(dest/'06_WORLD_DIAGNOSTICS.jsonl',diagnostic,'jsonl')
    save(dest/'07_RAW_REFERENCE_INDEX.jsonl',list(endpoint_index.values()),'jsonl')
    csvsave(dest/'03_STATISTICS.csv',stats)
    csvsave(dest/'09_RESPONSE_ACCEPTANCE.csv',acceptance)
    e0=sws/'e0_refresh_20260910_v3_1'
    # This is an explicitly dated historical snapshot, not a live extension-model status refresh.
    for name in ('primary_metrics.csv','primary_statistics_ci.csv','model_status.csv','actual_protocols.csv'):
        shutil.copy2(src(e0/'tables'/name),dest/('E0_'+name))
    shutil.copy2(src(e0/'E0_Full_Benchmark_Results_CN.md'),dest/'02_E0_EXISTING_RESULTS_CN.md')
    c1ac=jsonread(root/'P4_C1/ACCEPTANCE.json')
    c1lock=jsonread(root/'P4_C1/C1_PANEL_LOCK.json')
    csvsave(dest/'10_PROTECTED_BASELINE_GATED_SECONDARY.csv',protection)
    metadata=dict(created_at=now(),export_job=os.environ['SLURM_JOB_ID'],scope='PHASE5_RESULTS_SNAPSHOT_NOT_FINAL_STUDY_CLOSURE',
        models=MODELS,raw_responses=4221,unique_new_requests=1407,source_files=list(sources.values()),
        grade='AUTO_ONLY_PROVISIONAL',human_review='WAIVED_BY_RESEARCHER_NOT_AGENT_VERIFIED',
        new_inference_calls=0,source_modified=False,raw_text_scope='ALL_4221_NEW_RESPONSES; historical endpoints are normalized values plus raw path/hash, not complete historical raw text',
        omitted='Media, weights, source archives, full historical raw files, redundant logs; image-level validity cannot be audited using this text-only export.',
        c1_qualification=c1ac,c1_lock=c1lock,code=entry(__file__),
        scoring='SWS v3 gold-blind normalization then deterministic exact typed values. E0 uses its own label interface.',
        decoding=dict(do_sample=False,enable_thinking=False,max_new_tokens=512,batch_size=1,seed=20260909),
        posthoc_secondary='E2 pooled family/wording differences and baseline-gated protected damage only; no primary metrics changed.')
    save(dest/'11_PROVENANCE.json',metadata)
    def select(batch,metric,group=None):
        return [r for r in stats if r.get('batch')==batch and r['metric']==metric and r.get('applicable',True) and (group is None or r.get('group',r.get('sequence'))==group)]
    def metric_table(rr):
        return table(['模型','条件','事件数/条件分母','条件 world 数','估计 [95% CI]'],[[r['model'],r.get('group',r.get('sequence','—')),f"{float(r['numerator']):g}/{r['denominator']}",r['worlds'],interval(r)] for r in rr])
    chunks = ['''# SpaceConflict 实验结果汇总：供 ChatGPT 分析

## 0. 阅读范围与结论边界

这是 2026-09-10 批次的结果快照，覆盖 Phase5 行为证据闭合及其复用的 Phase4 E0/E2/E5/E8。不是对所有历史 Phase A/B0 的完整重分析，也不意味着主指南全部研究分支已经完成。文件实际生成时间与输入 SHA256 见 `11_PROVENANCE.json`。

核心问题是：空间事实是否会被错误候选陈述改变；更新、原状态保存、无关事实保护、目标状态选择和最终判定，能否在行为上分离。**不预设 Wrong-State Selection 或统一的空间世界状态缺陷已获证明。**

目前最值得继续讨论的是多步更新/分支下的行为不一致，而不是宣布已经找到单一内部机制。C1 false-versus-sham 未在三个模型上稳定复现；C1 的选择条件只有 0–2 个合格 world，不能用 100% 的小分母比例包装成强证据。

所有机制结果沿用 `AUTO_ONLY_PROVISIONAL`：研究者取消了人工审核门槛，不能改写成代理完成了独立人工 VERIFIED。原始数据、gold、旧响应和旧评分均未修改。此次仅汇总和打包，没有运行新模型、训练或新 test。

## 1. 实际完成了什么

三模型为 Qwen3.5-4B、9B、27B；9B 主分析，4B/27B 对照。三模型使用同一提前冻结的 world 和请求，不按小模型失败选择 27B。
''']
    chunks.append(table(['新增批次','world 数/模型','请求/模型','三模型响应','状态'],[
        ['E5 动作与中间状态补测',80,1120,3360,'完成推理、确定性评分、逐 world 诊断和 CI'],
        ['原生 E8 L4 count 补测',9,72,216,'完成；只覆盖窄计数子集'],
        ['C1 新留出 count',9,215,645,'完成；ADD-only，小规模复现'],
        ['合计（world 跨批次不可直接相加）','—',1407,4221,'9 个批次×模型评分验收全部 COMPLETE']]))
    chunks.append('''
其他已经形成的证据：E2 为 2,010 条匹配诊断行、200 个 underlying world；既有 E8 为 957 条诊断行、319 个 level-world anchor（312 个 underlying world）。冻结 E8 实际有 320 个 anchor，其中 1 个未编译，3 个模型的未运行覆盖记录保留在 `08_E8_UNCOMPILED_ANCHORS.csv`，没有默默删除。

原生 E8 的 15 个缺 PRE anchor 中，11 个通过原始构建 prestates 和独立 count verifier 找回；4 个未找回，另 2 个不满足单 ADD/REMOVE 合同，最终 9 个进入本轮补测。不是由 POST 倒推 PRE，也不是让模型补 gold。

C1 从 12 个本地媒体完整且未登记暴露的 CA-VQA validation 源 world 检索证据，经规范事实和匹配资格筛选得到 9 个 count world；候选 525 个媒体核对已登记历史的 21,283 个媒体。只证明相对登记历史的无重叠，不证明无未登记人工浏览或无模型预训练暴露。

## 2. E0：完整 benchmark 的背景成绩

这是已有的 E0 2026-09-10T19:50:38Z 快照，不是新一轮 test。三个主模型各 24,196 条输入、4,284 个 world，L1/L2/L3/L4 输入数分别为 16,598 / 2,424 / 2,602 / 2,572。all-split 仅作全覆盖描述，不能当作独立泛化成绩。

| 模型 | ClaimAcc [95% CI] | PairAcc [95% CI] | 已有 test-only ClaimAcc [95% CI] |
| --- | --- | --- | --- |
| 4B | 55.82% [55.09,56.56] | 36.65% [35.60,37.66] | 55.26% [53.80,56.71] |
| 9B | 59.26% [58.54,60.01] | 43.30% [42.32,44.28] | 56.51% [55.10,57.95] |
| 27B | 62.53% [61.75,63.28] | 51.03% [50.04,51.98] | 56.04% [54.65,57.48] |

test-only 每模型 N=5,608。all-split 的单调提高并未对应严格单调的 test ClaimAcc。PairAcc 要求同一完整 S/C pair 两侧均正确，UNKNOWN 不计入 pair；PairAcc 下降本身不是机制证据。CI 为按来源分层、world 聚类 bootstrap 5,000 次。

L1–L4、来源、track、split、扩展模型及其协议见 `02_E0_EXISTING_RESULTS_CN.md` 和 `E0_*.csv`。该快照 13 个扩展清单模型中 10 个主评测 COMPLETE；Gemma、Qwen3-VL-8B-Thinking 未全量完成，Llama Scout 未运行。部分辅助 judge 尚未完成；这些是快照状态，不是本报告生成时的实时进度。扩展模型不能与下面的三模型机制补测混作一个实验。

## 3. E2 → C1：错误候选是否特异性改变事实报告

条件：neutral 原本正确的匹配记录，对比 false candidate 与 irrelevant sham。不是只看 false 条件准确率；同一 world 的多个 offset 不是独立样本。

下表为 C1 新的 9 个 count world：差值是 false 错误率减 sham 错误率，单位百分点；列中分子为净错误数差，不是单个二元事件数。
''')
    chunks.append(metric_table(select('c1_count_v1','false_minus_sham','H1')))
    chunks.append('''
4B false/sham 为 0/15 与 1/15；9B 为 5/19 与 3/19；27B 为 3/19 与 0/19。9B 的差值 CI 跨 0，27B 下界为 0，4B 方向相反：**不足以声称存在跨规模稳定的 false-specific fact corruption**，也不能据此证明不存在效应。

E2 原有分 case/family/wording 的全部统计保留在 `03_STATISTICS.csv`。下面仅为 9B 按 family/wording 汇总的报告阶段探索性描述（不是新主指标，不替代原分层，也不是 C1 确认检验）：
''')
    chunks.append(metric_table([r for r in stats if r.get('module')=='E2_POOLED' and r['model']=='qwen35_9b']))
    chunks.append('''
## 4. E5：初始事实与动作答对后，更新是否仍失败

80 个冻结 count world，各有 INVERSE 和 TWO_STEP；每条动作 3 个字段（TYPE/TARGET/AMOUNT），两步共 6 个字段全对才算 action correct。初始 target 和 protected 事实均对才进入 initial+action 条件。不同模型合格分母不同，不能把这些条件比例直接解释为规模的因果效应。

### 4.1 初始事实和动作正确，最终 target 错误
''')
    chunks.append(metric_table(select('e5_measurement_v1','final_wrong_given_initial_action')))
    chunks.append('''
### 4.2 同一动作序列的中间状态正确，最终 target 错误
''')
    chunks.append(metric_table(select('e5_measurement_v1','step2_wrong_given_step1')))
    chunks.append('''
TWO_STEP 的条件失败在 4B/9B 很明显，27B 较少，但 27B 也并非始终正确。INVERSE 相比 TWO_STEP 不同，提示任务结构有影响。这里是**同 world、同序列的跨调用行为匹配**：初始事实来自既有 E1，最终状态来自既有 E5，动作/中间状态是新补测；不是一次生成中的真实中间轨迹，不能断言模型在内部已经正确执行第一步却忘记第二步。

### 4.3 原状态/无关事实保护：不要混淆“答错”和“被破坏”

原指标 `protected_wrong_given_target` 或 C1 的 `protected_wrong_given_post` 没有要求 protected 的初始报告正确，不能直接称干预导致损坏。以下是本报告额外计算的 **post-hoc secondary**：同时要求 protected PRE 正确、target POST 正确后，protected AFTER 错误。没有修改冻结主指标或按结果换题。
''')
    chunks.append(metric_table(protection))
    chunks.append('''
这些仍是跨调用行为转变，不证明内部存储被覆盖；感知不稳定、重数、提示/状态措辞差异和比较接口仍是竞争解释。未经 PRE 条件化的原指标也完整保留在 CSV，供核对。

## 5. C1：POST、保存与选择的窄子集结果

C1 为 9 个新 count world，ADD-only；三个明确状态的计数为 pre、pre+2、pre+3，不混为二元 LEFT/RIGHT。

### 5.1 PRE 与 action 正确时，POST 错误
''')
    chunks.append(metric_table(select('c1_count_v1','post_wrong_given_pre_action','H2_H3_H4')))
    chunks.append('''
### 5.2 JOINT_STATE 正确时，目标状态回答错误
''')
    chunks.append(metric_table(select('c1_count_v1','selection_wrong_given_joint','H2_H3_H4')))
    chunks.append('''
特别注意：4B/9B 的 100% 来自 2/2 和 1/1；27B 为 0/0（没有 JOINT_STATE 全正确的合格 world），不是 0% 错误。这个指标记录任意 target 错误，包含可能的 null 或不对应其他合法状态的值，**不能自动称“选中了另一个状态”**。必须逐条检查 `06_WORLD_DIAGNOSTICS.jsonl` 的 JOINT_STATE 和 TARGET_S0/SA/SB，再区分 other-state attraction、一般数值错误与弃答。

† 退化 bootstrap [0,0] 或 [100,100] 只反映当前样本重采样，绝不意味着真实误差率确定无疑。例如 2/2 和 1/1 的二项 Wilson 95% 敏感性区间约为 [34.24%,100%]、[20.65%,100%]；本报告不以此替换原 bootstrap 主区间。

## 6. 原生 E8：找回构建证据后的补测

固定 9 个 L4 count world，下面每个事件按 world 计数，分母为满足前件的 world。verdict 错误定义为该 world 的 supported/contradictory 判定至少一项错误，不是逐 claim 错误率。
''')
    for metric in ('post_wrong_given_pre_action','select_wrong_given_joint','verdict_wrong_given_post'):
        chunks.append('\n### '+metric+'\n\n'+metric_table(select('native_e8_measurement_v1',metric)))
    chunks.append('''
TARGET_PRE/POST 在此批次分别别名引用 PRE_VALUE/POST_VALUE，同一物理响应不能当作独立的 selection 复现。ACTION_TARGET 的 noun/NONE 枚举是有限合同，不代表已经验证复杂 object grounding。9 个 count world 不能支撑“全部空间任务的统一失败机制”。

原有 E8 的 L1–L4 分层证据与缺项均保留。L1 独立 object/argument gold 和 L3 local/alignment/global 链仍有缺口；不能把缺测或空条件解释为模型没有失败。不要混合 L1 低阶控制与 L4 状态推理。

## 7. 输出接口和统计可靠性

实际新增请求为 greedy、thinking disabled、batch_size=1、512 输出 token 上限。只对保留的前缀评分；截断本身不自动判无效。本轮行为实验用 SWS v3 不读取 gold 的格式规范化，再做 typed value/facts 的确定性精确评分，**不是用 4B judge 来决定这些条件指标**。E0 的 label/confidence/reason 协议及自动解释辅助分是另一套测量。

接口计数（null 是合法 schema 下的弃答，不等于解析无效；次数是物理响应，不是重复 endpoint 引用）：
''')
    chunks.append(table(['批次','模型','返回','严格解析无效','规范化后无效','含 null 响应','达到截断标记'],[
        [r['batch'],r['model'],r['returned'],r.get('strict_invalid',0),r.get('normalized_invalid',0),r.get('null_response',0),r.get('truncated',0)] for r in acceptance]))
    chunks.append('''
9 个验收全部 COMPLETE、规范化后无效和未运行均为 0，不代表没有内容错误或视觉问题。原回答、格式转换操作、null、错误和全部反例保留在 `05_NEW_RAW_RESPONSES.csv`。历史 E5 的空 action 占位已在派生 v2 表中与新测量分离，本包使用 updated_analysis_v2，不用旧占位制造“仍未运行”的假象。

统计以 underlying world 聚类 bootstrap 5,000 次、固定 seed 20260909；重复 offset 的点估计为匹配记录等权，不是 world-macro。CI 是 world 抽样不确定性，不是重复生成方差。小样本、条件筛选、退化区间及多重探索均限制解释；本轮未做多重检验校正，不把某一个 CI 作为全研究的正式显著性结论。C1 混合 CSV 中跨组无适用性的空统计行标为 applicable=false，不能当成真的未运行实验。

## 8. 尚未闭合的分支与不能声称的结论

| 分支 | 当前边界 |
| --- | --- |
| C1 泛化 | 只有 9 个新 count world；无合格 non-count 留出；没有覆盖 H5 |
| 真正必要的多视图 | 来源清单有候选，但尚无通过必要性证据的合格 world；G4–G8 不得冒充已运行 |
| 原生 TIME/FRAME/BRANCH | 候选来源盘点不等于合格原生匹配实验；需明确与可控文本分支不同 |
| Genuine observation | 没有形成合格真实新观测 matched test，不能声称证实了真实观测下的状态更新 |
| E8 非计数/低阶链 | 部分中间 gold 和匹配端点缺失，缺口保留 |
| C2/有限白盒 | 本阶段未扩展；没有凭本轮结果获得可直接声称的机制锁或白盒因果证据 |
| 整体项目验收 | 新补测完成，不等于主指南所有分支完成；本包是分析快照，不冒充最终 REVIEW 验收包 |

来源目录盘点覆盖 5,536 个 world；多视图来源候选 2,445 个不等于合格实验样本。缺口意味着证据边界，并不自动意味着原 benchmark 的问题答案无效。

## 9. 请 ChatGPT 重点评估什么

1. E5 的 TWO_STEP 失败与 C1 小规模结果放在一起，最稳妥的论文主张是什么？应保留哪些反例？
2. false-versus-sham 在 discovery 与 C1 上的差异，是否更像任务/来源/措辞依赖，而非稳定 claim-induced fact corruption？不要只看正向结果。
3. 对 PRE、action、POST、protected、JOINT、target、verdict 的逐 world 响应，哪些只能支持跨调用功能分离，哪些仍无法区分感知、更新、状态选择、比较与接口？
4. 小分母选择结果是否应降级为未解决？请区分真的报告了另一合法状态、其他错误值和 null，不把二元标签当作机制证据。
5. 在不按失败挑 world、不反复调提示的前提下，最小的下一阶段证据需求是什么？哪些主张现在必须撤回或降级？

建议判断：当前证据更适合支持“任务结构依赖的、异质的更新/保存/判定不一致”，而非“单一、已定位的 Wrong-State Selection”。格式不合规导致无效分这个解释在新补测的规范化计分口径下不再足以解释失败；但感知误差、重数不稳定、跨调用测量差异、状态措辞和候选影响尚未普遍排除。任何进入内部机制分析的建议都应先说明对应的可复现行为锚点。

## 10. 文件导航与复现

先读本报告和 `02_E0_EXISTING_RESULTS_CN.md`；统计和 CI 查 `03_STATISTICS.csv`；英文实际问题、system prompt、媒体角色/hash 在 `04_NEW_PROMPTS.jsonl`；用 request_id 把它与 `05_NEW_RAW_RESPONSES.csv` 连接。`06_WORLD_DIAGNOSTICS.jsonl` 保留所有诊断行及端点真值、回答、状态、反例，`07_RAW_REFERENCE_INDEX.jsonl` 为历史原响应路径/hash 索引。

本包包含全部 4,221 条新增原始回答文本，但没有所有更早历史响应的全文；历史端点提供规范化值与原文件索引。包不含图片、视频、权重、下载源档案和冗余日志，因此 GPT 可复核文本与统计，不能独立核验真实视觉内容。原始大文件仍在实验室持久存储，具体路径和输入 SHA256 见 `11_PROVENANCE.json`。所有未运行/不适用/空条件继续保留。

`12_REPRODUCE_CN.md` 记录本次导出命令和输出校验。不要为了复现这份汇总重新提交推理。不要把本报告的分析建议当成自动授权进入训练、白盒或新 test。
''')
    report='\n\n'.join(chunks)
    reportpath=dest/'01_RESULTS_SUMMARY_CN.md'; reportpath.write_text(report,encoding='utf-8')
    start='''# 给 ChatGPT 的阅读入口

请先读 01_RESULTS_SUMMARY_CN.md，再按问题查看表格。请评估证据强度与竞争解释，不预设某个机制成立，不混合 discovery/confirmation、L1/L4、count/non-count，也不把条件分母为 0 当作 0% 错误。

包中 05 是全部新增原始回答全文，04 是对应实际英文输入；不是只选成功或失败案例。03 是统计与 CI；06 是完整诊断行（嵌入历史端点规范化回答）。媒体未包含，不能声称已审核实际图像。E0 是既有带日期的快照，未实时刷新扩展模型。

请给出：能支持/不能支持的论文主张、最强反例、尚未排除的竞争解释、最小必要下一步。先陈述分析采用的 world/条件分母和数据范围。
'''
    (dest/'00_START_HERE_CN.md').write_text(start,encoding='utf-8')
    command=f"sbatch --partition=general --account=YOUR_ACCOUNT --qos=allocated --nodes=1 --ntasks=1 --cpus-per-task=2 --mem=16G --time=00:10:00 --output='{HERE.parent}/report_export_%j.out' --error='{HERE.parent}/report_export_%j.err' '{HERE}/job_cpu.sh' export_gpt_results_v1"
    (dest/'12_REPRODUCE_CN.md').write_text(f'# 复现与保护\n\n作业 {os.environ["SLURM_JOB_ID"]}；只读汇总，无新模型调用。\n\n```bash\n{command}\n```\n\n导出目录是不可覆写保护；重复执行会主动失败。若需要独立复核，请复制导出代码并指定全新的导出目录及文件名，不修改源结果。输入哈希在 11_PROVENANCE.json，包内校验在 SHA256SUMS。实际导出代码附在 export_gpt_results_v1.py。\n',encoding='utf-8')
    shutil.copy2(__file__,dest/'export_gpt_results_v1.py')
    files=sorted(p for p in dest.iterdir() if p.is_file())
    (dest/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in files),encoding='utf-8')
    # Check exported joins and complete counterexample coverage before publishing.
    assert len(csvrows(dest/'05_NEW_RAW_RESPONSES.csv')) == 4221
    assert len(list(rows(dest/'04_NEW_PROMPTS.jsonl'))) == 1407
    archive=HERE.parent/'SpaceConflict_Phase5_GPT_Analysis_Package_20260910.zip'
    final_report=HERE.parent/'SpaceConflict_Phase5_Results_For_GPT_CN.md'
    if archive.exists() or final_report.exists(): raise RuntimeError('REFUSE_OVERWRITE_PUBLISHED_EXPORT')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(dest.iterdir()):
            if p.is_file(): z.write(p,p.name)
    with zipfile.ZipFile(archive) as z: assert z.testzip() is None
    shutil.copy2(reportpath,final_report)
    save(dest/'EXPORT_ACCEPTANCE.json',dict(status='COMPLETE_RESULTS_SNAPSHOT_NOT_FINAL_STUDY',archive=entry(archive),report=entry(final_report),
        raw_response_rows=4221,prompt_rows=1407,diagnostic_rows=len(diagnostic),statistics_rows=len(stats),
        score_acceptance_checked=9,zip_crc_passed=True,source_hashes_recorded=True,originals_modified=False))
    print(json.dumps(dict(report=str(final_report),archive=str(archive),archive_bytes=archive.stat().st_size,
        acceptance=acceptance,protection=protection),ensure_ascii=False),flush=True)

if __name__=='__main__': main()
