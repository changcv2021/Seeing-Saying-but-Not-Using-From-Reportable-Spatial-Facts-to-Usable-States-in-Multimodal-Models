# pss_full_l4_preserved：只添加、不替换 L4 exposure

用户要求日期：2026-09-23。新代码和输出独立，不改原 `formal_training_v4`、`pss_l4`、`pss_full`、release、gold、raw 或 `label_rescore_v2`。

## 实验定义

1. 从旧 PSS-L4 每个 seed 的实际日志重放 2,237 updates × 16 个 primary units。保留全部原始 answer/state 序列、样本/辅助 key、每条 loss 权重和原 batch 内顺序。
2. 从相同 seed 旧 Full PSS 的已冻结、实际运行序列提取所有 level 为 L1/L3 的状态辅助 occurrence。连同其同 world 原答案形成新增单位，answer/state 各 0.5，沿用旧 loss 定义。**不额外加入 L2 状态题，也不替换任何 L4 occurrence。**
3. 新增单位按 16 个一批，最后不足一批只循环补入新增流最前面的 L1/L3 单位（最多 15 个），完整记录。旧 L4 流完全不补、不删。按固定 floor-ratio 将额外批次均匀插入旧批次；无模型表现或 test 参与。
4. 新总步数 = 2,237 + ceil(额外单位数 / 16)。旧每条 L4 状态监督的次数、loss-weight exposure 均须逐 key 相等；S0/S1/S2、grounded/trajectory-history 分开统计。
5. 相同 Qwen3.5-9B backbone、初始权重、LoRA r16/alpha32/dropout0.05、AdamW 2e-5、weight decay0.01、clip1.0、effective batch16、双卡 DDP、micro batch2/rank、原 canonical state serialization 和 per-primary-unit mean loss。3% ceil warmup 与 linear decay 按新总步数重算。不使用旧已训练 adapter 初始化。
6. Train/dev/test 仍为 approved_v2，逐 world/source alias/exact-media 核对。test 固定 5,608 条。最后固定 checkpoint，不按结果挑 seed、checkpoint、prompt 或 parser。

## 解释边界

- `L1/L3 alignment` 指旧 Full PSS 的 canonical state 辅助题，并不是新建 contrastive loss；其中 L1 不一定是多视图任务。
- 新增单位必须保持旧 answer/state loss 定义，因此还带来额外答案 exposure 和更长计算。结果能检验此“添加方案”，不能单独排除训练长度、额外答案以及不同 LR 时间位置的贡献。
- 保持 L4 的绝对次数与单次 loss 权重，不声称其在全部训练中所占比例相同，也不声称旧/new 梯度轨迹完全一样。
- 输入 tokens 从同 key 的旧实际 processor 回执精确汇总；新训练每条再次核对实际 tensor/媒体 hash、target token IDs。non-padding = prompt/input + target，不含 padding。

## 执行及保护

持久根目录：

`artifacts/model_results/pss_20260922_v1/approved_v2/pss_full_l4_preserved_v1/`

- `audit/DATASET_EXPOSURE_AUDIT_CN.md`、`audit/EXPOSURE_AUDIT.json`：训练前审计，全部监督类型唯一数/次数/权重/tokens/epoch-equivalent。
- `audit/units_<seed>.json`：完整冻结顺序；`processor_receipts.json`：与历史实际输入一致性证据。
- `seed_<seed>/PLAN.json`、`runs/pss_full_l4_preserved__seed_<seed>/`：训练配置、日志和新检查点。
- `seed_<seed>/GPU_ACCEPTANCE.json`：同 seed 两次真实工程 update，第二次新进程恢复；不是方法结果。
- `seed_<seed>/ACTUAL_EXPOSURE_CONFIRMED.json`：训练完成后逐 key/权重/token 验证；没有该回执不释放 test。
- `evaluation/seed_<seed>/`：各 seed 独立四个单卡 test 分片，沿用旧 inference wrapper；不等另一 seed 完成。
- `evaluation/seed_<seed>/label_rescore_v2/`：直接调用原 v2 score 函数，只替换输入/输出位置；原 parser/metrics 不变。
- `final_report/REPORT_CN.md`、`ALL_MODEL_LEVEL_SCORES.csv`、`SUMMARY.json`：两个 seed 完成后生成，与 Base / Balanced / PSS-L4 / 旧 Full PSS 并列，包含均值/SD及分层、分标签下降位置。

资源：CPU audit general / YOUR_ACCOUNT / allocated，4 CPU、32G、1h、0 GPU；冻结/训练后审核/评分 general 2 CPU、16G、1h。每 seed 独立 2 GPU、8 CPU、128G，gpu / YOUR_ACCOUNT / allocated，48h 单次分配；没有额外实验总时长上限。每 seed test 四个独立 1 GPU / 4 CPU / 64G / 48h 分片。GPU 均合并项目当前避让列表。

只在正常分配边界且已有完整检查点时续提训练；错误、取消不盲目重试。两个 seed 不设串行屏障；训练完成的 seed 自动进入实际 exposure 审核、test、固定评分。所有提交保留 intent/receipt；提交成功不等于完成。

## 工程记录

首次 CPU audit `8322512` 在读取某些 trajectory 内层 public request 时发现没有 `split` 键而停止；未创建审计结果、更未训练。它们的外层监督记录有 `split=train` 和 underlying world。新核验遵循已冻结外层 split + canonical alias map，并检查媒体不属于 dev/test；内层若有 split 必须仍为 train，缺失数显式记录。没有修改任何源数据，也没有绕过 world 隔离。修正后 CPU audit：`8322624`。

复现必须使用新的独立输出版本；不要重复运行已完成目录。冻结文件以 `FREEZE.json` 与 `source_snapshot/` 为准。
