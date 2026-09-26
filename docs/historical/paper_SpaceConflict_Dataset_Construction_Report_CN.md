# SpaceConflict 数据集整理与构建说明（论文写作版）

核对日期：2026-09-17。本文根据实际构建代码、冻结 release、manifest、自动审计和已有 E0 元数据整理，不把最初指南中的计划数量当作已经完成的结果。本次只新增说明文档，没有修改原始数据、gold、划分或历史预测。

## 1. 数据集究竟是什么

SpaceConflict 是一个**基于现有多模态数据、由来源可追溯的事实和受约束语义编辑构建的空间陈述一致性 benchmark**。它不是重新拍摄的图像/视频库，也不是将多个上游 VQA 数据集的原题直接拼接起来。

我们的新增部分是：统一事实表示、带上下文的空间命题、成对的正确/矛盾陈述、证据不足样本、干预分支、构造轨迹，以及可程序复核的答案证据。

模型的基本任务是：结合给定图片、多个视图或视频，以及题目提供的范围/视角/干预条件，判断一条英文陈述属于：

- `SUPPORTED`：在指定上下文中，已有证据支持该陈述。
- `CONTRADICTORY`：同一上下文中的证据明确反驳该陈述。
- `UNKNOWN`：现有证据不足，陈述成立和不成立都仍与可用证据相容。

其中，“没有标注”“没有看到”“图里没有这条边”不自动等于否定。未选中的选择题选项也不自动成为矛盾陈述。

### 1.1 三个计数单位

| 单位 | 含义 | 当前数量 |
|---|---|---:|
| Pair | 同一媒体和上下文下的一条 S 陈述与一条 C 陈述 | 10,948 |
| Claim / model input | 模型独立判断的一条陈述；一个 pair 对应两条 | 21,896 条 S/C + 2,300 条 U = **24,196** |
| Underlying world | 将不同来源指向的同一底层场景归并后的统计单位 | **4,284** |

因此，论文不要将“10,948 pairs”“24,196 inputs”和“4,284 worlds”都写成 questions。UNKNOWN 单独计数，不人为配成 S/C pair。

## 2. 当前冻结版本和实际规模

当前完整 benchmark 是两个版本的组合，而不是把所有历史版本累加：

1. L1–L3：`release/production_available_v10/`。
2. L4：`l4/v3_3/release/`。

| 层级 | S/C pairs | SUPPORTED | CONTRADICTORY | UNKNOWN | 总输入数 |
|---|---:|---:|---:|---:|---:|
| L1 | 7,559 | 7,559 | 7,559 | 1,480 | 16,598 |
| L2 | 1,212 | 1,212 | 1,212 | 0 | 2,424 |
| L3 | 1,041 | 1,041 | 1,041 | 520 | 2,602 |
| L4 | 1,136 | 1,136 | 1,136 | 300 | 2,572 |
| 合计 | **10,948** | **10,948** | **10,948** | **2,300** | **24,196** |

上述 claim 数量与现有 E0 论文证据表一致。S/C 在每个 pair 内严格平衡，但 Level、source、operator 和 UNKNOWN 的分布并不均衡；不能描述为“四级均衡数据集”。

### 2.1 数据来源及贡献

下表贡献数量均为 **S/C pairs**，不包含 UNKNOWN，避免将不同单位相加。

| 上游来源 | 在实际制作中的作用 | 最终 pairs |
|---|---|---:|
| CA-1M / CA-VQA | 参考帧与支持帧、定性关系、可见性和精确计数；从合格 QA 重建带范围的事实 | 5,351 |
| SPAR（含 SPAR-7M 来源） | 显式空间关系、对象定位/绑定、合格的二前提关系链和多视图题 | 2,900 |
| OmniSpatial | 从可明确复原的定性空间 QA 构造陈述对 | 1,108 |
| VSI-Bench | 视频内计数、出现顺序及符合规则的组合关系 | 407 |
| STI-Bench | 有明确视频时间范围的定性关系与对象绑定 | 46 |
| Hypo3D 场景体系 + L4 衍生构造 | 原生干预及受控干预的状态陈述；见第 6 节 | 1,136 |
| 合计 | | **10,948** |

L4 还利用了 EmbodiedScan、3DSSG、ReferIt3D 等结构化来源补充对象目录、唯一指代、精确类别数量或关系证据。它们是**辅助 grounding / PRE 证据来源**，不能把这 1,136 对全部说成“直接取自 Hypo3D 原生 QA”。MMScan 静态场景标注也不能自动充当 Hypo3D 干预后的 POST 真值。

SCOPE 和 EmbodiedBench 未进入当前构建流程：前者当时未确认生产数据源，后者没有启用 simulator oracle 流程。

### 2.2 下载的数据量不等于 benchmark 数据量

下载完整上游数据，是为了查找原始标注、补齐媒体和建立可验证的事实。最终只引用通过构造与验证、被抽样选中的条目及其所需媒体。

例如，registry 记录 CA-VQA 完整下载约 **11.58 TB（十进制）**，但这不是 SpaceConflict 的容量，也不意味着模型评测逐个使用了其中所有文件。实际构建只使用符合条件的源条目；内部评测包收集题目所引用的媒体，不包含全部未引用的上游媒体。旧评测包的容量和缺失媒体统计属于当时快照，不能直接当作补齐后的当前容量。

## 3. 原始资料如何整理成可构造的数据

### 3.1 冻结来源，而不是只保存下载链接

`datasets.yaml` 记录来源仓库、revision、数据路径、下载/校验记录、适用任务和来源限制。各来源有独立、带版本的 contract，规定：

- 一个 world 是什么，例如 scene、capture 或 parent video。
- 哪些原生标注和 QA 能转成事实。
- 什么条件下可以认定两个对象是同一实例。
- 允许哪些空间谓词、作用范围、参考系和推导规则。
- 哪些问题必须拒绝，例如目标不唯一、时间范围不清楚或缺少证据。

原始文件保持只读。清洗、适配和构造结果写入独立中间目录，并保存源条目 ID、源文件 hash、配置、随机种子和拒绝原因。

### 3.2 源数据适配与事实重建

不同来源的 QA/标注由专门 adapter 转为统一结构。一个事实不仅有“谁在谁左边”，还必须携带它成立的上下文：

```text
fact = predicate(subject, object/value)
     + world_id
     + media/view/frame
     + reference_frame
     + time_scope / scope
     + state_id / branch_id
     + source provenance
```

例如，`COUNT(chair)=2` 只有与“指定参考帧内可见”“整个场景”“干预后的分支”等范围一起才有确定含义。不能将不同范围的计数合并。

适配后的事实要能重建原始题意及答案；无法唯一重建、指代不稳定或互相冲突的记录被拒绝，不依赖模型常识补齐。

实际实现中特别处理过两类身份问题：

- SPAR 的组合关系使用同图路径与精确 bbox 等来源依据对齐实体，不能只因类别名相同就合并对象。
- CA-VQA train 条目使用完整 TFRecord 文件名、record index 和 QA index 等定位来源，避免不同 shard 的 ID 冲突；部分 world 由有序图像组合的内容标识建立。

因此，某些来源的 world 是来源支持的媒体组合单位，不能一概宣传成精确恢复了完整物理场景。

### 3.3 部分世界图与最小证据子图

同一 world 的已知事实形成 **partial world graph**。图是部分的，不声称含有场景中的所有物体、关系或状态。

构造某题时，从中提取真正使用的 evidence subgraph；保留事实 ID、来源、规则和推导顺序。图里没有的事实不会自动补为 false，也不允许使用模型预测事实作为 benchmark gold。

构造流程可概括为：

```text
冻结来源与 contract
  → 源标注/QA 适配与重建
  → world 索引与 world-ID 划分
  → 部分世界图与证据子图
  → 受支持命题
  → 类型化语义编辑，构造矛盾命题
  → 答案证据与规则验证
  → 英文实现与 graph–text–graph 检查
  → 自动验收、去重与配额抽样
  → 冻结 release，并分离模型输入与 gold
```

## 4. 正确题和错误题具体怎样制作

SpaceConflict 的主体不是让语言模型自由编写一个“看起来错误”的句子，而是先确定图上的命题与真值，再生成英文陈述。

1. 从来源事实或获准规则推导出 supported claim。
2. 在同一媒体、world、参考系和时间/状态范围内，对命题进行有类型的语义编辑。
3. 用证据检验编辑后的命题确实被反驳；如果只是不知道，就不能标为 CONTRADICTORY。
4. 为两条陈述保存共享证据、修改位置、规则和 certificate。
5. 最后将命题实现为英文，保持成对表达风格和上下文一致。

L1–L3 最终 release 的编辑算子分布如下：

| 算子 | 实际含义 | pairs |
|---|---|---:|
| `SUBJECT_OBJECT_SWAP` | 保持关系词，交换主语与宾语 | 5,284 |
| `COUNT_CLASS_REBIND` | 保持精确数量，将该数量错误绑定到另一个有可反驳证据的类别 | 2,577 |
| `RELATION_GRAPH_UNSAT` | 利用不可约组合关系构造与关系图不一致的命题 | 1,212 |
| `VISIBLE_CLASS_REBIND` | 将可见性事实错误绑定到另一个类别 | 498 |
| `APPEARANCE_ORDER_ERROR` | 错置视频内对象/事件出现顺序 | 195 |
| `SUBJECT_OBJECT_REBIND` | 在指定时间范围内错误绑定主体/客体 | 46 |

这些数量来自实际 quota 报告，不是指南允许的全部算子列表。L4 使用另外的状态变化算子，不能将上表当作全数据集算子统计。

### 4.1 英文题面的生成方式

当前 L1–L3 实现采用确定性的英文模板、关系词变体和成对共享的实体别名。先选定结构，再实现文字；不是通过反复询问模型、按模型错误率挑选措辞。

每条题面保存文本片段到实体、关系、数量和上下文的对齐，随后解析回图并比对。这样可检查语言实现是否改变了原命题。

“Minimal pair”主要指**结构语义上的受控编辑**，不意味着正反题一定只差一个 token。它也不意味着全库英文句子完全不重复：L1–L3 审计记录表面文本重复率约 25.89%，但 `claim + media` 复合键通过唯一性检查。相同文本在不同场景可对应不同实例。

## 5. L1–L4 如何定义，实际分别做到了什么

层级由证据依赖结构定义，不是根据模型答错多少来划分，也不是经验准确率必然单调的难度等级。

| Level | 设计含义 | 当前实现应如何描述 |
|---|---|---|
| L1：Atomic Conflict | 显式事实上的局部一致性 | 对象交换、类别绑定、可见性与精确数量等局部矛盾；可能提供多张图，但不能因此自动称为高阶推理 |
| L2：Compositional Conflict | 多个不可约前提共同约束结论 | 当前主要是获准关系上的**唯一、不可约二前提传递链**，不是所有 2–4 跳图推理类型都已覆盖 |
| L3：Latent World Conflict | 需要跨视图、时间或参考系的证据 | 当前包括合格多视图关系、视频出现顺序和指定时间区间关系；不是任意视频题都视为 L3 |
| L4：Intervention Conflict | 干预后状态与陈述的一致性 | 区分原生变化、受控变化、core 与 calibration；并非每个 L4 都严格需要 PRE 与 action 的联合推理 |

L2 代码明确排除：已有直接结论、存在多条替代证明路径、跨上下文拼接，以及删去一个选定前提后结论仍可成立的情形。传递规则只在来源 contract 允许时使用。

L3 的 SPAR 扩展采用严格多视图输入筛选；视频任务保留来源声明的时间范围，不制造未提供的对象跨帧身份关系。

设计上有 `GEO-TOPO`、`XFORM-PROJ`、`DYNAMIC`、`IDENTITY`、`EMBODIED-OBS` 等 track，但不应把设计空间说成最终均有充分覆盖。L1–L3 当前 primary-track 为 GEO-TOPO 8,771、XFORM-PROJ 800、DYNAMIC 241；另两类没有 primary-track 样本。后补 L4 track 应单独注明 derived annotation 版本，不能混同原始发布字段。

## 6. L4 为什么单独重建，以及最后怎样构建

### 6.1 为什么不能只拿 Hypo3D 的 POST 答案改写

原始 Hypo3D 提供变化描述和变化后 QA，但不是所有题目都有可直接恢复的 PRE 状态、唯一操作目标和可重放转移规则。早期 adapter 虽形成 3,335 个候选，但当时可证明满足严格 L4 构造要求的候选为 0；候选量不能当最终 L4 数量。

后续采用问题相关的局部 transition micrograph，结合对象目录和唯一指代；随后按新版指南扩展为 Native、Controlled 和 Unknown 三组成。关键是保留不同真值来源，而不是将所有样本包装为同一种生成方式。

### 6.2 L4-Native：利用原生干预与原生 POST 标注

保留 Hypo3D 的 scene、change/branch 和 QA 对应关系，规范化源 POST 事实，再生成英文 S/C 陈述。

- **Native-Direct：201 pairs**。
- **Native-Aggregated：215 pairs**。
- 合计 **416 pairs**。

Aggregated 将同一 `(scene_id, change_id)` 分支的多个 QA 事实合并、按事实去重；不同变化分支不混合。当前代码的扩展路径按该分支 POST fact graph 是否含多个事实确定 subtype，因此 **Aggregated 不等于每题都需要多跳推理**，也不等于用前题模型答案生成后题 gold。

Native 的标签证据可以来自源 POST QA；这与“模型只凭可见 PRE 媒体和 action 是否能可靠推出该答案”是两个问题。论文应区分来源答案的一致性校验与实际输入可解性，不能只因 `AUTO_ACCEPTED` 就断言每题已通过人工可解性审核。

### 6.3 L4-Controlled：真实场景初态上的受控变化

使用来源支持的初始计数、对象或关系，定义 benchmark 自己的明确动作 DSL，计算变化后的局部状态。不是生成一个新的真实拍摄 POST 场景，也不是物理仿真视频。

当前动作家族包括：

- `REMOVE_AND_RECOUNT`：移除唯一目标后重新计数。
- `ADD_AND_RECOUNT`：加入一个指定类别实例后重新计数。
- `REPLACE_AND_RECOUNT`：替换后更新相关类别数量。
- `REPLACEMENT_IDENTITY`：区分原对象与替换后的新实例。
- `MOVE_TO_OPPOSITE_SIDE`：沿指定轴移动到锚点的另一侧。
- `SWAP_POSITIONS`：沿指定轴交换对象位置。

两个分离实现的程序 `engine_a` 与 `checker_b` 从 PRE facts 和 action 得到 POST facts，要求结果完全一致；随后检查 S 可推出、C 被反驳，以及图文一致性。

需要如实注明：部分关系初态取自 3DSSG 显式关系，部分取自 EmbodiedScan 9-DoF box 的轴向严格分离判断。当前几何函数使用 `margin=0.02`（源坐标单位），参考系为 `source_world_axes`。因此不能沿用旧总规范，笼统写成“整个最终版本完全没有数值几何或阈值派生关系”；题目不要求输出距离，不等于构建时从未使用几何数值。参考轴与实际媒体是否清楚对应也是需要披露的可观测性边界。

### 6.4 Core 与 Calibration 不混淆

| L4 发布组成 | pairs |
|---|---:|
| Native-Direct | 201 |
| Native-Aggregated | 215 |
| Controlled-Core | 630 |
| Controlled-Calibration | 90 |
| 合计 | **1,136** |

Controlled 总计 720，占 L4 的 63.38%。**全体 Calibration 为 109，而不是 90**：90 个 Controlled，加上 19 个 Native；对应 core 为 1,027。

Core 的意图是需要初态与干预联合决定答案；Calibration 允许动作本身已足够，例如移除后不存在、替换产生新身份。代码中的依赖标记/规则验收不等于每题都做过真实模型干预消融；实际行为验证应作为后续实验单独报告。

最终 L4 transition-family 数量为：MOVEMENT 556、REPLACEMENT 203、REMOVAL 196、ADDITION 178、ATTRIBUTE 3。这是来源变化类型统计，不能等同于六个 controlled DSL 算子的数量。

## 7. UNKNOWN 是如何制作的

UNKNOWN 不是随机写一个离谱句子，也不是把模型答错的题改为“不知道”。它检验的是在**当前实际可用输入**下能否确定真值。

主要做法是从可判定题移除决定性证据，或明确保留一种使后态不唯一的欠规定情形，同时记录：

- 原始确定题/parent ID。
- 可用与被移除的证据 ID，以及应从模型输入移除的媒体访问路径。
- 使陈述为真的一个可行补全，以及使其为假的另一个可行补全。
- 缺少什么证据、增加哪类证据才能判定。

可行补全用于证明“不确定”，不是声称真实世界同时处于两种状态。构造时还要防止被删证据仍通过 archive member、重复媒体引用或别名访问。

L1–L3 最终有 2,000 条 UNKNOWN：L1 为 1,480、L3 为 520，L2 为 0；这一部分从 test 来源构造，不能宣称各层或各 split 的 U 都平衡。

L4 有 300 条，四种原因各 75 条：

| 原因 | 含义 |
|---|---|
| `MISSING_PRE_COUNT` | 缺少决定更新结果的初始数量证据；该路径实际移除媒体 |
| `REFERENCE_FRAME_AMBIGUITY` | 没有确定参考系 |
| `UNRESOLVED_POST_IDENTITY` | 替换后的实例身份语义未指定 |
| `POST_STATE_UNDERSPECIFIED` | 动作没有说明足以唯一确定的最终空间状态 |

按发布审计的分类，L4 中 225/300（75%）标为 evidence ablation，余下 75 为 source underspecification。这里的 ablation 不全是“少一张图”，也包含移除决定性条件。

## 8. 答案、解释与质量验证如何组织

### 8.1 Gold 不由被测模型或评分模型生成

确定题的 gold 来自已接受的源事实/QA 与受约束规则；Controlled POST 来自确定性转移程序。模型生成的 `reason` 是评测输出，不是制作时的事实真值。后续 Qwen judge 对解释的评分，也不改变 benchmark 的 S/C/U 标签。

每个 pair 通常保留：`pair_id`、source/revision/hash、world、split、level/track、media references、S/C 的文本与结构、operator、certificate 和 construction trace。L4 进一步记录 PRE、action、branch、origin、dependency type 和 POST 命题。

模型输入与私有验证材料必须分离：不向模型暴露正确标签、成对另一侧的答案标记、POST oracle、proof/certificate 或通过字段名泄露的 `supported_claim` / `contradictory_claim` 容器。

### 8.2 已执行的自动检查

L1–L3 的验证链包括：来源重建、上下文/图一致性、证明重放、最小证据检查、图文往返、成对表达检查、独立规则验证、去重、hash/schema 和 world-ID split 审计。UNKNOWN 还检查可行补全与被删证据。

实际审计记录：

- L1–L3 release audit：`PASS`，9,812 pairs、19,624 binary claims、2,000 UNKNOWN；schema/hash/媒体角色及登记 world-ID split 错误为 0。
- L1–L3 replay audit：13,936 条使用到的唯一证据事实被重放，49,060 个 artifact 引用，失败数 0。
- L4 final audit：`PASS`，1,136 pairs、300 UNKNOWN；pair/action/UNKNOWN schema 错误为 0；当时检查的 2,205 个唯一媒体文件缺失 0、hash 错误 0。

这些数字描述对应版本、对应检查的结果，不等于“所有上游事实绝对正确”“所有模型 processor 后输入都经过人工检查”或“所有可能的语言捷径都已排除”。来源标注可能有错；模板表达可能有偏；程序间也可能共享错误假设。

原始 benchmark 的仓库政策没有正式的全量人工标注验收阶段，使用 `AUTO_ACCEPTED`。后续诊断研究的研究者检查/审核豁免，不应倒写为全量 benchmark 的独立双人标注或人工一致率。

## 9. 抽样、划分与一个必须披露的历史问题

### 9.1 抽样与配额

构造器先对来源 world-ID 建立划分，再生成英文，尽量避免同一已登记 world 的不同题面跨 split。

world split 程序按种子与 world ID 的哈希排序，基础目标比例为 train/dev/test = 60%/15%/25%；最终 pair/input 比例受不同 world 题量、可证明候选和配额影响，不等于该比例。

L1–L3 最终从 11,276 个已自动验收候选中选出 9,812 对。配额阶段分别记录 bucket cap 拒绝 820、test-world-level cap 拒绝 321、world cap 拒绝 323。配置中 test world pair cap 为 4、非 test 为 16，SPAR 的 L1/L2/L3 bucket 上限分别为 1,100/1,000/800；抽样种子为 20260826。

L4 发布配置种子为 20260829。其 test 采用每 world 最多 2 对、同 world/family 最多 1 对、UNKNOWN test 每 world 最多 1 条。最终 test 为 225 pairs，未达到 250–350 的软目标，没有为补数量放宽证明门槛。

### 9.2 合并后的历史 split 数量

| 历史 split | S/C pairs | S/C inputs | UNKNOWN | 总 inputs |
|---|---:|---:|---:|---:|
| train | 7,470 | 14,940 | 182 | 15,122 |
| dev | 1,707 | 3,414 | 52 | 3,466 |
| test | 1,771 | 3,542 | 2,066 | 5,608 |
| 合计 | 10,948 | 21,896 | 2,300 | 24,196 |

### 9.3 4,484 与 4,284 的差别，以及底层场景交叉

原发布 ID 口径共有 **4,484 个 global_world_id**。后续 E0 的 `world_identity_v2` 将 `hypo3d:scene…` 映射回 `scannet:scene…`，将相应 UUID 场景映射回 `3rscan:…`，底层场景口径得到 **4,284**。

本次对已冻结的 24,196 行元数据做了轻量复核：

- 同一原始 `global_world_id` 出现在多个 split：**0**。
- 同一归并后 `world_cluster_id` 出现在多个历史 split：**123**，涉及 **1,299 inputs**。
- 其中 train/test 交叉 75 worlds，train/dev 32，dev/test 16。
- 可追溯例子：`hypo3d:scene0001_00` 在 test，`scannet:scene0001_00` 在 train；二者映射到同一 underlying world。

因此，论文可以说“构造时按登记的来源 world ID 划分”，但**不能说当前合并 release 已完全实现跨来源底层场景隔离**。这不意味着 1,299 条标签错误，也不意味着当前被测预训练模型在这些题上训练过；它限制的是将历史 split 视为严格独立场景训练/测试划分的说法。

当前 all-split E0 是描述性全覆盖评测，不等于独立 test 泛化实验。如果以后用于训练或严格 held-out 评测，需要另建不可变版本，按 underlying-world 重新分组或排除重叠 world；本次没有改动历史 split 或分数。

## 10. 文件如何保存、组织和复现

### 10.1 代码与制作证据

项目根目录：

```text
external/projects/
  iclr benchmark/space contradict benchmark/SpaceConflict/
```

重要内容的职责如下；不同历史 run 使用各自版本子目录，不应将它们重复合并：

```text
datasets.yaml / contracts/ / configs/   来源登记、语义规则、构建配置
data/raw/                              原始数据引用/只读来源
data/canonical/                        统一后的事实与来源定位
world_index/ / splits/                 world 索引及划分
world_graphs/ / evidence_subgraphs/    世界图及题目证据
claim_graphs/                         结构化 S/C 命题
construction_traces/ / certificates/  编辑轨迹与答案证明
realizations/ / realization_traces/   英文题面及结构对齐
candidates/ / sampled/ / reports/     候选、拒绝/抽样结果、验收
release/production_available_v10/     冻结 L1–L3
l4/v3_3/release/                      冻结 L4、输入、gold、test slices
```

### 10.2 实验室存储中的内部评测包

长期内部目录：

```text
artifacts/
  benchmark/l1_l3/release/       L1–L3 陈述与 UNKNOWN
  benchmark/l1_l3/evaluation/    媒体解析后的输入清单
  benchmark/l4/release/          L4 blind inputs 与 gold
  media/                        题目引用的内部媒体副本
  upstream_media/               后续补齐的上游媒体
  software/                     复现代码
  documentation/                文档
  model_results/                后续模型结果，不是新 benchmark gold
```

模型评测应使用相应冻结 run 的请求清单和媒体映射。顶层旧 `README`、旧 bundle config 中的缺失数量可能停留在早期快照，不应替代后续补齐清单或已冻结 E0 输入。

公开发布采用 **source-reference + local generation**：提供源 ID、revision、hash、派生陈述、证明及本地重建脚本；终端用户自行获取上游数据。内部含媒体的文件夹不能直接作为公开可再分发包。这是当前工程发布策略，不是本文新作出的许可授权判断。

## 11. 写论文时应主动说明的边界

1. **数量与最初配额不同。** 原始指南希望四层分配 2,000/2,000/3,500/2,500 pairs；最终为 7,559/1,212/1,041/1,136。总量超过 10,000 不等于原始逐层计划完成。
2. **覆盖不均衡。** 当前 L1–L3 主要由空间关系和类别绑定构成；不是所有五类 track、所有模态都完整覆盖。该版本模态计数为 single image 3,175、multi-view images 6,184、continuous video 453 pairs。
3. **原计划与实际筛选有偏离。** 例如 registry 曾设 OmniSpatial 500-pair 上限，但当前 release 为 1,108；不能宣称所有初始来源配额均被严格遵守。
4. **L4 是混合来源。** Native 与 Controlled 分开报，Calibration 与 Core 分开报；不是所有样本都是强 PRE+action 联合推理，也不是所有题都具备同等视觉证据强度。
5. **不同 split 的底层场景重叠。** 具体数量和处理边界见第 9.3 节。
6. **自动验证有边界。** graph/text/proof 一致性不等于人工视觉证据充分性，不能声称没有自然语言模板偏差或上游标注误差。
7. **原 benchmark 与后续诊断实验分开。** 后续多步 action、oracle/sham、state lookup、符号程序和内部干预请求是研究实验派生集，不计入这里的 24,196 条原 benchmark 输入；其生成协议应放在 Experiment/Diagnostics 小节。

另有一处文档遗留：`production_available_v10/DATASET_CARD.md` 模板文字仍提到 UNKNOWN 未达到 2,000，但该版本 manifest 与审计已确认 2,000。论文应使用机器可核查数量，不照抄过时概述。本次未覆盖修改该历史 card。

## 12. 可用于论文正文的表述草稿

### 12.1 中文

我们构建 SpaceConflict，以检验多模态模型能否在指定对象、视角、时间和状态上下文中判断空间陈述的一致性。该基准复用 CA-VQA、SPAR、OmniSpatial、VSI-Bench、STI-Bench 和 Hypo3D 等来源的媒体与标注，而非直接拼接其原始问答。我们通过来源专属的确定性适配器，将可明确重建的标注转为具有实体、参考系、作用范围和来源记录的部分世界事实；随后从证据子图产生受支持命题，并通过受约束的语义编辑构造可被同一证据反驳的命题。英文题面在命题确定后实现，并经过图文往返及程序验证。证据不足样本单独标记为 UNKNOWN，通过可用证据下真、假两种可行补全刻画其不可判定性。

SpaceConflict 按证据结构组织为原子、组合、跨视图/时间和干预四个层级。L4 进一步区分源数据原生变化与在来源支持初态上定义的受控变化；受控变化由分离实现的转移程序交叉检查，而不依赖被测模型产生真值。冻结组合版本包含 10,948 对 S/C 陈述和 2,300 条 UNKNOWN，共 24,196 条输入，覆盖 4,284 个归并后的底层 world。我们同时公开版本、来源、构造与验收记录，并报告层级不均衡、calibration 样本和自动验证边界。

划分限制应一并保留：构造时按来源 world ID 划分，但跨来源归并后有 123 个底层 world 跨越历史 split。因此全量结果作为 all-split 描述性评测报告，不将当前合并划分宣称为完全场景隔离的泛化测试。

### 12.2 English draft

We construct SpaceConflict to evaluate the consistency of spatial claims under explicit entity, view, temporal, and state contexts. Rather than concatenating existing VQA questions, we reuse source media and annotations from CA-VQA, SPAR, OmniSpatial, VSI-Bench, STI-Bench, and Hypo3D. Source-specific deterministic adapters convert reconstructable annotations into provenance-linked facts in partial world graphs. We derive supported claims from evidence subgraphs and apply typed semantic edits to obtain claims that are explicitly refuted under the same context. English realizations are generated after the structured claims are fixed and are checked through graph–text–graph consistency and programmatic verification. A separate UNKNOWN component represents insufficient evidence, with recorded completions under which the claim is respectively true and false.

The benchmark covers atomic, compositional, cross-view/temporal, and intervention-conditioned conflicts. Its intervention component distinguishes source-native changes from benchmark-controlled changes over source-grounded initial facts; controlled transitions are cross-checked by separately implemented programs. The frozen composite contains 10,948 supported–contradictory pairs and 2,300 UNKNOWN claims, yielding 24,196 inputs across 4,284 normalized underlying worlds. We report the non-uniform level distribution, distinguish core from calibration examples, and retain provenance and construction records. Historical splits are disjoint by registered world ID, but cross-source normalization reveals 123 underlying worlds spanning multiple splits; consequently, all-split evaluation is descriptive and is not presented as a strictly scene-disjoint generalization test.

## 13. 证据索引与复核方式

以下路径中，`P` 指 SpaceConflict 项目根目录，`R` 指 `artifacts/model_results/spatial_world_state/sws_20260909_v1`。

| 证据 | 文件 |
|---|---|
| 总体构建规范、来源注册 | `P/PROJECT_SPEC.md`、`P/datasets.yaml` |
| 来源适配规则 | `P/contracts/` 下各来源版本化 YAML |
| L1–L3 实际配置 | `P/configs/production_available_v10.yaml` |
| L1–L3 最终规模、分布与配额 | `P/release/production_available_v10/manifest.json`、`P/reports/quota.quota_production_available_v10.seed_20260826.json` |
| L1–L3 验收与追溯链 | `P/reports/release_audit.production_available_v10.json`、`P/reports/replay_chain_audit.production_available_v10.json` |
| L4 构建语义与规模 | `P/contracts/l4_three_part_v3.yaml`、`P/l4/v3_3/release/manifest.json`、`P/l4/v3_3/release/L4_THREE_PART_REPORT_CN.md` |
| L4 媒体、UNKNOWN 和 schema 审计 | `P/reports/hypo3d_l4_v3/final_audit.v3_3.json` |
| L1–L3 实际生成实现 | `P/src/spaceconflict/generation/{claims,language,verification}.py` |
| L4 实际生成实现 | `P/src/spaceconflict/l4_three_part/{native,controlled,engine_a,checker_b,unknown}.py` |
| 几何派生边界 | `P/src/spaceconflict/hypo3d_l4/geometry_relations.py` |
| 归并 world 元数据 | `R/repairs/world_identity_v2/baseline_world_metadata.jsonl`、同目录 `identity_acceptance.json` |
| E0 冻结数量 | `R/e0_refresh_20260910_v3_1/acceptance.json` |

本次第 9.3 节使用的元数据文件 SHA-256：

```text
86126a07094253fc07982c6dcdb21274a1a41348ecd9ae0f6cd8249744984694
```

轻量复核命令（只读元数据，不运行模型）：

```bash
jq -s '{
  inputs: length,
  release_world_ids: ([.[].global_world_id] | unique | length),
  underlying_worlds: ([.[].world_cluster_id] | unique | length),
  release_world_cross_split: (
    group_by(.global_world_id)
    | map(select(([.[].split] | unique | length) > 1)) | length),
  underlying_world_cross_split: (
    group_by(.world_cluster_id)
    | map(select(([.[].split] | unique | length) > 1)) | length)
}' artifacts/model_results/spatial_world_state/sws_20260909_v1/repairs/world_identity_v2/baseline_world_metadata.jsonl
```

返回关键值为 `24196 / 4484 / 4284 / 0 / 123`。这是历史冻结材料的统计澄清，不是新增或删改 benchmark 样本。
