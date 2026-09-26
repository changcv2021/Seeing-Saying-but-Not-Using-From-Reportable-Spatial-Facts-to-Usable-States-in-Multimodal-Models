# Preserved-L4：训练前数据与实际 exposure 审计

状态：PASS。原 PSS-L4 与 Full PSS 的两个 rank 日志已逐样本重放核对；不是仅比较配置。

新实验保留每个原始 PSS-L4 batch、样本顺序、每条 L4 状态题次数和 loss 权重。额外批次复用旧 Full PSS 实际抽中的 L1/L3 状态题及同 world 答案，answer/state 各 0.5。只为新批次补齐最多 15 个额外 L1/L3 单位，不改 L4。

| 配置 | seed | 更新步数 | primary units | input tokens | target tokens | non-padding tokens | primary epoch-equivalent |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| pss_l4 | 20260922 | 2237 | 35792 | 77589670 | 518265 | 78107935 | 2.6560 |
| pss_full | 20260922 | 2237 | 35792 | 109185771 | 2033955 | 111219726 | 2.6560 |
| pss_full_l4_preserved | 20260922 | 3352 | 53632 | 132718094 | 1449413 | 134167507 | 3.9798 |
| pss_l4 | 20260923 | 2237 | 35792 | 77610243 | 518076 | 78128319 | 2.6560 |
| pss_full | 20260923 | 2237 | 35792 | 109230722 | 2029968 | 111260690 | 2.6560 |
| pss_full_l4_preserved | 20260923 | 3358 | 53728 | 132959235 | 1454191 | 134413426 | 3.9869 |

所有配置 effective batch = 16 原始样本单位；2 ranks；micro batch 每 rank 2 条序列；按每 rank 8 个单位累积，实际 4–8 个 micro-batches。input tokens 含实际处理后的视觉 token，但不含 target；non-padding = input + target。

## pss_l4__seed_20260922

| 监督类型 | pool 唯一数 | 实际唯一数 | 实际 exposures | loss-weight exposures | input tokens | target tokens | non-padding tokens | pool epoch-equivalent |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ANSWER_L1 | 10072 | 5643 | 8948 | 8640.5 | 12810708 | 67131 | 12877839 | 0.8884 |
| ANSWER_L2 | 1176 | 1176 | 8948 | 8367.0 | 8573951 | 67035 | 8640986 | 7.6088 |
| ANSWER_L3 | 1188 | 1181 | 8948 | 8791.5 | 15417855 | 67089 | 15484944 | 7.5320 |
| ANSWER_L4 | 1040 | 1040 | 8948 | 5614.0 | 20247146 | 65288 | 20312434 | 8.6038 |
| L4_GROUNDED_STATE_S0 | 386 | 379 | 3514 | 1757.0 | 8187733 | 100177 | 8287910 | 9.1036 |
| L4_GROUNDED_STATE_S1 | 550 | 540 | 4857 | 2428.5 | 11407387 | 137700 | 11545087 | 8.8309 |
| L4_TRAJECTORY_HISTORY_S0 | 68 | 57 | 102 | 51.0 | 243984 | 3656 | 247640 | 1.5000 |
| L4_TRAJECTORY_HISTORY_S1 | 68 | 57 | 100 | 50.0 | 243923 | 3576 | 247499 | 1.4706 |
| L4_TRAJECTORY_HISTORY_S2 | 136 | 107 | 185 | 92.5 | 456983 | 6613 | 463596 | 1.3603 |

## pss_full__seed_20260922

| 监督类型 | pool 唯一数 | 实际唯一数 | 实际 exposures | loss-weight exposures | input tokens | target tokens | non-padding tokens | pool epoch-equivalent |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ANSWER_L1 | 10072 | 5643 | 8948 | 4474.0 | 12810708 | 67131 | 12877839 | 0.8884 |
| ANSWER_L2 | 1176 | 1176 | 8948 | 4474.0 | 8573951 | 67035 | 8640986 | 7.6088 |
| ANSWER_L3 | 1188 | 1181 | 8948 | 4474.0 | 15417855 | 67089 | 15484944 | 7.5320 |
| ANSWER_L4 | 1040 | 1040 | 8948 | 5557.0 | 20247146 | 65288 | 20312434 | 8.6038 |
| L1_GROUNDED_STATE_OBSERVED | 7288 | 3442 | 9758 | 4879.0 | 13486403 | 426563 | 13912966 | 1.3389 |
| L2_GROUNDED_STATE_OBSERVED | 1591 | 1558 | 9287 | 4643.5 | 9593603 | 782832 | 10376435 | 5.8372 |
| L3_GROUNDED_STATE_OBSERVED | 540 | 536 | 8082 | 4041.0 | 13839685 | 370915 | 14210600 | 14.9667 |
| L4_GROUNDED_STATE_S0 | 386 | 380 | 2773 | 1386.5 | 6457475 | 79676 | 6537151 | 7.1839 |
| L4_GROUNDED_STATE_S1 | 550 | 536 | 3674 | 1837.0 | 8631938 | 105567 | 8737505 | 6.6800 |
| L4_TRAJECTORY_HISTORY_S0 | 68 | 14 | 14 | 7.0 | 33485 | 499 | 33984 | 0.2059 |
| L4_TRAJECTORY_HISTORY_S1 | 68 | 11 | 11 | 5.5 | 26839 | 395 | 27234 | 0.1618 |
| L4_TRAJECTORY_HISTORY_S2 | 136 | 25 | 27 | 13.5 | 66683 | 965 | 67648 | 0.1985 |

## pss_full_l4_preserved__seed_20260922

| 监督类型 | pool 唯一数 | 实际唯一数 | 实际 exposures | loss-weight exposures | input tokens | target tokens | non-padding tokens | pool epoch-equivalent |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ANSWER_L1 | 10072 | 5643 | 17221 | 12777.0 | 25006003 | 129168 | 25135171 | 1.7098 |
| ANSWER_L2 | 1176 | 1176 | 10090 | 8938.0 | 9751714 | 75543 | 9827257 | 8.5799 |
| ANSWER_L3 | 1188 | 1181 | 16839 | 12737.0 | 28654249 | 126312 | 28780561 | 14.1742 |
| ANSWER_L4 | 1040 | 1040 | 9482 | 5881.0 | 21440030 | 69190 | 21509220 | 9.1173 |
| L1_GROUNDED_STATE_OBSERVED | 7288 | 3442 | 9758 | 4879.0 | 13486403 | 426563 | 13912966 | 1.3389 |
| L3_GROUNDED_STATE_OBSERVED | 540 | 536 | 8082 | 4041.0 | 13839685 | 370915 | 14210600 | 14.9667 |
| L4_GROUNDED_STATE_S0 | 386 | 379 | 3514 | 1757.0 | 8187733 | 100177 | 8287910 | 9.1036 |
| L4_GROUNDED_STATE_S1 | 550 | 540 | 4857 | 2428.5 | 11407387 | 137700 | 11545087 | 8.8309 |
| L4_TRAJECTORY_HISTORY_S0 | 68 | 57 | 102 | 51.0 | 243984 | 3656 | 247640 | 1.5000 |
| L4_TRAJECTORY_HISTORY_S1 | 68 | 57 | 100 | 50.0 | 243923 | 3576 | 247499 | 1.4706 |
| L4_TRAJECTORY_HISTORY_S2 | 136 | 107 | 185 | 92.5 | 456983 | 6613 | 463596 | 1.3603 |

L4 保留验证：`PASS_EXACT_PER_KEY_COUNTS_AND_WEIGHTS`；S0/S1/S2 原值与新值：`{"S0": 3616, "S1": 4957, "S2": 185}` / `{"S0": 3616, "S1": 4957, "S2": 185}`。
新增 L1/L3 exposures：`{"L1": 9758, "L3": 8082}`；warmup steps：101。

## pss_l4__seed_20260923

| 监督类型 | pool 唯一数 | 实际唯一数 | 实际 exposures | loss-weight exposures | input tokens | target tokens | non-padding tokens | pool epoch-equivalent |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ANSWER_L1 | 10072 | 5636 | 8948 | 8641.5 | 12816428 | 67059 | 12883487 | 0.8884 |
| ANSWER_L2 | 1176 | 1176 | 8948 | 8364.0 | 8573932 | 67107 | 8641039 | 7.6088 |
| ANSWER_L3 | 1188 | 1184 | 8948 | 8790.5 | 15418147 | 67098 | 15485245 | 7.5320 |
| ANSWER_L4 | 1040 | 1040 | 8948 | 5614.0 | 20247210 | 65276 | 20312486 | 8.6038 |
| L4_GROUNDED_STATE_S0 | 386 | 382 | 3541 | 1770.5 | 8248697 | 100716 | 8349413 | 9.1736 |
| L4_GROUNDED_STATE_S1 | 550 | 544 | 4835 | 2417.5 | 11357822 | 136938 | 11494760 | 8.7909 |
| L4_TRAJECTORY_HISTORY_S0 | 68 | 53 | 97 | 48.5 | 232022 | 3476 | 235498 | 1.4265 |
| L4_TRAJECTORY_HISTORY_S1 | 68 | 53 | 92 | 46.0 | 224389 | 3294 | 227683 | 1.3529 |
| L4_TRAJECTORY_HISTORY_S2 | 136 | 117 | 199 | 99.5 | 491596 | 7112 | 498708 | 1.4632 |

## pss_full__seed_20260923

| 监督类型 | pool 唯一数 | 实际唯一数 | 实际 exposures | loss-weight exposures | input tokens | target tokens | non-padding tokens | pool epoch-equivalent |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ANSWER_L1 | 10072 | 5636 | 8948 | 4474.0 | 12816428 | 67059 | 12883487 | 0.8884 |
| ANSWER_L2 | 1176 | 1176 | 8948 | 4474.0 | 8573932 | 67107 | 8641039 | 7.6088 |
| ANSWER_L3 | 1188 | 1184 | 8948 | 4474.0 | 15418147 | 67098 | 15485245 | 7.5320 |
| ANSWER_L4 | 1040 | 1040 | 8948 | 5557.0 | 20247210 | 65276 | 20312486 | 8.6038 |
| L1_GROUNDED_STATE_OBSERVED | 7288 | 3461 | 9833 | 4916.5 | 13569392 | 429976 | 13999368 | 1.3492 |
| L2_GROUNDED_STATE_OBSERVED | 1591 | 1556 | 9195 | 4597.5 | 9530073 | 774671 | 10304744 | 5.7794 |
| L3_GROUNDED_STATE_OBSERVED | 540 | 536 | 8097 | 4048.5 | 13853965 | 371516 | 14225481 | 14.9944 |
| L4_GROUNDED_STATE_S0 | 386 | 377 | 2715 | 1357.5 | 6322184 | 78481 | 6400665 | 7.0337 |
| L4_GROUNDED_STATE_S1 | 550 | 540 | 3746 | 1873.0 | 8801828 | 107359 | 8909187 | 6.8109 |
| L4_TRAJECTORY_HISTORY_S0 | 68 | 12 | 13 | 6.5 | 31091 | 463 | 31554 | 0.1912 |
| L4_TRAJECTORY_HISTORY_S1 | 68 | 8 | 8 | 4.0 | 19523 | 287 | 19810 | 0.1176 |
| L4_TRAJECTORY_HISTORY_S2 | 136 | 19 | 19 | 9.5 | 46949 | 675 | 47624 | 0.1397 |

## pss_full_l4_preserved__seed_20260923

| 监督类型 | pool 唯一数 | 实际唯一数 | 实际 exposures | loss-weight exposures | input tokens | target tokens | non-padding tokens | pool epoch-equivalent |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ANSWER_L1 | 10072 | 5636 | 17234 | 12784.5 | 25050905 | 129168 | 25180073 | 1.7111 |
| ANSWER_L2 | 1176 | 1176 | 10147 | 8963.5 | 9755515 | 76116 | 9831631 | 8.6284 |
| ANSWER_L3 | 1188 | 1184 | 16858 | 12745.5 | 28705810 | 126420 | 28832230 | 14.1902 |
| ANSWER_L4 | 1040 | 1040 | 9489 | 5884.5 | 21461262 | 69186 | 21530448 | 9.1240 |
| L1_GROUNDED_STATE_OBSERVED | 7288 | 3461 | 9837 | 4918.5 | 13574058 | 430157 | 14004215 | 1.3498 |
| L3_GROUNDED_STATE_OBSERVED | 540 | 536 | 8099 | 4049.5 | 13857159 | 371608 | 14228767 | 14.9981 |
| L4_GROUNDED_STATE_S0 | 386 | 382 | 3541 | 1770.5 | 8248697 | 100716 | 8349413 | 9.1736 |
| L4_GROUNDED_STATE_S1 | 550 | 544 | 4835 | 2417.5 | 11357822 | 136938 | 11494760 | 8.7909 |
| L4_TRAJECTORY_HISTORY_S0 | 68 | 53 | 97 | 48.5 | 232022 | 3476 | 235498 | 1.4265 |
| L4_TRAJECTORY_HISTORY_S1 | 68 | 53 | 92 | 46.0 | 224389 | 3294 | 227683 | 1.3529 |
| L4_TRAJECTORY_HISTORY_S2 | 136 | 117 | 199 | 99.5 | 491596 | 7112 | 498708 | 1.4632 |

L4 保留验证：`PASS_EXACT_PER_KEY_COUNTS_AND_WEIGHTS`；S0/S1/S2 原值与新值：`{"S0": 3638, "S1": 4927, "S2": 199}` / `{"S0": 3638, "S1": 4927, "S2": 199}`。
新增 L1/L3 exposures：`{"L1": 9837, "L3": 8099}`；warmup steps：101。

## 解释边界

L1/L3 alignment 指复用原 Full PSS 的 canonical state 辅助监督，不新增 contrastive loss，也不把所有 L1 单视图题伪称多视图题。新增单位同时包含原定义的答案监督；更长训练和额外答案 exposure 是本实验的伴随变化，不能仅据性能差异排除其贡献。

沿用 approved_v2 的 source/physical-space/exact-media alias 隔离；train/dev/test = 13,476 / 3,267 / 5,608，test 原文件 hash 未变。未获得官方 physical identity 的来源仍保留原审计限制。

完整逐 key 曝光在 EXPOSURE_AUDIT.json；冻结顺序在 units_<seed>.json；历史实际 processor token/hash 回执在 processor_receipts.json。所有旧数据只读。
