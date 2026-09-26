# Phase8 v4：按 updates / 有效 batch 对齐、双卡加速

2026-09-22 用户明确覆盖旧 supervised-token 等量预算。只保留现有五方案 × 两 seeds，不新增误写的 Step-SFT 或第六种方法。

## 旧任务和检查点

现场核查：8312729_0–9 全部已于 17:10:24 CANCELLED，旧运行时长 36:21，不存在仍需取消的活跃旧训练项。保留 `formal_training_v1/` 全部数据、日志和 checkpoints；不删除或覆盖。

旧最近 committed checkpoint：Natural 两 seeds 各 step 2；Balanced 两 seeds 各 step 2；CoT step 24 / 23；PSS-L4 step 9 / 5；Full PSS step 14 / 14。它们是旧 token 预算的部分结果，不能当作新预算结果。

新运行从同一 Qwen3.5-9B base 初始化，不加载这些旧部分训练 adapter/optimizer。否则不均衡的旧训练历史会污染新比较。原 checkpoint 仍可供追溯或独立复现旧分支。

## 五方法共同设置

| 设置 | 新规则 |
| --- | --- |
| 方法 | Answer Natural、Answer Balanced、Partial CoT、PSS-L4、Full PSS |
| Seeds | 20260922、20260923，分别报告 |
| 原始训练池 | 同一 13,476 条，原 world split 不变 |
| 更新步数 | 每项 2,237 |
| Effective batch | 每次更新 16 条原始样本，2 ranks × 每 rank 8 条 |
| Micro batch | 每 rank 每次 forward 最多 2 条序列；按权重梯度累计 |
| 原始样本曝光次数 | 每项 35,792 次，不依据 target 长度重复采样 |
| 采样 | Balanced / CoT / 两 PSS 同 seed 逐位置相同的 level → world → sample；Natural 保留原样本频率对照 |
| LoRA | language attention only，r16 / alpha32 / dropout0.05，BF16 |
| Optimizer / LR | AdamW，2e-5，weight decay0.01，clip1.0，3% warmup + linear decay |
| 终点 | 固定最终 step；不按 dev/test 分数挑 seed 或 checkpoint |
| 不再匹配 | supervised output tokens、总输入 tokens、forward 序列数、FLOPs、wall time；逐项实测和报告 |

**有效 batch 的单位是原始样本，不是辅助 forward 序列。** Natural / Balanced 每单位一个原 answer；CoT 使用同题已有 rationale+answer target（288 条获批 fallback 保持 answer-only）；PSS 每单位原 answer + 一个同 underlying world 的已有 state 辅助 query。PSS 无可用 state 则仅答案，不跨 world 凑数，不造新 gold。

每个原始单位总权重为 1。有辅助时 answer/state 各 0.5；每条序列先按其有效 target tokens 求均值，再按原始单位求均值。state query 保留已审核的原公开媒体上下文与 state_interface_v2，不把不同假设操作的 state 错接到原问题上。PSS 比答案基线有更多辅助 forward/监督，是方法差异，不能声称 total compute / information matched，也不能仅用这轮比较排除“更多监督信息”的竞争解释。

可用 pool 相同不代表所有样本都在固定世界均衡预算内曝光。实际 unique samples/worlds、level counts、总 target tokens 及共享流 SHA 在 `PLAN.json.expected_exposure`。实际采样不看模型错误或 test。

## 双卡和流水线

- PyTorch DDP，同一节点两张 A100，各进程独占一张分配内 GPU；共同梯度更新，不是两份无关联训练。
- 每 rank 两个 spawned CPU worker；图像读取、processor、原输入张量 hash 在后台完成，prefetch_factor=2，pinned memory，非阻塞 GPU 传输。
- 每 worker 有界 512 MiB CPU LRU，缓存已经处理并带 hash 回执的输入；不每次在 GPU 主线程重复读图/编码/做哈希。
- 图像分辨率、原问题和 gold 不改。左 padding，监督 mask 只覆盖原 target，不对 padding 或 prompt 求 loss；媒体按批内样本顺序拼接。
- 开启 Flash / memory-efficient / cuDNN SDPA，由实际模型和 tensor shape 选择；保留 math 作为不支持情形的 fallback，**不强制 math**。开启 TF32，关闭强制 deterministic algorithms。
- 冒烟记录实际 profiler attention operators，不仅查看 enable 开关。快速后端不再要求跨独立训练过程逐位相同。

参考当前安装版的 [PyTorch 2.8 DDP 文档](https://docs.pytorch.org/docs/2.8/generated/torch.nn.parallel.DistributedDataParallel.html) 和 [SDPA 文档](https://docs.pytorch.org/docs/2.8/generated/torch.nn.functional.scaled_dot_product_attention.html)。本项目可否实际运行以 GPU_ACCEPTANCE 为准。

## 恢复与资源

新 checkpoint 原子存档 adapter、两个 rank 各自 optimizer/scheduler/RNG、global step 与计数。数据顺序由 step 和 seed 随机访问，不依赖预取推进到哪里。真实新进程立即加载后检查 serialized weights / optimizer / scheduler / RNG 一致，并继续下一步；不把快速 kernel 的微小数值差异当作必须禁用加速的理由。

每项正式 2 GPU / 8 CPU / 128 GiB / 单次 48h，gpu / YOUR_ACCOUNT / allocated。数组 0–9 无限流、无项间依赖，沿用坏卡避让列表。没有总体 walltime 封顶。分配结束前同步保存并仅续提未完成项；取消、OOM、其他异常不盲目重试。正式任务可同时排队，但两张卡需在同一节点可用。

## 本轮提交

- CPU 8312914：单元测试 + 冻结 train catalog / 新曝光计划，4 CPU / 16 GiB / 45min。
- GPU 8312915：仅依赖 CPU 成功，实际两卡五方法 ingress、两个 fresh-process restore，2 GPU / 8 CPU / 128 GiB / 1h。
- CPU **8312979**：1 CPU / 2 GiB / 15min，afterany:8312915；全部通过即直接提交十项正式数组。只有分配边界导致未完成检查时，才正常申请 2 GPU / 8 CPU / 128 GiB / 2h 的新分配继续剩余固定工程 case。代码/GPU 异常不会盲目重试。

Slurm 拒绝将已运行的 8312915 从 1h 延长到 2h，实际时限未变，没有绕过控制。8312916、预先排队但不一定需要的 8312969/8312973 均在未运行时取消，以条件式 CPU router 取代，避免已验收后还等待无用 GPU。完整调度记录为 `UPDATE_MATCHED_V4_VALIDATION_ROUTING.json`。

前置提交不等于正式十项已经提交。正式数组以新输出目录 `SUBMITTED.json` 为准；训练完成须有各 run 的 `TRAINING_COMPLETE.json`，不能把工程 smoke 当方法分数。

实际进度：8312914 已 COMPLETED（37 秒），8 项单元测试通过，新预算冻结。8312915 已分配 nid0643 两 GPU 并开始。计划实际覆盖所有 **2,221 train worlds**；Natural 每 seed 曝光 13,476 个不同原始样本；四种共享 balanced 流曝光 9,040 / 9,036 个不同样本（可用池仍为同一 13,476）。每方法都是 35,792 个 primary units。第一 seed 的 supervised tokens 为 Natural 267,536、Balanced 266,543、CoT 1,807,159、PSS-L4 518,265、Full PSS 2,033,955；只报告，不强行相等。

已实际完成的初轮更新：Natural 27.36s、Balanced 22.95s、CoT 22.25s（不含新进程/worker 初始化与 profiler 汇总）。Natural 峰值两卡分别 24.32 / 21.86 GiB。profiler 记录实际 `aten::_scaled_dot_product_flash_attention` 与 `aten::_scaled_dot_product_efficient_attention`，两 ranks 更新后 adapter hash 相同。其余 PSS 和恢复 case 仍待结束，不能据前三项宣称所有方法验收完成；上述单步也不是正式长跑吞吐估计。

17:51 EDT 更新：PSS-L4 初轮也已完成，更新阶段 28.73s，16 个 primary units、247 个实际监督 tokens，双 rank COMPLETE、加速 attention、同步 adapter hash 均通过。当前四方法完成，Full PSS 正在执行，两个 fresh-process resume 尚未全部验证。正式十项仍以 SUBMITTED.json 为准，不能把此时的工程验证作业等同于已开始全量训练。

持久输出：

`artifacts/model_results/pss_20260922_v1/approved_v2/formal_training_v4/`

新代码 hash、脚本、数据来源、PLAN 均冻结；source_snapshot 保存实际代码副本。修复需要新版本，原件保留。原 release、gold、test、旧预测、旧训练检查点均未修改。

训练后主评测仍为完整 held-out test 5,608 条；不会运行 train+dev+test 混合结果冒充泛化成绩。当前新版训练器只到训练产物，未宣称训练后评测已完成或已自动部署。
