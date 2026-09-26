# SFT 前后 Known accuracy / UNKNOWN recall 核对

日期：2026-09-25。仅汇总既有结果；未重新推理、训练、修改预测、gold 或评分规则。

## 1. 结论

- **Known 准确率没有下降；下降的是 UNKNOWN recall。** 相对 Base，Balanced 和三种 PSS 配置的两 seed 均值在各个 level 上均提高了 Known accuracy。
- 对 L3，Base 的 UNKNOWN recall 为 43.08%（224/520）；Balanced、PSS-L4、旧 Full PSS、新 preserved-L4 Full PSS 的两个 seed 均为 0%（0/520）。下降 **43.08 个百分点**。
- Overall UNKNOWN recall：Base 为 52.42%（1,083/2,066）；Balanced、PSS-L4、新 preserved-L4 Full PSS 均为 3.19%（各 seed 66/2,066），下降 **49.23 个百分点**。旧 Full PSS 的均值为 3.03%，下降 49.39 个百分点。
- 不能笼统写“微调后整体 ClaimAcc 下降”：Balanced、PSS-L4、新 preserved-L4 Full PSS 的 Overall ClaimAcc 分别提高 1.24、1.12、1.75 个百分点。L3 的 ClaimAcc 则全部下降。
- 这是一项分标签的指标分解，尚不能独立解释 UNKNOWN 识别退化的训练原因，也不能将其直接等同于某种内部机制。
- 当前核查未确认论文名 **OSS** 与代码配置的对应关系，下文保留真实配置名，不擅自替换。

## 2. 口径与来源

- Backbone：Qwen3.5-9B；Base 未微调。SFT 使用 seeds 20260922、20260923。
- 同一 approved_v2 held-out test：5,608 inputs、1,124 worlds；不是全 split 的 24,196 inputs。
- 全部采用同一修正后的 label_rescore_v3；汇总状态 COMPLETE，13/13 结果齐全。
- Known accuracy = gold 为 SUPPORTED / CONTRADICTORY 的样本中预测正确比例。预测 UNKNOWN 或无法解析均计错。
- UNKNOWN recall = gold 为 UNKNOWN 的样本中预测正确为 UNKNOWN 的比例。
- PairAcc 仅纳入 component=binary、恰有 SUPPORTED 与 CONTRADICTORY 两条的完整 pair；必须两条均正确。**Known accuracy 不等于 PairAcc。**
- 表中百分比均保留两位小数；微调配置取两 seed 的算术均值。± 为两 seed 的样本标准差，不是置信区间；Base 只有一次评测。
- 原始逐 seed 正确数与各指标见同目录 CSV；它包含全部 13 个已完成模型配置，而正文重点比较用户指定的方法。

来源：[冻结 v3 汇总](artifacts/model_results/pss_20260922_v1/approved_v2/label_rescore_v3/final/SUMMARY.json)。SUMMARY.json SHA256：

`94e17239c71742a75d56ec702191683cb242aeb3e3309d2f5afee2b075b0d644`

评分定义：[common.py](artifacts/model_results/pss_20260922_v1/approved_v2/label_rescore_v3/source_snapshot/read_only_dependencies/common.py:84)。

## 3. 固定分母

| Level | 全部 inputs | Known inputs | UNKNOWN inputs | 完整 binary pairs |
|---|---:|---:|---:|---:|
| L1 | 3654 | 2174 | 1480 | 1087 |
| L2 | 462 | 462 | 0 | 231 |
| L3 | 976 | 456 | 520 | 228 |
| L4 | 516 | 450 | 66 | 225 |
| Overall | 5608 | 3542 | 2066 | 1771 |

L2 无 UNKNOWN，UNKNOWN recall 应写 N/A，不应写 0%。

## Overall：分标签结果

| 方法 | Known accuracy (%) | Δ Known (pp) | UNKNOWN recall (%) | Δ UNKNOWN (pp) | ClaimAcc (%) | PairAcc (%) |
|---|---:|---:|---:|---:|---:|---:|
| Base | 58.92 | — | 52.42 | — | 56.53 | 44.49 |
| Answer-SFT Balanced | 89.60 ± 0.14 | +30.67 | 3.19 ± 0.00 | -49.23 | 57.77 | 84.33 |
| PSS-L4 | 89.41 ± 0.12 | +30.49 | 3.19 ± 0.00 | -49.23 | 57.65 | 84.58 |
| 旧 Full PSS | 87.18 ± 2.87 | +28.26 | 3.03 ± 0.24 | -49.39 | 56.18 | 80.15 |
| 新 Full PSS（preserved-L4） | 90.40 ± 0.04 | +31.48 | 3.19 ± 0.00 | -49.23 | 58.27 | 86.31 |

## L1：分标签结果

| 方法 | Known accuracy (%) | Δ Known (pp) | UNKNOWN recall (%) | Δ UNKNOWN (pp) | ClaimAcc (%) | PairAcc (%) |
|---|---:|---:|---:|---:|---:|---:|
| Base | 51.70 | — | 55.47 | — | 53.23 | 38.91 |
| Answer-SFT Balanced | 88.82 ± 0.07 | +37.12 | 0.00 ± 0.00 | -55.47 | 52.85 | 83.90 |
| PSS-L4 | 88.94 ± 0.10 | +37.24 | 0.00 ± 0.00 | -55.47 | 52.91 | 84.91 |
| 旧 Full PSS | 85.90 ± 3.22 | +34.20 | 0.00 ± 0.00 | -55.47 | 51.11 | 78.84 |
| 新 Full PSS（preserved-L4） | 90.02 ± 0.07 | +38.32 | 0.00 ± 0.00 | -55.47 | 53.56 | 86.52 |

## L2：分标签结果

| 方法 | Known accuracy (%) | Δ Known (pp) | UNKNOWN recall (%) | Δ UNKNOWN (pp) | ClaimAcc (%) | PairAcc (%) |
|---|---:|---:|---:|---:|---:|---:|
| Base | 92.64 | — | — | — | 92.64 | 87.88 |
| Answer-SFT Balanced | 97.51 ± 0.46 | +4.87 | — | — | 97.51 | 96.75 |
| PSS-L4 | 96.86 ± 0.46 | +4.22 | — | — | 96.86 | 95.45 |
| 旧 Full PSS | 96.10 ± 0.00 | +3.46 | — | — | 96.10 | 94.37 |
| 新 Full PSS（preserved-L4） | 96.54 ± 0.61 | +3.90 | — | — | 96.54 | 95.67 |

## L3：分标签结果

| 方法 | Known accuracy (%) | Δ Known (pp) | UNKNOWN recall (%) | Δ UNKNOWN (pp) | ClaimAcc (%) | PairAcc (%) |
|---|---:|---:|---:|---:|---:|---:|
| Base | 54.82 | — | 43.08 | — | 48.57 | 39.91 |
| Answer-SFT Balanced | 96.71 ± 0.00 | +41.89 | 0.00 ± 0.00 | -43.08 | 45.18 | 95.83 |
| PSS-L4 | 96.38 ± 0.78 | +41.56 | 0.00 ± 0.00 | -43.08 | 45.03 | 95.61 |
| 旧 Full PSS | 96.49 ± 0.93 | +41.67 | 0.00 ± 0.00 | -43.08 | 45.08 | 95.18 |
| 新 Full PSS（preserved-L4） | 96.82 ± 0.16 | +42.00 | 0.00 ± 0.00 | -43.08 | 45.24 | 95.83 |

## L4：分标签结果

| 方法 | Known accuracy (%) | Δ Known (pp) | UNKNOWN recall (%) | Δ UNKNOWN (pp) | ClaimAcc (%) | PairAcc (%) |
|---|---:|---:|---:|---:|---:|---:|
| Base | 63.33 | — | 57.58 | — | 62.60 | 31.56 |
| Answer-SFT Balanced | 78.00 ± 0.94 | +14.67 | 100.00 ± 0.00 | +42.42 | 80.81 | 62.00 |
| PSS-L4 | 77.00 ± 0.16 | +13.67 | 100.00 ± 0.00 | +42.42 | 79.94 | 60.67 |
| 旧 Full PSS | 74.78 ± 6.13 | +11.44 | 94.70 ± 7.50 | +37.12 | 77.33 | 56.67 |
| 新 Full PSS（preserved-L4） | 79.44 ± 0.47 | +16.11 | 100.00 ± 0.00 | +42.42 | 82.07 | 66.00 |

## 4. L3 ClaimAcc 下降的精确分解

L3 的 Known 占 456/976 = 46.72%，UNKNOWN 占 520/976 = 53.28%。因此：

`ClaimAcc = (456/976) × Known accuracy + (520/976) × UNKNOWN recall`

| 相对 Base（两 seed 均值） | Known 提升对 ClaimAcc 的贡献 (pp) | UNKNOWN 下降对 ClaimAcc 的贡献 (pp) | ClaimAcc 净变化 (pp) | PairAcc 变化 (pp) |
|---|---:|---:|---:|---:|
| Answer-SFT Balanced | +19.57 | -22.95 | -3.38 | +55.92 |
| PSS-L4 | +19.42 | -22.95 | -3.53 | +55.70 |
| 旧 Full PSS | +19.47 | -22.95 | -3.48 | +55.26 |
| 新 Full PSS（preserved-L4） | +19.62 | -22.95 | -3.33 | +55.92 |

例如 Balanced：Known 正确数由 250/456 提高到两个 seed 均为 441/456，多答对 191 条；UNKNOWN 正确数由 224/520 降到 0/520，少答对 224 条。最终总正确数减少 33 条，即 ClaimAcc 下降 33/976 = 3.38 个百分点。同时，两个 seed 的完整 pair 正确数为 218/228、219/228，明显高于 Base 的 91/228。

新 preserved-L4 Full PSS：Known 正确数分别为 442/456、441/456，UNKNOWN 均为 0/520；L3 ClaimAcc 均值 45.24%，PairAcc 均值 95.83%。不能把 seed 20260922 的 45.29% / 96.05% 当成两 seed 均值。

## 5. 可用于论文的表述

> 在 L3 held-out test 上，Answer-SFT Balanced 的 Known accuracy 从 Base 的 54.82% 提升至 96.71%，但 UNKNOWN recall 从 43.08% 降至 0%。由于 UNKNOWN 占该层输入的 53.28%，其识别损失超过了 Known 样本上的收益，导致 ClaimAcc 从 48.57% 降至 45.18%，而仅对完整二元样本对计算的 PairAcc 从 39.91% 提升至 95.83%（微调结果为两个 seed 的均值）。因此，这一指标分化在统计上对应 UNKNOWN 识别退化，而不是 Known 准确率下降。

若 OSS 最终对应上述任一 PSS 配置，则 **L3** 的 X / Y / Z 可统一填为 **43.08% / 0.00% / 0.00%**。若表格为 **Overall**，X / Y 应为 **52.42% / 3.19%**，Z 在 PSS-L4 或新 preserved-L4 时为 **3.19%**，在旧 Full PSS 时为 **3.03%**。

不要推广成“所有 level 的 UNKNOWN 都退化”：L4 的 UNKNOWN recall 从 Base 的 57.58% 提高到 Balanced、PSS-L4、新 preserved-L4 的 100%；旧 Full PSS 的均值为 94.70%。总体 UNKNOWN 退化集中于 L1 与 L3。

