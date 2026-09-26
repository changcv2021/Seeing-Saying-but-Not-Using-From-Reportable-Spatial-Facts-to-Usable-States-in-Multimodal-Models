# SpaceConflict Paper Evidence Report

单文件论文写作证据报告 / 2026-09-12


用途：可直接上传给 ChatGPT，用于正文、方法、附录和图表写作。本文只整理既有实验，不新增模型推理，不改 prompt、gold、parser、历史评分或冻结判定。E0 使用 2026-09-10 19:50 UTC 冻结快照；I1 使用最终统计 snapshot_8210758。


读表单位：准确率为百分比；两准确率之差（Δ）以百分点 pp 表达，表中乘100显示的百分号差值均指pp而非相对增长率；log-prob差以nats表达。整数比值为实际计数；均值/配对净差的numerator可为和或净事件数，不能解读成全部正确数。

## 1. Executive Summary


核心问题：当 MLLM 能从视觉输入中独立正确报告空间事实时，该事实是否也能成为后续状态转换中可靠使用的操作性状态？本文区分事实可报告性、条件化的组合任务表现和内部因果使用，不把三者视为同义。

**Available spatial fact ≠ operationally usable spatial state.** 这是跨条件行为发现的概括，而不是模型同一次完整推理已正确编码 S0 的证明。核心案例满足 B02=correct、B01=wrong、B05=correct。B02 是独立初值查询，B01 是视觉两步转换，B05 是显式正确 S0 加原媒体。

9B 在 160 个序列/80 个 world 中有 50 个 Type A 序列、37 个 world。4B 和 27B 也存在相应案例，但数量不同。显式初值、纯符号和后缀条件支持任务接口与状态使用之间存在行为差距；不能仅凭 oracle 救援定位到编码、绑定或更新模块。B06 对 9B 仅 104/160，不支持把一切归因为简单缺少 S1。

目标语义控制是必要的竞争解释检查：同一 96 程序/16 家族下，9B/27B 的 S1 由索引问法 0/96 变成三个明确语义问法各 96/96；这限制了把原 B2 异常称为稳定 Wrong-State Selection 的叙述。4B/9B 的其他目标仍有反例。

非计数扩展仅覆盖 47 个 world 的水平、垂直和深度二元坐标反射。9B/27B 的 explicit−sham 配对效应为正，4B 无稳定正效应。不能外推为所有 3D 或 embodied spatial intelligence。

内部分析没有闭合机制故事：R1 未建立稳定超越表面基线的状态读出证据；I2 单-token S1 interchange 为 0/384 CF 命中；I1 两个 LOCALIZE 候选在 SELECT 中主 Type A 救援均 0/17，特异性区间跨零，最终 NO_GO。没有反向破坏也没有正向救援，不足以称选择性修复。I3 和跨规模内部验证按门槛未运行。负结果只限制所测映射、位置和干预方式，不能证明内部无状态，也不能证明机制必然分布式。

最稳妥的论文贡献是：以 world 可追溯的共同面板建立事实可报告与组合转换成功之间的条件化差距；通过目标语义和 matched sham 限制过度解释；完整报告未能验证局部因果接口的机制测试。不要写成已经找到“空间状态电路”。

## 2. Final Research Questions and Claims


RQ1：事实能否独立正确报告？RQ2：可报告事实是否保证组合任务正确？RQ3：显式初值救援是否超过无关信息及符号/后缀控制？RQ4：目标索引失败是否由问法造成？RQ5：行为是否扩展至有限非计数任务？RQ6：固定表示分析和局部因果干预是否给出可重复、选择性的机制证据？

事实正确使用 typed exact match；null/invalid 按原评分保留。历史材料的 LOCALIZE/SELECT/LOCKED_EVAL 与 Phase7 新分区不同，不拼成“从未曝光正式测试集”。研究者豁免审核的记录仍是 HUMAN_REVIEW_WAIVED_BY_RESEARCHER / AUTO_ONLY_PROVISIONAL，不生成新的人工 VERIFIED。

## 3. Dataset and E0 Benchmark


| 范围 | Inputs | Underlying worlds | SUPPORTED | CONTRADICTORY | UNKNOWN | 完整 S/C pairs |
| --- | --- | --- | --- | --- | --- | --- |
| ALL | 24196 | 4284 | 10948 | 10948 | 2300 | 10948 |
| L1 | 16598 | 2945 | 7559 | 7559 | 1480 | 7559 |
| L2 | 2424 | 725 | 1212 | 1212 | 0 | 1212 |
| L3 | 2602 | 844 | 1041 | 1041 | 520 | 1041 |
| L4 | 2572 | 441 | 1136 | 1136 | 300 | 1136 |


world 可跨 Level/来源，不能相加。all-split 是描述性全覆盖；test-only 是已有冻结结果的子集，不是新增 test。ClaimAcc 对输入等权；BinaryClaimAcc 仅 S/C；PairAcc 要求同 pair 的 S/C 两条都正确，UNKNOWN 不进入 PairAcc；C/U Recall 对各 gold 标签条件化；World-macro 为逐 world 准确率等权均值，不是整数“正确 world 数”。

Source artifact: `./phase4/E0_results_20260910/E0_Full_Benchmark_Results_v2_CN.md`  
Source hash: `d771db4c26727dc261270b5b715113c14a656446795d671b6cc8007f09839fdf`  
Rows / metric names: §2 数据规模；与 acceptance 及分层统计交叉核对.


Source artifact: `artifacts/model_results/spatial_world_state/sws_20260909_v1/e0_refresh_20260910_v3_1/acceptance.json`  
Source hash: `0e6d3e8b70834581938d9ee7e7261c288e776d4ca7adf0e4cec1ba0c99213864`  
Rows / metric names: expected_inputs, main_common_worlds, captured_at.


### E0-A / Main Table 1A：全部完整模型

单元格给 numerator/denominator、百分比与 world 数。CI 未存储的扩展模型明确标 CI_NOT_AVAILABLE，不补造区间。

| Model | ClaimAcc | 95% CI | BinaryClaimAcc | PairAcc | 95% CI | C Recall | U Recall | World-macro |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| internvl35_14b | 14641/24196 = 60.51%; W=4284 | CI_NOT_AVAILABLE | 13835/21896 = 63.19%; W=4238 CI_NOT_AVAILABLE | 4444/10948 = 40.59%; W=4238 | CI_NOT_AVAILABLE | 7440/10948 = 67.96%; W=4238 CI_NOT_AVAILABLE | 806/2300 = 35.04%; W=858 CI_NOT_AVAILABLE | 2664.0223733565595/4284 = 62.19%; W=4284 CI_NOT_AVAILABLE |
| internvl35_8b | 13984/24196 = 57.79%; W=4284 | CI_NOT_AVAILABLE | 13070/21896 = 59.69%; W=4238 CI_NOT_AVAILABLE | 3746/10948 = 34.22%; W=4238 | CI_NOT_AVAILABLE | 7433/10948 = 67.89%; W=4238 CI_NOT_AVAILABLE | 914/2300 = 39.74%; W=858 CI_NOT_AVAILABLE | 2385.2141420289204/4284 = 55.68%; W=4284 CI_NOT_AVAILABLE |
| mimo_vl_7b_rl | 9359/24196 = 38.68%; W=4284 | CI_NOT_AVAILABLE | 7759/21896 = 35.44%; W=4238 CI_NOT_AVAILABLE | 1928/10948 = 17.61%; W=4238 | CI_NOT_AVAILABLE | 2311/10948 = 21.11%; W=4238 CI_NOT_AVAILABLE | 1600/2300 = 69.57%; W=858 CI_NOT_AVAILABLE | 1566.4611687861764/4284 = 36.57%; W=4284 CI_NOT_AVAILABLE |
| qwen25vl_32b | 13105/24196 = 54.16%; W=4284 | CI_NOT_AVAILABLE | 11848/21896 = 54.11%; W=4238 CI_NOT_AVAILABLE | 3590/10948 = 32.79%; W=4238 | CI_NOT_AVAILABLE | 3910/10948 = 35.71%; W=4238 CI_NOT_AVAILABLE | 1257/2300 = 54.65%; W=858 CI_NOT_AVAILABLE | 2223.8577309025745/4284 = 51.91%; W=4284 CI_NOT_AVAILABLE |
| qwen25vl_7b | 5895/24196 = 24.36%; W=4284 | CI_NOT_AVAILABLE | 3877/21896 = 17.71%; W=4238 CI_NOT_AVAILABLE | 132/10948 = 1.21%; W=4238 | CI_NOT_AVAILABLE | 136/10948 = 1.24%; W=4238 CI_NOT_AVAILABLE | 2018/2300 = 87.74%; W=858 CI_NOT_AVAILABLE | 1002.0691955550407/4284 = 23.39%; W=4284 CI_NOT_AVAILABLE |
| qwen35_27b | 15130/24196 = 62.53%; W=4284 | [61.7491, 63.2796]% | 14066/21896 = 64.24%; W=4238 [63.4754, 65.0071]% | 5587/10948 = 51.03%; W=4238 | [50.0408, 51.9804]% | 7201/10948 = 65.77%; W=4238 [64.8339, 66.7154]% | 1064/2300 = 46.26%; W=858 [43.6419, 48.8981]% | 2329.875445672674/4284 = 54.39%; W=4284 [53.6812, 55.1066]% |
| qwen35_4b | 13505/24196 = 55.82%; W=4284 | [55.0942, 56.5595]% | 12315/21896 = 56.24%; W=4238 [55.5033, 56.9744]% | 4012/10948 = 36.65%; W=4238 | [35.5958, 37.6623]% | 4924/10948 = 44.98%; W=4238 [43.8590, 46.1164]% | 1190/2300 = 51.74%; W=858 [48.7632, 54.5532]% | 2153.7463005609006/4284 = 50.27%; W=4284 [49.5001, 51.0439]% |
| qwen35_9b | 14339/24196 = 59.26%; W=4284 | [58.5372, 60.0075]% | 13150/21896 = 60.06%; W=4238 [59.3033, 60.7952]% | 4741/10948 = 43.30%; W=4238 | [42.3208, 44.2781]% | 5828/10948 = 53.23%; W=4238 [52.2068, 54.2334]% | 1189/2300 = 51.70%; W=858 [49.0176, 54.3650]% | 2240.523956461215/4284 = 52.30%; W=4284 [51.5527, 53.0459]% |
| qwen3vl_2b_thinking | 6226/24196 = 25.73%; W=4284 | CI_NOT_AVAILABLE | 5929/21896 = 27.08%; W=4238 CI_NOT_AVAILABLE | 1679/10948 = 15.34%; W=4238 | CI_NOT_AVAILABLE | 2816/10948 = 25.72%; W=4238 CI_NOT_AVAILABLE | 297/2300 = 12.91%; W=858 CI_NOT_AVAILABLE | 908.7228043940723/4284 = 21.21%; W=4284 CI_NOT_AVAILABLE |
| qwen3vl_8b_instruct | 12349/24196 = 51.04%; W=4284 | CI_NOT_AVAILABLE | 10698/21896 = 48.86%; W=4238 CI_NOT_AVAILABLE | 3469/10948 = 31.69%; W=4238 | CI_NOT_AVAILABLE | 5379/10948 = 49.13%; W=4238 CI_NOT_AVAILABLE | 1651/2300 = 71.78%; W=858 CI_NOT_AVAILABLE | 1966.3921780259855/4284 = 45.90%; W=4284 CI_NOT_AVAILABLE |


Source artifact: `artifacts/model_results/spatial_world_state/sws_20260909_v1/e0_refresh_20260910_v3_1/tables/primary_statistics_ci.csv`  
Source hash: `b7f8c310677cae7e055e35640e0ea64e0abb8f7537b2aa15a4276287e237ac30`  
Rows / metric names: dimension=('OVERALL', 'ALL'); 六项 metric；world-macro numerator 为各 world accuracy 之和.


### E0-B / Main Table 1B：完整模型 L1–L4


| Model | L1 ClaimAcc | L1 PairAcc | L2 ClaimAcc | L2 PairAcc | L3 ClaimAcc | L3 PairAcc | L4 ClaimAcc | L4 PairAcc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| internvl35_14b | 9777/16598 = 58.90%; W=2945 CI_NOT_AVAILABLE | 2834/7559 = 37.49%; W=2924 CI_NOT_AVAILABLE | 2076/2424 = 85.64%; W=725 CI_NOT_AVAILABLE | 889/1212 = 73.35%; W=725 CI_NOT_AVAILABLE | 1380/2602 = 53.04%; W=844 CI_NOT_AVAILABLE | 286/1041 = 27.47%; W=796 CI_NOT_AVAILABLE | 1408/2572 = 54.74%; W=441 CI_NOT_AVAILABLE | 435/1136 = 38.29%; W=441 CI_NOT_AVAILABLE |
| internvl35_8b | 9508/16598 = 57.28%; W=2945 CI_NOT_AVAILABLE | 2553/7559 = 33.77%; W=2924 CI_NOT_AVAILABLE | 1742/2424 = 71.86%; W=725 CI_NOT_AVAILABLE | 593/1212 = 48.93%; W=725 CI_NOT_AVAILABLE | 1352/2602 = 51.96%; W=844 CI_NOT_AVAILABLE | 227/1041 = 21.81%; W=796 CI_NOT_AVAILABLE | 1382/2572 = 53.73%; W=441 CI_NOT_AVAILABLE | 373/1136 = 32.83%; W=441 CI_NOT_AVAILABLE |
| mimo_vl_7b_rl | 6014/16598 = 36.23%; W=2945 CI_NOT_AVAILABLE | 926/7559 = 12.25%; W=2924 CI_NOT_AVAILABLE | 1709/2424 = 70.50%; W=725 CI_NOT_AVAILABLE | 732/1212 = 60.40%; W=725 CI_NOT_AVAILABLE | 632/2602 = 24.29%; W=844 CI_NOT_AVAILABLE | 38/1041 = 3.65%; W=796 CI_NOT_AVAILABLE | 1004/2572 = 39.04%; W=441 CI_NOT_AVAILABLE | 232/1136 = 20.42%; W=441 CI_NOT_AVAILABLE |
| qwen25vl_32b | 9034/16598 = 54.43%; W=2945 CI_NOT_AVAILABLE | 2483/7559 = 32.85%; W=2924 CI_NOT_AVAILABLE | 1260/2424 = 51.98%; W=725 CI_NOT_AVAILABLE | 523/1212 = 43.15%; W=725 CI_NOT_AVAILABLE | 1366/2602 = 52.50%; W=844 CI_NOT_AVAILABLE | 259/1041 = 24.88%; W=796 CI_NOT_AVAILABLE | 1445/2572 = 56.18%; W=441 CI_NOT_AVAILABLE | 325/1136 = 28.61%; W=441 CI_NOT_AVAILABLE |
| qwen25vl_7b | 3881/16598 = 23.38%; W=2945 CI_NOT_AVAILABLE | 64/7559 = 0.85%; W=2924 CI_NOT_AVAILABLE | 530/2424 = 21.86%; W=725 CI_NOT_AVAILABLE | 2/1212 = 0.17%; W=725 CI_NOT_AVAILABLE | 800/2602 = 30.75%; W=844 CI_NOT_AVAILABLE | 0/1041 = 0.00%; W=796 CI_NOT_AVAILABLE | 684/2572 = 26.59%; W=441 CI_NOT_AVAILABLE | 66/1136 = 5.81%; W=441 CI_NOT_AVAILABLE |
| qwen35_27b | 9729/16598 = 58.62%; W=2945 [57.7028, 59.5231]% | 3508/7559 = 46.41%; W=2924 [45.2700, 47.5417]% | 2223/2424 = 91.71%; W=725 [89.4409, 93.7934]% | 1063/1212 = 87.71%; W=725 [84.9180, 90.4203]% | 1505/2602 = 57.84%; W=844 [55.3728, 60.2943]% | 515/1041 = 49.47%; W=796 [46.0901, 52.6823]% | 1673/2572 = 65.05%; W=441 [63.2138, 66.8999]% | 501/1136 = 44.10%; W=441 [40.9760, 47.2841]% |
| qwen35_4b | 8730/16598 = 52.60%; W=2945 [51.7110, 53.4472]% | 2610/7559 = 34.53%; W=2924 [33.4546, 35.6444]% | 2028/2424 = 83.66%; W=725 [80.8763, 86.3952]% | 863/1212 = 71.20%; W=725 [66.5612, 75.9214]% | 1225/2602 = 47.08%; W=844 [45.0693, 49.0408]% | 214/1041 = 20.56%; W=796 [17.8155, 23.4375]% | 1522/2572 = 59.18%; W=441 [57.6968, 60.6129]% | 325/1136 = 28.61%; W=441 [25.9364, 31.3601]% |
| qwen35_9b | 9204/16598 = 55.45%; W=2945 [54.5702, 56.3021]% | 2954/7559 = 39.08%; W=2924 [38.0096, 40.1586]% | 2177/2424 = 89.81%; W=725 [87.5581, 91.9737]% | 1025/1212 = 84.57%; W=725 [81.4902, 87.5869]% | 1396/2602 = 53.65%; W=844 [51.3158, 56.0247]% | 412/1041 = 39.58%; W=796 [36.2614, 42.6890]% | 1562/2572 = 60.73%; W=441 [59.1342, 62.2477]% | 350/1136 = 30.81%; W=441 [27.9714, 33.6247]% |
| qwen3vl_2b_thinking | 4770/16598 = 28.74%; W=2945 CI_NOT_AVAILABLE | 1162/7559 = 15.37%; W=2924 CI_NOT_AVAILABLE | 1267/2424 = 52.27%; W=725 CI_NOT_AVAILABLE | 496/1212 = 40.92%; W=725 CI_NOT_AVAILABLE | 119/2602 = 4.57%; W=844 CI_NOT_AVAILABLE | 20/1041 = 1.92%; W=796 CI_NOT_AVAILABLE | 70/2572 = 2.72%; W=441 CI_NOT_AVAILABLE | 1/1136 = 0.09%; W=441 CI_NOT_AVAILABLE |
| qwen3vl_8b_instruct | 8343/16598 = 50.27%; W=2945 CI_NOT_AVAILABLE | 2250/7559 = 29.77%; W=2924 CI_NOT_AVAILABLE | 1662/2424 = 68.56%; W=725 CI_NOT_AVAILABLE | 716/1212 = 59.08%; W=725 CI_NOT_AVAILABLE | 1284/2602 = 49.35%; W=844 CI_NOT_AVAILABLE | 211/1041 = 20.27%; W=796 CI_NOT_AVAILABLE | 1060/2572 = 41.21%; W=441 CI_NOT_AVAILABLE | 292/1136 = 25.70%; W=441 CI_NOT_AVAILABLE |


Source artifact: `artifacts/model_results/spatial_world_state/sws_20260909_v1/e0_refresh_20260910_v3_1/tables/primary_statistics_ci.csv`  
Source hash: `b7f8c310677cae7e055e35640e0ea64e0abb8f7537b2aa15a4276287e237ac30`  
Rows / metric names: LEVEL × L1–L4 × ClaimAcc/PairAcc; 完整模型.


### 已有 test-only 与模型状态


| Model | Metric | 正确/分母，worlds | 95% CI |
| --- | --- | --- | --- |
| internvl35_14b | ClaimAcc | 3087/5608 = 55.05%; W=1162 | CI_NOT_AVAILABLE |
| internvl35_14b | PairAcc | 784/1771 = 44.27%; W=1114 | CI_NOT_AVAILABLE |
| internvl35_8b | ClaimAcc | 2864/5608 = 51.07%; W=1162 | CI_NOT_AVAILABLE |
| internvl35_8b | PairAcc | 584/1771 = 32.98%; W=1114 | CI_NOT_AVAILABLE |
| mimo_vl_7b_rl | ClaimAcc | 2787/5608 = 49.70%; W=1162 | CI_NOT_AVAILABLE |
| mimo_vl_7b_rl | PairAcc | 403/1771 = 22.76%; W=1114 | CI_NOT_AVAILABLE |
| qwen25vl_32b | ClaimAcc | 3011/5608 = 53.69%; W=1162 | CI_NOT_AVAILABLE |
| qwen25vl_32b | PairAcc | 566/1771 = 31.96%; W=1114 | CI_NOT_AVAILABLE |
| qwen25vl_7b | ClaimAcc | 2421/5608 = 43.17%; W=1162 | CI_NOT_AVAILABLE |
| qwen25vl_7b | PairAcc | 27/1771 = 1.52%; W=1114 | CI_NOT_AVAILABLE |
| qwen35_27b | ClaimAcc | 3143/5608 = 56.04%; W=1162 | [54.6515, 57.4833]% |
| qwen35_27b | PairAcc | 902/1771 = 50.93%; W=1114 | [48.7901, 53.0579]% |
| qwen35_4b | ClaimAcc | 3099/5608 = 55.26%; W=1162 | [53.8006, 56.7072]% |
| qwen35_4b | PairAcc | 694/1771 = 39.19%; W=1114 | [37.0097, 41.4410]% |
| qwen35_9b | ClaimAcc | 3169/5608 = 56.51%; W=1162 | [55.1003, 57.9458]% |
| qwen35_9b | PairAcc | 787/1771 = 44.44%; W=1114 | [42.2271, 46.6821]% |
| qwen3vl_2b_thinking | ClaimAcc | 1143/5608 = 20.38%; W=1162 | CI_NOT_AVAILABLE |
| qwen3vl_2b_thinking | PairAcc | 277/1771 = 15.64%; W=1114 | CI_NOT_AVAILABLE |
| qwen3vl_8b_instruct | ClaimAcc | 3098/5608 = 55.24%; W=1162 | CI_NOT_AVAILABLE |
| qwen3vl_8b_instruct | PairAcc | 539/1771 = 30.43%; W=1114 | CI_NOT_AVAILABLE |


Source artifact: `artifacts/model_results/spatial_world_state/sws_20260909_v1/e0_refresh_20260910_v3_1/tables/primary_statistics_ci.csv`  
Source hash: `b7f8c310677cae7e055e35640e0ea64e0abb8f7537b2aa15a4276287e237ac30`  
Rows / metric names: SOURCE_SPLIT=test；无新增 test 调用.


| Model | 返回/期望 | worlds | 主状态（冻结日） | 辅助解释状态 | 阻塞 |
| --- | --- | --- | --- | --- | --- |
| Gemma 4 31B IT | 18934/24196 | 4281 | PARTIAL | NOT_COMPLETE | N/A |
| InternVL3.5-14B | 24196/24196 | 4284 | COMPLETE | COMPLETE_AUTOMATIC_AUXILIARY_NOT_VISUAL_PROOF | N/A |
| InternVL3.5-8B | 24196/24196 | 4284 | COMPLETE | COMPLETE_AUTOMATIC_AUXILIARY_NOT_VISUAL_PROOF | N/A |
| Llama 4 Scout | 0/24196 | 0 | BLOCKED | NOT_COMPLETE | ACCESS_BLOCKED:GatedRepoError |
| MiMo-VL-7B-RL | 24196/24196 | 4284 | COMPLETE | COMPLETE_AUTOMATIC_AUXILIARY_NOT_VISUAL_PROOF | N/A |
| Qwen/Qwen2.5-VL-32B-Instruct | 24196/24196 | 4284 | COMPLETE | IN_PROGRESS | N/A |
| Qwen/Qwen2.5-VL-7B-Instruct | 24196/24196 | 4284 | COMPLETE | COMPLETE_AUTOMATIC_AUXILIARY_NOT_VISUAL_PROOF | N/A |
| Qwen/Qwen3.5-27B | 24196/24196 | 4284 | COMPLETE | IN_PROGRESS | N/A |
| Qwen/Qwen3.5-4B | 24196/24196 | 4284 | COMPLETE | COMPLETE_AUTOMATIC_AUXILIARY_NOT_VISUAL_PROOF | N/A |
| Qwen/Qwen3.5-9B | 24196/24196 | 4284 | COMPLETE | COMPLETE_AUTOMATIC_AUXILIARY_NOT_VISUAL_PROOF | N/A |
| Qwen/Qwen3-VL-2B-Thinking | 24196/24196 | 4284 | COMPLETE | COMPLETE_AUTOMATIC_AUXILIARY_NOT_VISUAL_PROOF | N/A |
| Qwen/Qwen3-VL-8B-Instruct | 24196/24196 | 4284 | COMPLETE | COMPLETE_AUTOMATIC_AUXILIARY_NOT_VISUAL_PROOF | N/A |
| Qwen/Qwen3-VL-8B-Thinking | 21055/24196 | 4284 | PARTIAL | NOT_COMPLETE | N/A |


Source artifact: `artifacts/model_results/spatial_world_state/sws_20260909_v1/e0_refresh_20260910_v3_1/tables/model_status.csv`  
Source hash: `998f9787ed96bbeff69094093018cee3ae0866f7e9036c3b538aa1de5834a737`  
Rows / metric names: 完整注册清单；状态截至冻结日期，不宣称实时队列状态.


E0 三个 Qwen3.5 的全量准确率随规模改善，但已有 test-only ClaimAcc 为 55.26%、56.51%、56.04%，不严格单调。L1–L4 不是难度阶梯，不能把不同 source/题型分布解释成单一机制。E0 的 CI 为来源分层、world 聚类的 5,000 次 bootstrap（seed 20260909）；不表示重复生成方差。扩展模型的 thinking/processor 差异限制横向因果解释。Qwen3-VL-2B-Thinking 的低分受 512-token 接口下无最终 label 影响，不能全部归为空间能力。辅助 judge 分与本文准确率分开，不作为独立视觉 gold。

Source artifact: `artifacts/model_results/spatial_world_state/sws_20260909_v1/e0_refresh_20260910_v3_1/tables/interface_diagnostics.csv`  
Source hash: `120512f4db645975ec0b13e92904d3840cc541a420aa2c6f96402c398feafb08`  
Rows / metric names: 保留接口诊断；未调整 budget/parser.


## 4. Diagnostic Experimental Framework


```text
Visual world
  ├─ B02: independently report S0
  ├─ B01: full sequential transition
  └─ B05: explicit S0 + same media
         ↓ matched comparisons, not one internal trace
     B07(old S1 sham) / B07_MATCHED_V2(S0 sham)
     B08(symbolic) / B09(S1 + A2 suffix)
         ├─ W1: target prompt semantics
         ├─ Non-count: bounded coordinate transformation
         └─ R1 readability / I2 S1 interchange / I1 S0 donor patch
                 LOCALIZE → frozen candidates → SELECT NO_GO
                 I3 and cross-scale internal validation NOT_RUN
```


每个节点是独立请求或独立干预，不是把跨请求的正确答案拼成同一次正确内部轨迹。B1 80 个 world 各两序列，保护 pre 共享查询；W1 96 程序来自 16 家族；非计数 47 个 world；I1/I2 重复 layer/anchor/donor 不增加独立 world。

## 5. Exact Prompt Templates：阅读约定


完整英文 prompt 在末尾 Appendix A（属于本单文件）。逐字提取实际 public request 的 payload.system/text；E0 另外提取冻结响应的 rendered_prompt。没有按指南事后重写。这里采用完整已实例化模板（无手造 placeholder）；同一程序完整并列 T1–T4 × S0/S1/S2。每例记录实际 condition、system 引用、media 顺序/数量、schema 和 gold。媒体本身不嵌入，ChatGPT 不得声称重新看过图片验证 gold。

### 5.1 Unified diagnostic runtime settings（论文 Method / Appendix 用）

本表覆盖后续诊断实验，不替代 E0 的独立运行协议。4B/9B/27B 的完整 Model ID 与 revision 映射列在表后；所有设置来自实际环境记录与所用 runner，不从 E0 配置推定。B1/W0 列中，生成设置仅指 B1，W0 只读取历史预测做统计，没有额外推理。

| Setting | B1 / W0 | W1 | Non-count | R1 | I2 | I1 |
| --- | --- | --- | --- | --- | --- | --- |
| Model ID | Qwen3.5-4B / 9B / 27B | 同前三模型 | 同前三模型 | 同前三模型 | Qwen3.5-9B | Qwen3.5-9B |
| Model revision | R4 / R9 / R27 | R4 / R9 / R27 | R4 / R9 / R27 | R4 / R9 / R27 | R9 | R9 |
| Thinking | Off | Off | Off | Off（输入模板；正式提取不生成答案） | Off | Off |
| Decode | Greedy；W0=N/A | Greedy | Greedy | N/A（forward extraction） | Greedy / argmax | Greedy / argmax |
| max_new_tokens | 512；W0=N/A | 512 | 512 | N/A（正式表示提取） | 512 | 512 |
| Model forward dtype | BF16；W0=N/A | BF16 | BF16 | BF16；保存 residual=FP32，CPU probe=FP64 | BF16；候选 logits 转 FP32 | BF16；候选 logits 转 FP32 |
| Processor revision | 对应本地 checkpoint processor；见注1 | 同左 | 同左 | 同左 | 本地 R9 checkpoint processor；见注1 | 同左 |
| Processor class | Qwen3VLProcessor | Qwen3VLProcessor | Qwen3VLProcessor | 同一共享 Pipeline | 同一共享 Pipeline | 同一共享 Pipeline |
| Image min/max pixels | 100,352 / 401,408（有媒体的条件） | N/A（纯符号） | 100,352 / 401,408 | B1视觉上下文：100,352 / 401,408；B2符号：N/A | N/A（正式符号互换） | 100,352 / 401,408 |
| Generation / forward cache | B1 `use_cache=True`；W0=N/A | `use_cache=True` | `use_cache=True` | 正式提取 `use_cache=False` | `use_cache=False`；每生成token重算完整prefix | `use_cache=False`；每生成token重算完整prefix |
| Attention backend | SDPA | SDPA | SDPA | SDPA | SDPA | SDPA |
| Request batch size | 1（B1生成） | 1 | 1 | 1 context/forward | 1 recipient/trial | 1 recipient/trial |

固定模型版本（完整 Hugging Face repository ID；不是可变的 `main` 分支）：

- **R4**：`Qwen/Qwen3.5-4B`，revision=`851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`。
- **R9**：`Qwen/Qwen3.5-9B`，revision=`c202236235762e1c871ad0ccb60c8ee5ba337b9a`。
- **R27**：`Qwen/Qwen3.5-27B`，revision=`fc05daec18b0a78c049392ed2e771dde82bdf654`。

注1（processor 版本的证据边界）：实际调用为 `AutoProcessor.from_pretrained(model_path, local_files_only=True, use_fast=True)`，加载与对应模型同目录的本地 processor；没有另传独立 `revision=`，也没有单独记录一个不同的 processor commit。行为 raw 中确有 `processor_revision` 字段，但 runner 将其直接赋为 `mc['revision']`（模型 revision），所以它不是对独立 processor commit 的另一次验证。论文应写“processor loaded from the corresponding local model checkpoint; no separately pinned processor revision”，不能把该字段说成独立验证的第二个版本号。环境记录另保存 `processor_configuration` 和 `chat_template_sha256`，实际视觉输入也有逐请求 tensor hash。

注2（有效图像预算）：表中为每张图像的有效面积预算，而非固定宽高、总请求预算或processor配置文件中的默认 `size`。共享视觉 helper 先按 min/max pixels 缩放，再调用 processor 时设置 `do_resize=False`，避免二次缩放。patch size=16、merge size=2；W1和正式I2没有图像，所以不写全局默认值冒充实际视觉输入。R1包含视觉B1与纯符号B2上下文，两类分开标记。

注3（缓存与技术对照）：I1/I2 的正式干预及其对应 unpatched replay 基线禁用生成缓存，设置 `past_key_values=None` 并每步重放完整prefix；cached reference、noop/self 等技术等价测试另行存在，不能据此将正式实验填为 cached。R1 的正式表示提取无答案生成，缓存为关闭；其 T0 技术校准包含cached/uncached比较，但不算正式R1 decode。视觉图片的预处理缓存与模型生成缓存不是同一概念。

注4（解码与精度）：Greedy 指 `do_sample=False`，没有用于采样的temperature/top-p。BF16是模型加载/前向精度，不意味着所有中间计算、log-prob或CPU统计均为BF16；R1明确将residual转为FP32保存，再转FP64拟合probe。I1/I2将logits转FP32后计算log-softmax。实际记录的环境为 PyTorch `2.8.0+cu126`、Transformers `5.16.0.dev0`；模型未量化。512-token上限仍按保留输出评分，截断不自动判无效。W0本身没有dtype或decode设置；B1历史复用答案不被描述成重新生成。

来源（本小表的补充核验；未修改实验或历史配置）：

- Source artifact: `artifacts/model_results/qwen35_scale_512_20260906/config.json`；Source hash: `4a079d6c09c9aac4a6e60a8ec71e861af85c6199885f8014f23608e23f06bafc`；字段：`models[].model/revision/model_path`、`media_budget`。
- Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_b1b2_20260911_v1/config.json`；Source hash: `9f3ea50201028a23e8194535946957496a541fee09332300b3a775c62d4dc3b0`；字段：`generation`。另核对 B1、W1_TARGET、NONCOUNT 各三模型实际 `raw/<model>/shard_*/environment_*.json` 的 `model_revision/generation/media_budget/processor_configuration`，并非只读配置模板。
- Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_b1b2_20260911_v1/independent_wave1/representations_v2/qwen35_9b/EXTRACTION_ACCEPTANCE.json`；Source hash: `917dbf25e6690c63c4688e16a9bdf36f9358430c9f88f275f6f177c1275718f0`；字段：`model`、`actual_r1_forwards`、`new_behavior_answers`；4B/27B同名验收记录也核对为R4/R27。
- Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_b1b2_20260911_v1/i2_interchange_v1/technical/qwen35_9b/ACCEPTANCE.json`；Source hash: `3b35b2abf24cfe119aa001700c9b72dedfa0c36b14b1759bf09154d5b5ff65a6`；字段：`config.model/dtype/backend/cache_policy/torch/transformers`。
- Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/I1/technical/qwen35_9b/TECHNICAL_ACCEPTANCE.json`；Source hash: `1717ed9c7d61cdba2f695d5ed0219c3818ef0c205e39acaa070ea13cf5abb656`；字段：`engine.model/dtype/backend/cache_policy/torch/transformers`。
- 实现追踪：项目 `phase4/execution_sws_v1/real_worker_v1.py` 的 `model.generate` 与 `processor_revision` 赋值；`SpaceConflict/research/state_binding_phase_a1/core_execution_v3/pipeline_v3.py` 的 processor加载、`enable_thinking=False`、`do_resize=False`；`phase6/execution_ssm_internal_v1/representations.py` 和 `probe.py` 的前向/存储/拟合精度；`phase6/execution_ssm_i2_v1/engine.py` 的 `generate/forward/score`。R1实际使用 `representations_text_rope_v2.py` 受锁定修补包装，未改变上述dtype/cache设置。

## 6. W0 Operationalization-Gap Cases / Main Table 3


A: B02对、B01错、B05对；B: B02错、B01错、B05对；C: B02对、B01对；D: B02错、B01对；E: B01错、B05错。对本批全部返回、正确性为布尔值的记录，这五类互斥且穷尽；缺失时应另列 UNRESOLVED。null/invalid 被原 scorer 计作不正确仍可能落入行为类别，I1 主有效类别另外排除这些接口案例。各类 world 可重叠。

| Model | Type A seq/world | Type B seq/world | Type C seq/world | Type D seq/world | Type E seq/world |
| --- | --- | --- | --- | --- | --- |
| Qwen3.5-4B | 35/30 | 39/26 | 40/39 | 4/4 | 42/40 |
| Qwen3.5-9B | 50/37 | 54/30 | 50/37 | 6/6 | 0/0 |
| Qwen3.5-27B | 11/8 | 55/31 | 85/45 | 9/8 | 0/0 |


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/W0/cases.jsonl`  
Source hash: `37a25b5dda9bcbb0d2b5981129abc5fd00e20519a733d4f39eb7da52f4a7619d`  
Rows / metric names: cohorts × model；480 model-sequence records / 80 worlds.


| Model | Conditional metric | numerator/denominator | worlds | rate | 95% CI |
| --- | --- | --- | --- | --- | --- |
| qwen35_4b | B01_WRONG_GIVEN_B02_CORRECT | 64/104 | 52 | 61.54% | [55.7692, 68.2692]% |
| qwen35_4b | B05_RESCUE_GIVEN_B02_CORRECT_B01_WRONG | 35/64 | 51 | 54.69% | [42.1875, 66.6667]% |
| qwen35_4b | B06_RESCUE_GIVEN_B03_CORRECT_B01_WRONG | 35/44 | 34 | 79.55% | [65.8537, 91.1111]% |
| qwen35_9b | B01_WRONG_GIVEN_B02_CORRECT | 50/100 | 50 | 50.00% | [40.0000, 60.0000]% |
| qwen35_9b | B05_RESCUE_GIVEN_B02_CORRECT_B01_WRONG | 50/50 | 37 | 100.00% | [100.0000, 100.0000]% |
| qwen35_9b | B06_RESCUE_GIVEN_B03_CORRECT_B01_WRONG | 14/23 | 23 | 60.87% | [39.1304, 78.2609]% |
| qwen35_27b | B01_WRONG_GIVEN_B02_CORRECT | 11/96 | 48 | 11.46% | [4.1667, 19.7917]% |
| qwen35_27b | B05_RESCUE_GIVEN_B02_CORRECT_B01_WRONG | 11/11 | 8 | 100.00% | [100.0000, 100.0000]% |
| qwen35_27b | B06_RESCUE_GIVEN_B03_CORRECT_B01_WRONG | 17/19 | 15 | 89.47% | [75.0000, 100.0000]% |


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/W0/CONDITIONAL_METRICS.csv`  
Source hash: `fd212c63bb196a0910f084db22c6f7e1ebc03fba40eac304eeba5226cac2b547`  
Rows / metric names: 全部三项条件概率，已有 Phase7 CI 原样保留.


B05 rescue | Type A 按 Type A 的定义必为 100%，不是独立疗效证据；有意义的分母是全部 B02正确且B01错误案例。B1 的通用条件 CI 和 W0 的条件化 CI 来自不同冻结统计产物，不因小数差异选择较好看的区间。

## 7. B1 Behavioral Bridge / Main Table 2


| Condition | Qwen3.5-4B correct/N | Qwen3.5-4B % [95% CI] | Qwen3.5-4B worlds | Qwen3.5-9B correct/N | Qwen3.5-9B % [95% CI] | Qwen3.5-9B worlds | Qwen3.5-27B correct/N | Qwen3.5-27B % [95% CI] | Qwen3.5-27B worlds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B00 | 47/160 | 29.38% [21.8750, 37.5000]% | 80 | 53/160 | 33.12% [26.2500, 40.6250]% | 80 | 97/160 | 60.62% [51.2500, 70.0000]% | 80 |
| B01 | 44/160 | 27.50% [21.8750, 33.1250]% | 80 | 56/160 | 35.00% [26.8750, 43.1250]% | 80 | 94/160 | 58.75% [48.7500, 68.7500]% | 80 |
| B02 | 104/160 | 65.00% [53.7500, 75.0000]% | 80 | 100/160 | 62.50% [51.2500, 72.5000]% | 80 | 96/160 | 60.00% [50.0000, 70.0000]% | 80 |
| B03 | 67/160 | 41.88% [32.5000, 51.2500]% | 80 | 46/160 | 28.75% [20.6250, 36.8750]% | 80 | 111/160 | 69.38% [59.9844, 78.7656]% | 80 |
| B04 | 25/160 | 15.62% [10.6250, 21.2500]% | 80 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 |
| B05 | 103/160 | 64.38% [56.2500, 72.5000]% | 80 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 |
| B06 | 123/160 | 76.88% [70.6250, 83.1250]% | 80 | 104/160 | 65.00% [56.8750, 73.7500]% | 80 | 138/160 | 86.25% [80.0000, 91.8750]% | 80 |
| B07 | 42/160 | 26.25% [20.0000, 33.7500]% | 80 | 48/160 | 30.00% [22.5000, 38.1250]% | 80 | 95/160 | 59.38% [49.3750, 68.7500]% | 80 |
| B08 | 140/160 | 87.50% [83.1250, 91.8750]% | 80 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 |
| B09 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 |
| B10 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 | 154/160 | 96.25% [91.8750, 99.3750]% | 80 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 |
| B11 | 157/160 | 98.12% [95.0000, 100.0000]% | 80 | 159/160 | 99.38% [98.1250, 100.0000]% | 80 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 |
| B12 | 159/160 | 99.38% [98.1250, 100.0000]% | 80 | 150/160 | 93.75% [90.0000, 96.8750]% | 80 | 158/160 | 98.75% [96.8750, 100.0000]% | 80 |
| B13 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 |
| B14 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 | 160/160 | 100.00% [100.0000, 100.0000]% | 80 |
| B15 | 103/160 | 64.38% [53.7500, 75.0000]% | 80 | 99/160 | 61.88% [51.2500, 71.8750]% | 80 | 97/160 | 60.62% [50.0000, 71.2500]% | 80 |
| B16 | 34/160 | 21.25% [13.1250, 30.0000]% | 80 | 49/160 | 30.63% [21.2500, 40.0000]% | 80 | 29/160 | 18.12% [10.6250, 26.2500]% | 80 |
| B17 | 84/160 | 52.50% [41.2500, 63.7500]% | 80 | 80/160 | 50.00% [38.7500, 61.2500]% | 80 | 102/160 | 63.75% [52.5000, 73.7500]% | 80 |
| PROTECTED_PRE_SUPPLEMENT | 40/80 | 50.00% [38.7500, 61.2500]% | 80 | 29/80 | 36.25% [26.2500, 46.2500]% | 80 | 39/80 | 48.75% [37.5000, 60.0000]% | 80 |


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_b1b2_20260911_v1/result_summary_20260911/B1_B2_ALL_CONDITIONS.csv`  
Source hash: `7f7a934a1309fa7605bb50c65723bd0f3a86e323a8f2996cd130e8a47c62787d`  
Rows / metric names: batch=B1, sequence=ALL, split=ALL；全部18条件与保护pre补充.


B01 Full visual；B02 Direct S0；B03 S1 in full context；B05 explicit S0；B06 explicit S1；B07 历史 S1 sham；B08 symbolic；B09 S1+A2 suffix；B10/B11/B12 state-table S0/S1/S2；B15 post-action query S0；B16 protected after；B17 first-action S1；PROTECTED_PRE_SUPPLEMENT 是初始保护事实独立查询。B00/B04/B13/B14 作为附录控制保留，不混入核心 Type A 定义。


### 配对 rescue / harm

每项同 world/同序列配对，N=160、80 worlds。Rescue 分母是 baseline 错误；harm 分母是 baseline 正确；净差=(rescue−harm)/160。

| Model | Contrast | Rescue / before-wrong | Harm / before-correct | Net Δ pp | 95% CI pp | N/worlds |
| --- | --- | --- | --- | --- | --- | --- |
| qwen35_4b | B05_minus_B01 | 74/116 | 15/44 | 36.875 | [25.6250, 47.5000]% | 160/80 |
| qwen35_4b | B06_minus_B01 | 86/116 | 7/44 | 49.375 | [42.5000, 56.2500]% | 160/80 |
| qwen35_4b | B07_minus_B01 | 5/116 | 7/44 | -1.250 | [-5.6250, 3.1250]% | 160/80 |
| qwen35_4b | B08_minus_B01 | 96/116 | 0/44 | 60.000 | [53.7500, 66.2500]% | 160/80 |
| qwen35_4b | B09_minus_B01 | 116/116 | 0/44 | 72.500 | [66.8750, 78.1250]% | 160/80 |
| qwen35_9b | B05_minus_B01 | 104/104 | 0/56 | 65.000 | [56.8750, 73.1250]% | 160/80 |
| qwen35_9b | B06_minus_B01 | 55/104 | 7/56 | 30.000 | [21.2500, 38.7500]% | 160/80 |
| qwen35_9b | B07_minus_B01 | 5/104 | 13/56 | -5.000 | [-10.0000, 0.6250]% | 160/80 |
| qwen35_9b | B08_minus_B01 | 104/104 | 0/56 | 65.000 | [56.8750, 73.1250]% | 160/80 |
| qwen35_9b | B09_minus_B01 | 104/104 | 0/56 | 65.000 | [56.8750, 72.5000]% | 160/80 |
| qwen35_27b | B05_minus_B01 | 66/66 | 0/94 | 41.250 | [31.2500, 51.2500]% | 160/80 |
| qwen35_27b | B06_minus_B01 | 46/66 | 2/94 | 27.500 | [18.7500, 36.2500]% | 160/80 |
| qwen35_27b | B07_minus_B01 | 4/66 | 3/94 | 0.625 | [-2.5000, 3.7500]% | 160/80 |
| qwen35_27b | B08_minus_B01 | 66/66 | 0/94 | 41.250 | [31.8750, 51.2500]% | 160/80 |
| qwen35_27b | B09_minus_B01 | 66/66 | 0/94 | 41.250 | [31.2500, 51.2500]% | 160/80 |


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_b1b2_20260911_v1/result_summary_20260911/B1_PAIRED_CHANGES.csv`  
Source hash: `e135dcae9dae7d8697eb484b22d36d3e1ab5d474d46aeb19bf2d04e2a26ffeb7`  
Rows / metric names: split=ALL，全部已存配对对比.


## 8. B01/B06 Error Taxonomy


以下只在原 scorer 判错的序列内统计。主表使用原 numeric_class，多个数值签名一律 AMBIGUOUS，不强行解释为状态选择。S1 与 SHAM_S1_VALUE 本来同值，因此签名分类中常落入歧义；另给非互斥“数值相等”表避免把 exclusive S1=0 错当从不输出 S1。A2_ON_S0 使用实际 A2 运算，不一定是加法。

### B01

| Model | 错误/N | 错误worlds | S0 | S1 | A1_AMOUNT | A2_AMOUNT | A2_ON_S0 | A1_REPEATED_ON_S1 | OTHER_INTEGER | NULL | INVALID | AMBIGUOUS_NUMERIC_PATTERN |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen35_4b | 116/160 | 79 | 7/116 | 0/116 | 3/116 | 3/116 | 10/116 | 6/116 | 27/116 | 3/116 | 0/116 | 57/116 |
| qwen35_9b | 104/160 | 67 | 6/104 | 0/104 | 1/104 | 9/104 | 5/104 | 12/104 | 15/104 | 18/104 | 0/104 | 38/104 |
| qwen35_27b | 66/160 | 39 | 0/66 | 0/66 | 0/66 | 9/66 | 10/66 | 8/66 | 11/66 | 3/66 | 0/66 | 25/66 |


| Model | 非互斥签名 | count/errors | worlds |
| --- | --- | --- | --- |
| qwen35_4b | S0 | 31/116 | 31 |
| qwen35_4b | S1 | 35/116 | 31 |
| qwen35_4b | A1_AMOUNT | 30/116 | 27 |
| qwen35_4b | A2_AMOUNT | 21/116 | 20 |
| qwen35_4b | A2_ON_S0 | 10/116 | 10 |
| qwen35_4b | A1_REPEATED_ON_S1 | 17/116 | 16 |
| qwen35_9b | S0 | 17/104 | 17 |
| qwen35_9b | S1 | 17/104 | 17 |
| qwen35_9b | A1_AMOUNT | 17/104 | 16 |
| qwen35_9b | A2_AMOUNT | 33/104 | 30 |
| qwen35_9b | A2_ON_S0 | 5/104 | 5 |
| qwen35_9b | A1_REPEATED_ON_S1 | 21/104 | 21 |
| qwen35_27b | S0 | 1/66 | 1 |
| qwen35_27b | S1 | 19/66 | 19 |
| qwen35_27b | A1_AMOUNT | 11/66 | 11 |
| qwen35_27b | A2_AMOUNT | 22/66 | 15 |
| qwen35_27b | A2_ON_S0 | 10/66 | 6 |
| qwen35_27b | A1_REPEATED_ON_S1 | 9/66 | 9 |


### B06

| Model | 错误/N | 错误worlds | S0 | S1 | A1_AMOUNT | A2_AMOUNT | A2_ON_S0 | A1_REPEATED_ON_S1 | OTHER_INTEGER | NULL | INVALID | AMBIGUOUS_NUMERIC_PATTERN |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen35_4b | 37/160 | 33 | 0/37 | 0/37 | 0/37 | 0/37 | 1/37 | 20/37 | 0/37 | 0/37 | 0/37 | 16/37 |
| qwen35_9b | 56/160 | 40 | 0/56 | 0/56 | 0/56 | 11/56 | 0/56 | 7/56 | 18/56 | 1/56 | 0/56 | 19/56 |
| qwen35_27b | 22/160 | 18 | 0/22 | 0/22 | 0/22 | 0/22 | 3/22 | 0/22 | 5/22 | 0/22 | 0/22 | 14/22 |


| Model | 非互斥签名 | count/errors | worlds |
| --- | --- | --- | --- |
| qwen35_4b | S0 | 0/37 | 0 |
| qwen35_4b | S1 | 16/37 | 14 |
| qwen35_4b | A1_AMOUNT | 2/37 | 2 |
| qwen35_4b | A2_AMOUNT | 1/37 | 1 |
| qwen35_4b | A2_ON_S0 | 1/37 | 1 |
| qwen35_4b | A1_REPEATED_ON_S1 | 20/37 | 20 |
| qwen35_9b | S0 | 0/56 | 0 |
| qwen35_9b | S1 | 18/56 | 18 |
| qwen35_9b | A1_AMOUNT | 6/56 | 6 |
| qwen35_9b | A2_AMOUNT | 17/56 | 12 |
| qwen35_9b | A2_ON_S0 | 0/56 | 0 |
| qwen35_9b | A1_REPEATED_ON_S1 | 7/56 | 7 |
| qwen35_27b | S0 | 0/22 | 0 |
| qwen35_27b | S1 | 14/22 | 14 |
| qwen35_27b | A1_AMOUNT | 6/22 | 6 |
| qwen35_27b | A2_AMOUNT | 6/22 | 6 |
| qwen35_27b | A2_ON_S0 | 3/22 | 3 |
| qwen35_27b | A1_REPEATED_ON_S1 | 0/22 | 0 |


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/W0/cases.jsonl`  
Source hash: `37a25b5dda9bcbb0d2b5981129abc5fd00e20519a733d4f39eb7da52f4a7619d`  
Rows / metric names: b01/b06_correct, numeric_class, numeric_signatures; 描述性聚合，原表没有分类频率CI.


## 9. W1 Target-Semantic Controls


96 个相同程序/16 个生成家族；每模型 4×3×96=1,152 请求，三模型共3,456。每项正确数来自固定评分，不删除退化数值程序。CI 以16家族聚类。下表 S1 行即 S1 正文主表，并完整保留 S0/S2。

| Model | Target | T1 correct/96; % [CI]; families | T2 correct/96; % [CI]; families | T3 correct/96; % [CI]; families | T4 correct/96; % [CI]; families |
| --- | --- | --- | --- | --- | --- |
| qwen35_4b | S0 | 15/96; 15.62% [12.5000, 18.7500]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 |
| qwen35_4b | S1 | 37/96; 38.54% [31.2500, 44.7917]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 |
| qwen35_4b | S2 | 68/96; 70.83% [62.5000, 79.1667]%; F=16 | 69/96; 71.88% [65.6250, 78.1250]%; F=16 | 66/96; 68.75% [61.4583, 76.0417]%; F=16 | 66/96; 68.75% [61.4583, 76.0417]%; F=16 |
| qwen35_9b | S0 | 47/96; 48.96% [45.8333, 52.0833]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 |
| qwen35_9b | S1 | 0/96; 0.00% [0.0000, 0.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 |
| qwen35_9b | S2 | 92/96; 95.83% [92.7083, 98.9583]%; F=16 | 88/96; 91.67% [87.5000, 95.8333]%; F=16 | 75/96; 78.12% [72.9167, 83.3333]%; F=16 | 74/96; 77.08% [71.8750, 83.3333]%; F=16 |
| qwen35_27b | S0 | 33/96; 34.38% [33.3333, 36.4583]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 |
| qwen35_27b | S1 | 0/96; 0.00% [0.0000, 0.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 |
| qwen35_27b | S2 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 | 96/96; 100.00% [100.0000, 100.0000]%; F=16 |


Source artifact: `./phase7/gpt_review_snapshot_8210943/04_B2_TARGET_CONTRACT_RESULTS_SUMMARY.csv`  
Source hash: `cd57b613cdd5e49ae56d03c2c11d165a876262ae756d7374e83ff69f1265d287`  
Rows / metric names: 全部36模型×条件统计；CI 未重新计算.


### 输出值分布：非互斥终态匹配与互斥输出分类

terminal S2-match 为非互斥频率（可能本来就是 gold 或与其他状态同值）；后续分类先正确，再错误其他合法 state，再其他数值/null/invalid，互斥。避免把数值碰撞当作 Wrong-State Selection。

| Model | condition | Units | terminal S2-match | correct | wrong other legal state | other numeric | null | invalid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen35_4b | T1_S0 | 96 programs / 16 families | 43/96 | 15/96 | 75/96 | 6/96 | 0/96 | 0/96 |
| qwen35_4b | T1_S1 | 96 programs / 16 families | 48/96 | 37/96 | 48/96 | 11/96 | 0/96 | 0/96 |
| qwen35_4b | T1_S2 | 96 programs / 16 families | 68/96 | 68/96 | 24/96 | 4/96 | 0/96 | 0/96 |
| qwen35_4b | T2_S0 | 96 programs / 16 families | 33/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_4b | T2_S1 | 96 programs / 16 families | 0/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_4b | T2_S2 | 96 programs / 16 families | 69/96 | 69/96 | 11/96 | 16/96 | 0/96 | 0/96 |
| qwen35_4b | T3_S0 | 96 programs / 16 families | 33/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_4b | T3_S1 | 96 programs / 16 families | 0/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_4b | T3_S2 | 96 programs / 16 families | 66/96 | 66/96 | 13/96 | 17/96 | 0/96 | 0/96 |
| qwen35_4b | T4_S0 | 96 programs / 16 families | 33/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_4b | T4_S1 | 96 programs / 16 families | 0/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_4b | T4_S2 | 96 programs / 16 families | 66/96 | 66/96 | 13/96 | 17/96 | 0/96 | 0/96 |
| qwen35_9b | T1_S0 | 96 programs / 16 families | 78/96 | 47/96 | 46/96 | 3/96 | 0/96 | 0/96 |
| qwen35_9b | T1_S1 | 96 programs / 16 families | 95/96 | 0/96 | 95/96 | 1/96 | 0/96 | 0/96 |
| qwen35_9b | T1_S2 | 96 programs / 16 families | 92/96 | 92/96 | 0/96 | 4/96 | 0/96 | 0/96 |
| qwen35_9b | T2_S0 | 96 programs / 16 families | 33/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_9b | T2_S1 | 96 programs / 16 families | 0/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_9b | T2_S2 | 96 programs / 16 families | 88/96 | 88/96 | 0/96 | 8/96 | 0/96 | 0/96 |
| qwen35_9b | T3_S0 | 96 programs / 16 families | 33/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_9b | T3_S1 | 96 programs / 16 families | 0/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_9b | T3_S2 | 96 programs / 16 families | 75/96 | 75/96 | 0/96 | 21/96 | 0/96 | 0/96 |
| qwen35_9b | T4_S0 | 96 programs / 16 families | 33/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_9b | T4_S1 | 96 programs / 16 families | 0/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_9b | T4_S2 | 96 programs / 16 families | 74/96 | 74/96 | 0/96 | 22/96 | 0/96 | 0/96 |
| qwen35_27b | T1_S0 | 96 programs / 16 families | 96/96 | 33/96 | 63/96 | 0/96 | 0/96 | 0/96 |
| qwen35_27b | T1_S1 | 96 programs / 16 families | 96/96 | 0/96 | 96/96 | 0/96 | 0/96 | 0/96 |
| qwen35_27b | T1_S2 | 96 programs / 16 families | 96/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_27b | T2_S0 | 96 programs / 16 families | 33/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_27b | T2_S1 | 96 programs / 16 families | 0/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_27b | T2_S2 | 96 programs / 16 families | 96/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_27b | T3_S0 | 96 programs / 16 families | 33/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_27b | T3_S1 | 96 programs / 16 families | 0/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_27b | T3_S2 | 96 programs / 16 families | 96/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_27b | T4_S0 | 96 programs / 16 families | 33/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_27b | T4_S1 | 96 programs / 16 families | 0/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |
| qwen35_27b | T4_S2 | 96 programs / 16 families | 96/96 | 96/96 | 0/96 | 0/96 | 0/96 | 0/96 |


Source artifact: `./phase7/gpt_review_snapshot_8210943/04_B2_TARGET_CONTRACT_RESULTS.csv`  
Source hash: `bf63f33eeaa0127123ecd2dc0dff9a969b059ed23474f8bd7f72c61ea89b663a`  
Rows / metric names: prediction/s0/s1/s2/correct/valid；分类频率为描述性，未存CI.


### 非退化与配对对比（已有统计）


| Model | Condition | subset | correct/programs | families | accuracy [CI] |
| --- | --- | --- | --- | --- | --- |
| qwen35_4b | T1_S0 | S1_NE_S2 | 15/96 | 16 | 15.62% [12.5000, 18.7500]% |
| qwen35_4b | T1_S1 | S1_NE_S2 | 37/96 | 16 | 38.54% [31.2500, 44.7917]% |
| qwen35_4b | T1_S2 | S1_NE_S2 | 68/96 | 16 | 70.83% [62.5000, 79.1667]% |
| qwen35_4b | T2_S0 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_4b | T2_S1 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_4b | T2_S2 | S1_NE_S2 | 69/96 | 16 | 71.88% [65.6250, 78.1250]% |
| qwen35_4b | T3_S0 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_4b | T3_S1 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_4b | T3_S2 | S1_NE_S2 | 66/96 | 16 | 68.75% [61.4583, 76.0417]% |
| qwen35_4b | T4_S0 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_4b | T4_S1 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_4b | T4_S2 | S1_NE_S2 | 66/96 | 16 | 68.75% [61.4583, 76.0417]% |
| qwen35_9b | T1_S0 | S1_NE_S2 | 47/96 | 16 | 48.96% [45.8333, 52.0833]% |
| qwen35_9b | T1_S1 | S1_NE_S2 | 0/96 | 16 | 0.00% [0.0000, 0.0000]% |
| qwen35_9b | T1_S2 | S1_NE_S2 | 92/96 | 16 | 95.83% [92.7083, 98.9583]% |
| qwen35_9b | T2_S0 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_9b | T2_S1 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_9b | T2_S2 | S1_NE_S2 | 88/96 | 16 | 91.67% [87.5000, 95.8333]% |
| qwen35_9b | T3_S0 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_9b | T3_S1 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_9b | T3_S2 | S1_NE_S2 | 75/96 | 16 | 78.12% [72.9167, 83.3333]% |
| qwen35_9b | T4_S0 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_9b | T4_S1 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_9b | T4_S2 | S1_NE_S2 | 74/96 | 16 | 77.08% [71.8750, 83.3333]% |
| qwen35_27b | T1_S0 | S1_NE_S2 | 33/96 | 16 | 34.38% [33.3333, 36.4583]% |
| qwen35_27b | T1_S1 | S1_NE_S2 | 0/96 | 16 | 0.00% [0.0000, 0.0000]% |
| qwen35_27b | T1_S2 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_27b | T2_S0 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_27b | T2_S1 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_27b | T2_S2 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_27b | T3_S0 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_27b | T3_S1 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_27b | T3_S2 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_27b | T4_S0 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_27b | T4_S1 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |
| qwen35_27b | T4_S2 | S1_NE_S2 | 96/96 | 16 | 100.00% [100.0000, 100.0000]% |


Source artifact: `./phase7/gpt_review_snapshot_8210943/04b_B2_NONDEGENERATE_SUMMARY.csv`  
Source hash: `e8257e4cbb60447d934efdf6a82bd141f68ad19a5dff185ca6ab4aacd2e9943a`  
Rows / metric names: S1_NE_S2，全部条件，worlds字段在这里实际为program families.


| Model | Target | contrast | N/families | paired Δ [95% CI] |
| --- | --- | --- | --- | --- |
| qwen35_4b | S0 | T2 - T1 | 96/16 | 84.38% [81.2500, 87.5000]% |
| qwen35_4b | S0 | T3 - T1 | 96/16 | 84.38% [81.2500, 87.5000]% |
| qwen35_4b | S0 | T4 - T1 | 96/16 | 84.38% [81.2500, 87.5000]% |
| qwen35_4b | S1 | T2 - T1 | 96/16 | 61.46% [55.2083, 68.7500]% |
| qwen35_4b | S1 | T3 - T1 | 96/16 | 61.46% [55.2083, 68.7500]% |
| qwen35_4b | S1 | T4 - T1 | 96/16 | 61.46% [55.2083, 68.7500]% |
| qwen35_4b | S2 | T2 - T1 | 96/16 | 1.04% [-5.2083, 8.3333]% |
| qwen35_4b | S2 | T3 - T1 | 96/16 | -2.08% [-7.2917, 3.1250]% |
| qwen35_4b | S2 | T4 - T1 | 96/16 | -2.08% [-7.2917, 3.1250]% |
| qwen35_9b | S0 | T2 - T1 | 96/16 | 51.04% [47.9167, 54.1667]% |
| qwen35_9b | S0 | T3 - T1 | 96/16 | 51.04% [47.9167, 54.1667]% |
| qwen35_9b | S0 | T4 - T1 | 96/16 | 51.04% [47.9167, 54.1667]% |
| qwen35_9b | S1 | T2 - T1 | 96/16 | 100.00% [100.0000, 100.0000]% |
| qwen35_9b | S1 | T3 - T1 | 96/16 | 100.00% [100.0000, 100.0000]% |
| qwen35_9b | S1 | T4 - T1 | 96/16 | 100.00% [100.0000, 100.0000]% |
| qwen35_9b | S2 | T2 - T1 | 96/16 | -4.17% [-8.3333, 0.0000]% |
| qwen35_9b | S2 | T3 - T1 | 96/16 | -17.71% [-22.9167, -12.5000]% |
| qwen35_9b | S2 | T4 - T1 | 96/16 | -18.75% [-23.9583, -13.5417]% |
| qwen35_27b | S0 | T2 - T1 | 96/16 | 65.62% [63.5417, 66.6667]% |
| qwen35_27b | S0 | T3 - T1 | 96/16 | 65.62% [63.5417, 66.6667]% |
| qwen35_27b | S0 | T4 - T1 | 96/16 | 65.62% [63.5417, 66.6667]% |
| qwen35_27b | S1 | T2 - T1 | 96/16 | 100.00% [100.0000, 100.0000]% |
| qwen35_27b | S1 | T3 - T1 | 96/16 | 100.00% [100.0000, 100.0000]% |
| qwen35_27b | S1 | T4 - T1 | 96/16 | 100.00% [100.0000, 100.0000]% |
| qwen35_27b | S2 | T2 - T1 | 96/16 | 0.00% [0.0000, 0.0000]% |
| qwen35_27b | S2 | T3 - T1 | 96/16 | 0.00% [0.0000, 0.0000]% |
| qwen35_27b | S2 | T4 - T1 | 96/16 | 0.00% [0.0000, 0.0000]% |


Source artifact: `./phase7/gpt_review_snapshot_8210943/04a_B2_MATCHED_CONTRASTS.csv`  
Source hash: `ddf0871bc0e21262709503ea59438ea17af272a783105e5fb555ea7c270b33d3`  
Rows / metric names: 全部已存wording配对差.


W1 支持原 B2 S1 极端错误高度依赖 target specification / prompt semantics，不支持继续把原现象单独作为稳定 Wrong-State Selection 的证据。全对/全错的经验bootstrap零宽区间不是总体无不确定性。

## 10. Non-count Replication / Main Table 4


47 worlds：horizontal=34、vertical=6、depth=7。每world每模型4请求，188/模型，564总请求。状态为二元关系枚举；A1 做单轴坐标反射，A2 为 identity，S1=S2=flip(S0)。不是复杂物理运动或原生全类别L4。

| Model | DIRECT_S0 | FULL_TRANSITION | EXPLICIT_S0 | MATCHED_SHAM | paired explicit−sham | 95% CI | pairs/worlds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| qwen35_4b | 35/47; 74.47% [61.7021, 87.2340]% | 12/47; 25.53% [12.7660, 38.2979]% | 9/47; 19.15% [8.5106, 31.9149]% | 10/47; 21.28% [10.6383, 34.0426]% | -2.13% | [-19.1489, 14.8936]% | 47/47 |
| qwen35_9b | 42/47; 89.36% [78.7234, 97.8723]% | 11/47; 23.40% [12.7660, 36.1702]% | 37/47; 78.72% [65.9574, 89.3617]% | 9/47; 19.15% [8.5106, 31.9149]% | 59.57% | [40.4255, 76.5957]% | 47/47 |
| qwen35_27b | 41/47; 87.23% [76.5957, 95.7447]% | 4/47; 8.51% [2.1277, 17.0213]% | 47/47; 100.00% [100.0000, 100.0000]% | 14/47; 29.79% [17.0213, 42.5532]% | 70.21% | [57.4468, 82.9787]% | 47/47 |


Source artifact: `./phase7/gpt_review_snapshot_8210943/14_NONCOUNT_REPLICATION_SUMMARY.csv`  
Source hash: `93b3c11fe4c0573da0e7828634c4682e9fbd97747aea219538141f7b46b5f5ca`  
Rows / metric names: 全部模型四条件；correct由逐项矩阵核对.


Source artifact: `./phase7/gpt_review_snapshot_8210943/14a_NONCOUNT_MATCHED_CONTRASTS.csv`  
Source hash: `7551ea99875af87241e5f12e560713f1b3d55d1fa80b91ba3d36cbe722321dae`  
Rows / metric names: EXPLICIT_S0 - MATCHED_SHAM，已有CI.


### family 拆分（POSTHOC_DESCRIPTIVE，不是新增预定义主检验）

旧结果未保存 family 内 CI；此处只对冻结逐项正确性做事后分组，用 5,000 次 world bootstrap、seed=20260912；不改旧总表 CI，不据此选题或修改结论。小 family 与零宽区间均有限。

| Model | family | worlds | DIRECT_S0 | FULL_TRANSITION | EXPLICIT_S0 | MATCHED_SHAM | net numerator/N = paired Δ | 95% CI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen35_4b | HORIZONTAL | 34 | 30/34; 88.24% [76.4706, 97.0588]% | 5/34; 14.71% [2.9412, 26.4706]% | 8/34; 23.53% [8.8235, 38.2353]% | 4/34; 11.76% [2.9412, 23.5294]% | 4/34 = 11.76% | [-8.8235, 29.4118]% |
| qwen35_4b | VERTICAL | 6 | 5/6; 83.33% [50.0000, 100.0000]% | 1/6; 16.67% [0.0000, 50.0000]% | 0/6; 0.00% [0.0000, 0.0000]% | 0/6; 0.00% [0.0000, 0.0000]% | 0/6 = 0.00% | [0.0000, 0.0000]% |
| qwen35_4b | DEPTH | 7 | 0/7; 0.00% [0.0000, 0.0000]% | 6/7; 85.71% [57.1429, 100.0000]% | 1/7; 14.29% [0.0000, 42.8571]% | 6/7; 85.71% [57.1429, 100.0000]% | -5/7 = -71.43% | [-100.0000, -42.8571]% |
| qwen35_9b | HORIZONTAL | 34 | 30/34; 88.24% [76.4706, 97.0588]% | 6/34; 17.65% [5.8824, 29.4118]% | 32/34; 94.12% [85.2941, 100.0000]% | 7/34; 20.59% [8.8235, 35.2941]% | 25/34 = 73.53% | [55.8824, 88.2353]% |
| qwen35_9b | VERTICAL | 6 | 6/6; 100.00% [100.0000, 100.0000]% | 0/6; 0.00% [0.0000, 0.0000]% | 5/6; 83.33% [50.0000, 100.0000]% | 0/6; 0.00% [0.0000, 0.0000]% | 5/6 = 83.33% | [50.0000, 100.0000]% |
| qwen35_9b | DEPTH | 7 | 6/7; 85.71% [57.1429, 100.0000]% | 5/7; 71.43% [42.8571, 100.0000]% | 0/7; 0.00% [0.0000, 0.0000]% | 2/7; 28.57% [0.0000, 57.1429]% | -2/7 = -28.57% | [-57.1429, 0.0000]% |
| qwen35_27b | HORIZONTAL | 34 | 30/34; 88.24% [76.4706, 97.0588]% | 2/34; 5.88% [0.0000, 14.7059]% | 34/34; 100.00% [100.0000, 100.0000]% | 10/34; 29.41% [14.7059, 44.1176]% | 24/34 = 70.59% | [55.8824, 85.2941]% |
| qwen35_27b | VERTICAL | 6 | 5/6; 83.33% [50.0000, 100.0000]% | 2/6; 33.33% [0.0000, 66.6667]% | 6/6; 100.00% [100.0000, 100.0000]% | 1/6; 16.67% [0.0000, 50.0000]% | 5/6 = 83.33% | [50.0000, 100.0000]% |
| qwen35_27b | DEPTH | 7 | 6/7; 85.71% [57.1429, 100.0000]% | 0/7; 0.00% [0.0000, 0.0000]% | 7/7; 100.00% [100.0000, 100.0000]% | 3/7; 42.86% [14.2857, 85.7143]% | 4/7 = 57.14% | [14.2857, 85.7143]% |


重要family反例：9B的DEPTH Explicit S0=0/7，而Matched Sham=2/7，净差−2/7；4B DEPTH为1/7 vs 6/7。9B总体正效应主要由horizontal/vertical贡献，不能写成9B在全部非计数family均得到救援。上述分层属事后描述，不进行按成绩调prompt或重跑。

### Type-A-like：NOT_PREDEFINED / POSTHOC

Direct 对且 Full 错且 Explicit 对；conditional rate 的分母为 Direct对且Full错的world，不是47或已经被救回的Type-A-like本身。

| Model | Type-A-like seq/world | Type-A-like / total | rescue / Direct-correct-and-Full-wrong | conditional worlds | rate | posthoc 95% CI |
| --- | --- | --- | --- | --- | --- | --- |
| qwen35_4b | 8/8 | 8/47 | 8/33 | 33 | 24.24% | [9.0909, 39.3939]% |
| qwen35_9b | 31/31 | 31/47 | 31/34 | 34 | 91.18% | [79.4118, 100.0000]% |
| qwen35_27b | 40/40 | 40/47 | 40/40 | 40 | 100.00% | [100.0000, 100.0000]% |


Source artifact: `./phase7/gpt_review_snapshot_8210943/14_NONCOUNT_REPLICATION.csv`  
Source hash: `366c149ab98efa0ee3858d3e45c0edb6603f207ca56fec3dad506c2e3cb56b84`  
Rows / metric names: 原始correct；family由private gold proof.family读取，仅事后分组.


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/batches/NONCOUNT/private_gold/request_gold.jsonl`  
Source hash: `cf3e312b0c7511c3697d6b834ecb8b3b88944468ba76a1dfbe2c4cbb71428a2e`  
Rows / metric names: proof.family/s0/s1/s2 与 expected，无补造gold.


## 11. R1 Representation Probing / Main Table 5A


仅既有冻结线性probe结果。B1按world分 train/select/eval=48/16/16，每world两序列；B2按程序家族分10/3/3。所有固定层和两个锚点结果在 Appendix B 完整列出，包含常量变量不可识别与类覆盖限制。MAJORITY 与 WORD_NUMBER_BAG_PLUS_LENGTH 是实际基线；未发现独立 length-only 或 bag-only 结果，标 NOT_RUN_SEPARATE_BASELINE，不能事后声称跑过。combined surface baseline满足长度/词数字表面控制，但不能分辨其子成分贡献。

| Model | Method | Layer | correct/N | worlds | accuracy [95% CI] | unseen eval class rows | status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| qwen35_4b | MAJORITY | N/A | 10.0/32 | 16 | 31.25% [12.5000, 56.2500]% | 0 | ESTIMATED |
| qwen35_4b | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 22.0/32 | 16 | 68.75% [46.8750, 87.5000]% | 0 | ESTIMATED |
| qwen35_4b | RESIDUAL_LINEAR_RIDGE | 0 | 12.0/32 | 16 | 37.50% [12.5000, 62.5000]% | 0 | ESTIMATED |
| qwen35_4b | RESIDUAL_LINEAR_RIDGE | 4 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0 | ESTIMATED |
| qwen35_4b | RESIDUAL_LINEAR_RIDGE | 9 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0 | ESTIMATED |
| qwen35_4b | RESIDUAL_LINEAR_RIDGE | 13 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0 | ESTIMATED |
| qwen35_4b | RESIDUAL_LINEAR_RIDGE | 18 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0 | ESTIMATED |
| qwen35_4b | RESIDUAL_LINEAR_RIDGE | 22 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0 | ESTIMATED |
| qwen35_4b | RESIDUAL_LINEAR_RIDGE | 27 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0 | ESTIMATED |
| qwen35_4b | RESIDUAL_LINEAR_RIDGE | 31 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0 | ESTIMATED |
| qwen35_9b | MAJORITY | N/A | 10.0/32 | 16 | 31.25% [12.5000, 56.2500]% | 0 | ESTIMATED |
| qwen35_9b | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 22.0/32 | 16 | 68.75% [46.8750, 87.5000]% | 0 | ESTIMATED |
| qwen35_9b | RESIDUAL_LINEAR_RIDGE | 0 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0 | ESTIMATED |
| qwen35_9b | RESIDUAL_LINEAR_RIDGE | 4 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0 | ESTIMATED |
| qwen35_9b | RESIDUAL_LINEAR_RIDGE | 9 | 20.0/32 | 16 | 62.50% [37.5000, 81.2500]% | 0 | ESTIMATED |
| qwen35_9b | RESIDUAL_LINEAR_RIDGE | 13 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0 | ESTIMATED |
| qwen35_9b | RESIDUAL_LINEAR_RIDGE | 18 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0 | ESTIMATED |
| qwen35_9b | RESIDUAL_LINEAR_RIDGE | 22 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0 | ESTIMATED |
| qwen35_9b | RESIDUAL_LINEAR_RIDGE | 27 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0 | ESTIMATED |
| qwen35_9b | RESIDUAL_LINEAR_RIDGE | 31 | 20.0/32 | 16 | 62.50% [37.5000, 81.2500]% | 0 | ESTIMATED |
| qwen35_27b | MAJORITY | N/A | 10.0/32 | 16 | 31.25% [12.5000, 56.2500]% | 0 | ESTIMATED |
| qwen35_27b | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 22.0/32 | 16 | 68.75% [46.8750, 87.5000]% | 0 | ESTIMATED |
| qwen35_27b | RESIDUAL_LINEAR_RIDGE | 0 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0 | ESTIMATED |
| qwen35_27b | RESIDUAL_LINEAR_RIDGE | 9 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0 | ESTIMATED |
| qwen35_27b | RESIDUAL_LINEAR_RIDGE | 18 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0 | ESTIMATED |
| qwen35_27b | RESIDUAL_LINEAR_RIDGE | 27 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0 | ESTIMATED |
| qwen35_27b | RESIDUAL_LINEAR_RIDGE | 36 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0 | ESTIMATED |
| qwen35_27b | RESIDUAL_LINEAR_RIDGE | 45 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0 | ESTIMATED |
| qwen35_27b | RESIDUAL_LINEAR_RIDGE | 54 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0 | ESTIMATED |
| qwen35_27b | RESIDUAL_LINEAR_RIDGE | 63 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0 | ESTIMATED |


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_b1b2_20260911_v1/result_summary_20260911/R1_ALL_MODELS_ALL_RESULTS.csv`  
Source hash: `8468b3dacc757faf7234374a6e7f632dfe9a0324a8bfa516599cfe332842c007`  
Rows / metric names: B1/B01/S1/P_CHECKPOINT + same-slice baselines；all fixed layers.


全模型摘要使用同一个核心切片，不按eval挑模型/任务。best fixed-layer 仅描述该切片中已存 eval 值最大项（明确 POSTHOC_MAX，不作为验证过的最优层）；所有并列项及全部层保留。

| Model | POSTHOC_MAX fixed layers | probe correct/N | probe | surface correct/N | probe−surface Δ | eval worlds | unseen class rows |
| --- | --- | --- | --- | --- | --- | --- | --- |
| qwen35_4b | 9,22,27,31 | 22.0/32 | 68.75% | 22.0/32 = 68.75% | 0.00% | 16 | 0 |
| qwen35_9b | 27 | 22.0/32 | 68.75% | 22.0/32 = 68.75% | 0.00% | 16 | 0 |
| qwen35_27b | 18,27,36,54,63 | 18.0/32 | 56.25% | 22.0/32 = 68.75% | -12.50% | 16 | 0 |


当前probe没有建立稳定超越简单表面基线的状态表示证据；个别正差不代表跨变量、层和模型的一致优势，更不是因果使用。固定层读出失败也不能证明不存在可读表征。

## 12. I2 Counterfactual Interchange / Main Table 5B


Qwen3.5-9B；16个冻结pair、10个程序家族；8层×3锚点×16pair=384主干预，实际384返回，CF argmax hit=0/384。程序对不是视觉world。统计中的world_cluster_id实际是程序家族。每个主网格单元16pair/10家族。

| Layer | CHECKPOINT CF hit | A2-end CF hit | QUERY CF hit |
| --- | --- | --- | --- |
| 0 | 0/16; F=10 | 0/16; F=10 | 0/16; F=10 |
| 4 | 0/16; F=10 | 0/16; F=10 | 0/16; F=10 |
| 9 | 0/16; F=10 | 0/16; F=10 | 0/16; F=10 |
| 13 | 0/16; F=10 | 0/16; F=10 | 0/16; F=10 |
| 18 | 0/16; F=10 | 0/16; F=10 | 0/16; F=10 |
| 22 | 0/16; F=10 | 0/16; F=10 | 0/16; F=10 |
| 27 | 0/16; F=10 | 0/16; F=10 | 0/16; F=10 |
| 31 | 0/16; F=10 | 0/16; F=10 | 0/16; F=10 |


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/W2/I2_LOGPROB_DIAGNOSTICS.csv`  
Source hash: `d5d109510caec1dd9832c41bbc52294c4c97d5fe7ac3f84939757a050a4deb6a`  
Rows / metric names: control=PRIMARY, depth0–7 × anchors；CF整JSON候选.


上述24格CF命中的原有family-bootstrap区间均为[0,0]，来自全零经验样本，不证明总体CF成功率为零。

| metric | sum(delta)/N 或 hits/N | N/families | mean | 95% family CI |
| --- | --- | --- | --- | --- |
| delta_cf_lp | 1.462551332/384 | 384/10 | 0.003808727426921621 | [-0.0345, 0.0369] |
| delta_original_gold_lp | -20.209095186/384 | 384/10 | -0.05262785204749084 | [-0.0873, -0.0162] |
| delta_donor_final_lp | 6.596495041/384 | 384/10 | 0.01717837250230758 | [-0.0151, 0.0467] |
| delta_donor_s1_lp | 7.365594004/384 | 384/10 | 0.019181234384568313 | [-0.0219, 0.0551] |
| free_answer_changed | 13.000000000/384 | 384/10 | 0.033854166666666664 | [0.0089, 0.0613] |
| cf_hit | 0.000000000/384 | 384/10 | 0.0 | [0.0000, 0.0000] |
| donor_final_copy | 24.000000000/384 | 384/10 | 0.0625 | [0.0000, 0.1875] |
| donor_s1_copy | 1.000000000/384 | 384/10 | 0.0026041666666666665 | [0.0000, 0.0078] |


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/W2/GROUP_RESULTS.csv`  
Source hash: `4501ba320bd12127f4b7cd15bad43a6fb205f5ca8f826d92ddcf3e226d94d178`  
Rows / metric names: PRIMARY 全部已存候选logprob与生成指标.


### Controls 全部类型

CF target 指该control自身预定义反事实值；不同control的CF可能不同，因此不是所有CF hit可以直接相减。同primary-CF比较另外列出。original preserved同时给保持baseline输出与命中original gold，两者不同。绝对donor-final-match不是新增复制。

| control | returned/planned | pairs | families | CF hit | baseline preserved | original gold hit | donor-final match | null | invalid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MATCHED_RANDOM_DONOR | 112/120 | 15 | 8 | 16/112 | 111/112 | 95/112 | 24/112 | 0/112 | 0/112 |
| PRIMARY | 384/384 | 16 | 10 | 0/384 | 371/384 | 336/384 | 24/384 | 0/384 | 0/384 |
| SAME_DONOR_DIFFERENT_A2 | 120/120 | 15 | 10 | 0/120 | 117/120 | 117/120 | 32/120 | 0/120 | 0/120 |
| SAME_DONOR_FINAL_DIFFERENT_S1 | 80/80 | 10 | 7 | 8/80 | 79/80 | 79/80 | 8/80 | 0/80 | 0/80 |
| SAME_S1_DIFFERENT_HISTORY | 48/56 | 7 | 5 | 0/48 | 48/48 | 48/48 | 0/48 | 0/48 | 0/48 |
| SELF | 128/128 | 16 | 10 | 112/128 | 128/128 | 112/128 | 112/128 | 0/128 | 0/128 |
| UNRELATED_POSITION | 128/128 | 16 | 10 | 0/128 | 128/128 | 112/128 | 8/128 | 0/128 | 0/128 |


same-value unrelated register：本轮I2没有该独立control，NOT_RUN；不得把I1的S0 sham当作I2控制。上表SELF和UNRELATED_POSITION等以实际control ID为准。

Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/W2/I2_LOGPROB_DIAGNOSTICS.csv`  
Source hash: `d5d109510caec1dd9832c41bbc52294c4c97d5fe7ac3f84939757a050a4deb6a`  
Rows / metric names: 所有control，planned包含技术未运行；此表为原记录描述性聚合.


| control | metric | paired N/families | mean | 95% CI |
| --- | --- | --- | --- | --- |
| MATCHED_RANDOM_DONOR | PRIMARY_CHECKPOINT_MINUS_CONTROL_SAME_PRIMARY_CF_LP | 64/6 | 0.012370565382241239 | [-0.1109, 0.0996] |
| SAME_DONOR_FINAL_DIFFERENT_S1 | PRIMARY_CHECKPOINT_MINUS_CONTROL_SAME_PRIMARY_CF_LP | 8/1 | 0.20536600349714718 | CI_NOT_AVAILABLE |
| SAME_S1_DIFFERENT_HISTORY | PRIMARY_CHECKPOINT_MINUS_CONTROL_SAME_PRIMARY_CF_LP | 48/5 | 0.015831855443082077 | [-0.0259, 0.0431] |
| SELF | PRIMARY_CHECKPOINT_MINUS_CONTROL_SAME_PRIMARY_CF_LP | 24/3 | -0.07618169673973323 | [-0.2634, 0.0215] |
| UNRELATED_POSITION | PRIMARY_CHECKPOINT_MINUS_CONTROL_SAME_PRIMARY_CF_LP | 128/10 | 0.02316638929145398 | [-0.0351, 0.0675] |


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/W2/same_target_closure/MATCHED_CONTROL_RESULTS.csv`  
Source hash: `90ef651fcf50fc96432e664f112e935f1d83dd402ec4672fcc082ea3c4022918`  
Rows / metric names: 仅已保存相同primary-CF候选的对比.


16条技术不等价控制没有补齐：固定一次复核后仍有一个context cached/uncached输出不一致（11 vs 12，旧记录最小top2 margin为0），保留NOT_RUN_ENGINE_EQUIVALENCE_UNRESOLVED。主384全部返回，这16条缺口不减少主384分母，但削弱匹配控制闭合。240条历史记录缺少可比较的同primary-CF候选概率（含未运行/未保存），不补造。负结论只限冻结单token映射。

Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/W2/technical_followup/ACCEPTANCE.json`  
Source hash: `a4ad9e3214146ee31e48695e53d2a76a1f27e3fd7965687a2de4d907f0c3c225`  
Rows / metric names: 固定技术复核状态.


## 13. I1 LOCALIZE：完整32窗口（附录级探索）


9B LOCALIZE：64个A/B序列、41个world；8个block [0,5,9,14,19,22,26,31] ×4个位置 ×3donor。planned=6144，returned=5088；704无合格success donor、352引擎不等价。原分区按80world哈希排序前60% LOCALIZE（48world），后40% SELECT（32world）；A/B子集不是全部分区world。主A同world配对仅25序列/20world。

下面每窗口的 informative/sham/specific 均在同一主A匹配子集，先同world内平均再world等权；specific CI沿用原WINDOW_SUMMARY。rescue/harm/null/invalid是主A informative可返回记录；donor-copy是success donor下可识别A/B记录的绝对匹配，分母另列。不能用这些分母替换主匹配N。

| Block | Anchor | info ΔLP | sham ΔLP | specific ΔLP | 95% CI | matched seq/world | info rescue | info harm | success donor-match | info null / invalid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | P_A1_END | -0.001610 | -0.004306 | 0.002696 | [-0.0290, 0.0312] | 25/20 | 1/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 1/25; W=20 / 0/25; W=20 |
| 0 | P_A2_END | -0.001107 | 0.015729 | -0.016835 | [-0.0394, 0.0051] | 25/20 | 1/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 0 | P_CONTEXT_END | -0.007092 | -0.012296 | 0.005204 | [-0.0211, 0.0328] | 25/20 | 1/25; W=20 | N/A (no eligible denominator) | 11/34; W=27 | 1/25; W=20 / 0/25; W=20 |
| 0 | P_QUERY | -0.012741 | 0.010724 | -0.023465 | [-0.0569, 0.0078] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 5 | P_A1_END | 0.000041 | -0.013612 | 0.013653 | [-0.0121, 0.0376] | 25/20 | 1/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 1/25; W=20 / 0/25; W=20 |
| 5 | P_A2_END | -0.009554 | -0.007460 | -0.002094 | [-0.0347, 0.0301] | 25/20 | 1/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 1/25; W=20 / 0/25; W=20 |
| 5 | P_CONTEXT_END | 0.002909 | -0.015594 | 0.018502 | [-0.0115, 0.0512] | 25/20 | 1/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 1/25; W=20 / 0/25; W=20 |
| 5 | P_QUERY | -0.007725 | -0.010906 | 0.003182 | [-0.0195, 0.0269] | 25/20 | 1/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 9 | P_A1_END | 0.009425 | 0.004335 | 0.005090 | [-0.0235, 0.0349] | 25/20 | 2/25; W=20 | N/A (no eligible denominator) | 11/34; W=27 | 1/25; W=20 / 0/25; W=20 |
| 9 | P_A2_END | -0.047823 | -0.026203 | -0.021620 | [-0.0613, 0.0102] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 11/34; W=27 | 1/25; W=20 / 0/25; W=20 |
| 9 | P_CONTEXT_END | 0.033206 | -0.007099 | 0.040305 | [0.0109, 0.0700] | 25/20 | 1/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 1/25; W=20 / 0/25; W=20 |
| 9 | P_QUERY | -0.006226 | -0.001790 | -0.004436 | [-0.0241, 0.0161] | 25/20 | 1/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 14 | P_A1_END | 0.002873 | 0.029332 | -0.026460 | [-0.0519, -0.0003] | 25/20 | 1/25; W=20 | N/A (no eligible denominator) | 12/34; W=27 | 1/25; W=20 / 0/25; W=20 |
| 14 | P_A2_END | -0.152398 | -0.075489 | -0.076910 | [-0.1623, -0.0048] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 9/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 14 | P_CONTEXT_END | -0.011004 | 0.016452 | -0.027456 | [-0.0498, -0.0070] | 25/20 | 1/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 2/25; W=20 / 0/25; W=20 |
| 14 | P_QUERY | 0.013651 | 0.008213 | 0.005438 | [-0.0175, 0.0281] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 19 | P_A1_END | -0.007951 | -0.009769 | 0.001818 | [-0.0126, 0.0160] | 25/20 | 1/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 19 | P_A2_END | -0.018943 | -0.005286 | -0.013657 | [-0.0308, 0.0025] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 11/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 19 | P_CONTEXT_END | -0.000241 | -0.002615 | 0.002374 | [-0.0191, 0.0227] | 25/20 | 1/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 19 | P_QUERY | -0.004797 | 0.002579 | -0.007376 | [-0.0284, 0.0147] | 25/20 | 1/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 22 | P_A1_END | -0.008295 | 0.005784 | -0.014079 | [-0.0278, -0.0024] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 22 | P_A2_END | 0.006183 | -0.002741 | 0.008924 | [-0.0104, 0.0273] | 25/20 | 1/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 22 | P_CONTEXT_END | -0.008228 | -0.001462 | -0.006766 | [-0.0211, 0.0089] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 1/25; W=20 / 0/25; W=20 |
| 22 | P_QUERY | 0.005037 | 0.001665 | 0.003372 | [-0.0129, 0.0186] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 1/25; W=20 / 0/25; W=20 |
| 26 | P_A1_END | 0.000604 | -0.007602 | 0.008206 | [-0.0096, 0.0278] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 1/25; W=20 / 0/25; W=20 |
| 26 | P_A2_END | 0.005336 | -0.000164 | 0.005500 | [-0.0148, 0.0246] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 26 | P_CONTEXT_END | -0.001792 | 0.009439 | -0.011231 | [-0.0261, 0.0023] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 26 | P_QUERY | -0.000405 | -0.011473 | 0.011068 | [-0.0014, 0.0272] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 31 | P_A1_END | 0.000000 | 0.000000 | 0.000000 | [0.0000, 0.0000] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 31 | P_A2_END | 0.000000 | 0.000000 | 0.000000 | [0.0000, 0.0000] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 31 | P_CONTEXT_END | 0.000000 | 0.000000 | 0.000000 | [0.0000, 0.0000] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |
| 31 | P_QUERY | 0.000000 | 0.000000 | 0.000000 | [0.0000, 0.0000] | 25/20 | 0/25; W=20 | N/A (no eligible denominator) | 10/34; W=27 | 0/25; W=20 / 0/25; W=20 |


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/I1/reports/localize/snapshot_8209203/WINDOW_SUMMARY.csv`  
Source hash: `5be1fd21ed865ab6584678dc778d8f4309237c8e124e52d3f5357e28ba4d56c1`  
Rows / metric names: 全部32窗口specific和CI.


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/I1/reports/localize/snapshot_8209203/MATCHED_SPECIFICITY.csv`  
Source hash: `c91d050cf87314607b82966a99fef7cb80c7300b144c1a35a23923d1bc2cf19d`  
Rows / metric names: 同匹配集合informative/sham的world等权均值.


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/I1/reports/localize/snapshot_8209203/DIAGNOSTIC_MATRIX.csv`  
Source hash: `d84053bcba64aa9e7a8f94c0503726c6693f221d657fb0416eb01fe757ef3e22`  
Rows / metric names: 生成、复制、null、invalid与eligible分母.


### 冻结窗口选择规则：原文与实际代码


```text
Rank mean per-world informative-minus-sham correct logP on Type A LOCALIZE; positive mean only; top <=2 depth+anchor single-block windows; deterministic depth/anchor tiebreak.
```


```python
qualified=[s for s in summary if s['mean'] is not None and s['mean']>0]
        qualified.sort(key=lambda s:(-s['mean'],s['depth'],s['anchor']));windows=[dict(depth=s['depth'],anchor=s['anchor'],localize=s) for s in qualified[:2]]
```


实际规则：主A、同world匹配、world等权 informative−sham 的正均值排序；取最多2；并列按depth、anchor。LOCALIZE代码没有额外world数/CI显著性阈值，不应把SELECT的≥8world和校正下界>0门槛倒写成选层规则。LOCALIZE 32窗口区间未做选择校正。得到block9和block5@P_CONTEXT_END，CANDIDATE_LOCK注明先于SELECT读取；它们是候选，不是机制锁。

Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/I1/selection/CANDIDATE_LOCK.json`  
Source hash: `3b150ae6ad1c954e94644214f98a0d017b5ef9866fd908cd041bf32e36cb80a8`  
Rows / metric names: selected_before_SELECT, primary, windows.


Source artifact: `./phase7/execution_ssm_v2/i1_analyze.py`  
Source hash: `3e5689e34305acc28f4761c52dbbaacc86124133f9773b85b5f6bb23beed8ea8`  
Rows / metric names: qualified.sort / windows[:2] / SELECT checks.


## 14. I1 SELECT and NO_GO / Main Table 5C


| Block | Main Type A seq/world | specific ΔLP | 95% CI | corrected lower | free-generation rescue |
| --- | --- | --- | --- | --- | --- |
| 9 | 17/14 | 0.03565944947019618 | [-0.0034, 0.0792] | -0.008274478756337496 | 0/17; W=14 |
| 5 | 17/14 | 0.01948770543250638 | [-0.0118, 0.0506] | -0.015684638237761256 | 0/17; W=14 |


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/I1/selection/SELECT_DECISION.json`  
Source hash: `4b979943ef0dedbf274b2cbfd3939662a992c7bc8b42595ef012bf7bdb3051d7`  
Rows / metric names: windows.matched_specificity, familywise_specificity_lower.


两窗口普通95%区间都跨零；Bonferroni两窗口familywise95%的边际下界也小于零。全A标签可返回各20序列/15world，但3条原接口null/invalid单列，主有效17序列/14world，不能混用分母。

| Block | control | damage/change numerator/N | sequences | worlds | 已有95% CI |
| --- | --- | --- | --- | --- | --- |
| 9 | initial | 0/42 | 42 | 22 | [0.0000, 0.0000]% |
| 9 | protected | 0/14 | 14 | 10 | [0.0000, 0.0000]% |
| 9 | success | 0/22 | 22 | 16 | [0.0000, 0.0000]% |
| 9 | reverse answer change | 0/40 | 40 | 26 | NOT_PRECOMPUTED; descriptive zero events |
| 5 | initial | 0/42 | 42 | 22 | [0.0000, 0.0000]% |
| 5 | protected | 0/14 | 14 | 10 | [0.0000, 0.0000]% |
| 5 | success | 0/22 | 22 | 16 | [0.0000, 0.0000]% |
| 5 | reverse answer change | 0/40 | 40 | 26 | NOT_PRECOMPUTED; descriptive zero events |


零损伤bootstrap区间退化为[0,0]，不是总体风险为零；正向没有救援，反向没有破坏，不能仅由保护结果宣称“选择性”。

| Block | eligible sequences | worlds | post donor-value match | pre already matched | newly induced match |
| --- | --- | --- | --- | --- | --- |
| 9 | 26 | 20 | 10/26 | 9/26 | 1/26 |
| 5 | 26 | 20 | 9/26 | 9/26 | 0/26 |


冻结copy门槛考察绝对post匹配≤25%，不是新增复制率。因此程序判失败，但绝大多数匹配原本已存在；block9仅新增1/26，block5新增0/26。不能说干预诱发38%复制；新增数值匹配也不能自动证明复制机制。此说明不修改原gate。

| split | planned | returned | no success donor | engine unresolved | invalid/returned | null/returned | cases | worlds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL | 2596 | 2392 | 142 | 62 | 0 | 331 | 154 | 80 |
| LOCALIZE | 1400 | 1288 | 88 | 24 | 0 | 183 | 92 | 48 |
| SELECT | 1196 | 1104 | 54 | 38 | 0 | 148 | 62 | 32 |


coverage中的invalid/null为计数，分母为该行returned；合法null不自动正确，仍按各自gold；缺失不填0得分。

Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/I1/reports/selected/snapshot_8210758/DIAGNOSTIC_MATRIX.csv`  
Source hash: `bec344daec08bacf8b4aa61c655a5464cece63e8eabb79f0684204ad7274f900`  
Rows / metric names: split, query, eligibility, baseline_correct, correct, prediction, donor_value, status.


### 逐条冻结 gate 与最终判定


| Block | frozen check | passed |
| --- | --- | --- |
| 9 | all_matched_controls_returned | False |
| 9 | complete_execution | True |
| 9 | donor_copy_bounded | False |
| 9 | enough_primary_worlds | True |
| 9 | initial_damage_bounded | True |
| 9 | positive_informative | True |
| 9 | positive_specificity | False |
| 9 | positive_world_fraction | True |
| 9 | protected_damage_bounded | True |
| 9 | success_damage_bounded | True |
| 5 | all_matched_controls_returned | False |
| 5 | complete_execution | True |
| 5 | donor_copy_bounded | False |
| 5 | enough_primary_worlds | True |
| 5 | initial_damage_bounded | True |
| 5 | positive_informative | True |
| 5 | positive_specificity | False |
| 5 | positive_world_fraction | True |
| 5 | protected_damage_bounded | True |
| 5 | success_damage_bounded | True |


```json
{
  "ci": "Bonferroni 95% familywise across <=2 frozen windows; bootstrap recipient worlds",
  "informative_mean_gt": 0,
  "max_baseline_correct_initial_damage": 0.1,
  "max_baseline_correct_protected_damage": 0.1,
  "max_identifiable_donor_copy_fraction": 0.25,
  "max_success_damage": 0.1,
  "min_independent_primary_worlds": 8,
  "min_positive_world_fraction": 0.5,
  "missing_controls": "UNRESOLVED_NOT_PASS",
  "source": "Conservative numerical operationalization of qualitative guide gate; frozen before outputs, not post-hoc thresholds.",
  "specific_effect_simultaneous_lower_ci_gt": 0
}
```


free-generation rescue：观测均0/17；注意实际冻结代码并没有单独的rescue>0布尔gate，不能在报告中捏造一条原门槛。已存gate要求specific下界>0、informative均值>0、≥8主world、≥50%正效应world、匹配控制全部返回、三项damage≤10%、绝对copy≤25%。技术不等价缺口通过all_matched_controls_returned阻止GO。即使暂不使用解释受限的copy门槛，specific与技术完整性仍未通过。

```text
FINAL DECISION = NO_GO
I3 = NOT_RUN_GATE_NOT_MET
CROSS-SCALE INTERNAL VALIDATION = NOT_RUN_MECHANISM_LOCK_REQUIRED
```


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/I1/selection/SELECT_DECISION.json`  
Source hash: `4b979943ef0dedbf274b2cbfd3939662a992c7bc8b42595ef012bf7bdb3051d7`  
Rows / metric names: 完整冻结判定；未更改.


## 15. Representative Cases：固定规则的定性展示


选例不是新的实验选样：Type A案例先按指定类别限定，再以SHA256(world_id + "|" + sequence_id)最小选一例；非计数在9B Type-A-like中按SHA256(world_id)最小；W1在全部96程序中按SHA256(world_id)最小、不要求某个结果模式；I1在SELECT主有效A中按SHA256(case_id)最小，展示两个冻结窗口。规则与全部反例表同存，不按“最好看”的响应选例。

### Case 1: qwen35_9b Type A count

world=`arkitscenes:47334110`；sequence=TWO_STEP；gold S0/S1/S2=1/3/6；A1={"amount": 2, "kind": "ADD"}；A2={"amount": 3, "kind": "ADD"}。

#### B01（B07为历史S1 sham）


condition=`B01`；request_id=`ssm_80cb5e10d39c811cf9f15e2b`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new cabinets.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 3 new cabinets.
TARGET: S2
QUERY: How many cabinets are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 6}
```


Actual raw output：

```text
{"value":5}
```


#### B02（B07为历史S1 sham）


condition=`B02`；request_id=`ssm_5decbe8d053b588bdc998eb0`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
TARGET: S0
QUERY: How many cabinets are in the reference-image counting scope in state S0?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


Actual raw output：

```text
{"value":1}
```


#### B05（B07为历史S1 sham）


condition=`B05`；request_id=`ssm_0ddf40044883c5f822a94f5d`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
ORACLE INITIAL FACT: the target count in S0 is exactly 1.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new cabinets.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 3 new cabinets.
TARGET: S2
QUERY: How many cabinets are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 6}
```


Actual raw output：

```text
{"value":6}
```


#### B07（B07为历史S1 sham）


condition=`B07`；request_id=`ssm_9d91b8626910bd9ef546f8e0`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new cabinets.
STATE_NOTE: IRRELEVANT REGISTER: an unrelated bookkeeping entry is exactly 3. This is not a scene count or state update.
ACTION_2: add exactly 3 new cabinets.
TARGET: S2
QUERY: How many cabinets are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 6}
```


Actual raw output：

```text
{"value":5}
```


符合Type A：B02独立初值正确、B01最终值错误、B05显式初值恢复正确。sham不参与类别定义，原输出无论正负均保留。

Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/W0/cases.jsonl`  
Source hash: `37a25b5dda9bcbb0d2b5981129abc5fd00e20519a733d4f39eb7da52f4a7619d`  
Rows / metric names: qwen35_9b 固定哈希代表；raw及request引用在原记录内.


### Case 2: qwen35_27b Type A count

world=`arkitscenes:42899734`；sequence=INVERSE；gold S0/S1/S2=2/1/2；A1={"amount": 1, "kind": "REMOVE"}；A2={"amount": 1, "kind": "ADD"}。

#### B01（B07为历史S1 sham）


condition=`B01`；request_id=`ssm_9d907091972e1d094b202a4d`；world=`arkitscenes:42899734`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: paintings. COUNTING SCOPE: the paintings counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: remove exactly 1 counted paintings.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 1 new paintings.
TARGET: S2
QUERY: How many paintings are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 2}
```


Actual raw output：

```text
{"value":1}
```


#### B02（B07为历史S1 sham）


condition=`B02`；request_id=`ssm_3caee9ea34b880887f2bdb63`；world=`arkitscenes:42899734`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: paintings. COUNTING SCOPE: the paintings counted in the reference image, not a whole-room census.
TARGET: S0
QUERY: How many paintings are in the reference-image counting scope in state S0?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 2}
```


Actual raw output：

```text
{"value":2}
```


#### B05（B07为历史S1 sham）


condition=`B05`；request_id=`ssm_5a5d6913cbd783ac40217768`；world=`arkitscenes:42899734`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: paintings. COUNTING SCOPE: the paintings counted in the reference image, not a whole-room census.
ORACLE INITIAL FACT: the target count in S0 is exactly 2.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: remove exactly 1 counted paintings.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 1 new paintings.
TARGET: S2
QUERY: How many paintings are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 2}
```


Actual raw output：

```text
{"value":2}
```


#### B07（B07为历史S1 sham）


condition=`B07`；request_id=`ssm_23a7cb4a188a6d82cfd0cd15`；world=`arkitscenes:42899734`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: paintings. COUNTING SCOPE: the paintings counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: remove exactly 1 counted paintings.
STATE_NOTE: IRRELEVANT REGISTER: an unrelated bookkeeping entry is exactly 1. This is not a scene count or state update.
ACTION_2: add exactly 1 new paintings.
TARGET: S2
QUERY: How many paintings are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 2}
```


Actual raw output：

```text
{"value":1}
```


符合Type A：B02独立初值正确、B01最终值错误、B05显式初值恢复正确。sham不参与类别定义，原输出无论正负均保留。

Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/W0/cases.jsonl`  
Source hash: `37a25b5dda9bcbb0d2b5981129abc5fd00e20519a733d4f39eb7da52f4a7619d`  
Rows / metric names: qwen35_27b 固定哈希代表；raw及request引用在原记录内.


### Case 3: Non-count operationalization gap


#### DIRECT_S0


condition=`DIRECT_S0`；request_id=`ssmv2_8b210875e488ff65a96282be`；world=`scannet:scene0604_01`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 1 个媒体块，再插入以下text；roles=["frame_0"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: current_media. REFERENCE FRAME: source_question_declared_perspective. TARGET VIEW: primary_view. Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.
All images show S0, the original observed scene.
IMAGE ORDER: 1=frame_0
TARGET: S0
Use the named state and reference frame. QUERY: Along the horizontal (left/right) axis, what is the relation of the red bbox target to the blue bbox target?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["LEFT_OF", "RIGHT_OF"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["LEFT_OF", "RIGHT_OF"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "LEFT_OF"}
```


Actual raw output：

```text
{"value": "LEFT_OF"}
```


#### FULL_TRANSITION


condition=`FULL_TRANSITION`；request_id=`ssmv2_6ad319f2064d7c7822bac75a`；world=`scannet:scene0604_01`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 1 个媒体块，再插入以下text；roles=["frame_0"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: current_media. REFERENCE FRAME: source_question_declared_perspective. TARGET VIEW: primary_view. Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.
All images show S0, the original observed scene.
IMAGE ORDER: 1=frame_0
S0 is the original frame. Action 1 produces S1. Action 2 acts on S1 to produce S2. These are coordinate-frame transformations, not new images or physical movements.
ACTION_1: Reverse only the horizontal coordinate axis of the named reference frame; preserve the objects and their identities.
ACTION_2: Leave the transformed frame and objects unchanged.
TARGET: S2
Use the named state and reference frame. QUERY: Along the horizontal (left/right) axis, what is the relation of the red bbox target to the blue bbox target?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["LEFT_OF", "RIGHT_OF"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["LEFT_OF", "RIGHT_OF"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "RIGHT_OF"}
```


Actual raw output：

```text
{"value": "LEFT_OF"}
```


#### EXPLICIT_S0


condition=`EXPLICIT_S0`；request_id=`ssmv2_bf45c2815efc6162dd83c38e`；world=`scannet:scene0604_01`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 1 个媒体块，再插入以下text；roles=["frame_0"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: current_media. REFERENCE FRAME: source_question_declared_perspective. TARGET VIEW: primary_view. Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.
All images show S0, the original observed scene.
IMAGE ORDER: 1=frame_0
ORACLE INITIAL FACT: In S0, the red bbox target has relation LEFT_OF to the blue bbox target.
S0 is the original frame. Action 1 produces S1. Action 2 acts on S1 to produce S2. These are coordinate-frame transformations, not new images or physical movements.
ACTION_1: Reverse only the horizontal coordinate axis of the named reference frame; preserve the objects and their identities.
ACTION_2: Leave the transformed frame and objects unchanged.
TARGET: S2
Use the named state and reference frame. QUERY: Along the horizontal (left/right) axis, what is the relation of the red bbox target to the blue bbox target?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["LEFT_OF", "RIGHT_OF"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["LEFT_OF", "RIGHT_OF"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "RIGHT_OF"}
```


Actual raw output：

```text
{"value": "RIGHT_OF"}
```


#### MATCHED_SHAM


condition=`MATCHED_SHAM`；request_id=`ssmv2_848ce63a85a356096d5ceb0c`；world=`scannet:scene0604_01`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 1 个媒体块，再插入以下text；roles=["frame_0"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: current_media. REFERENCE FRAME: source_question_declared_perspective. TARGET VIEW: primary_view. Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.
All images show S0, the original observed scene.
IMAGE ORDER: 1=frame_0
UNRELATED REGISTER: A separate bookkeeping entry stores the relation code LEFT_OF; it is not a fact about these objects.
S0 is the original frame. Action 1 produces S1. Action 2 acts on S1 to produce S2. These are coordinate-frame transformations, not new images or physical movements.
ACTION_1: Reverse only the horizontal coordinate axis of the named reference frame; preserve the objects and their identities.
ACTION_2: Leave the transformed frame and objects unchanged.
TARGET: S2
Use the named state and reference frame. QUERY: Along the horizontal (left/right) axis, what is the relation of the red bbox target to the blue bbox target?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["LEFT_OF", "RIGHT_OF"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["LEFT_OF", "RIGHT_OF"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "RIGHT_OF"}
```


Actual raw output：

```text
{"value": "LEFT_OF"}
```


Source artifact: `./phase7/gpt_review_snapshot_8210943/14_NONCOUNT_REPLICATION.csv`  
Source hash: `366c149ab98efa0ee3858d3e45c0edb6603f207ca56fec3dad506c2e3cb56b84`  
Rows / metric names: Case3：9B固定哈希Type-A-like，仅定性.


### Case 4: W1 同一程序的四种 S1 问法


Gold S0/S1/S2=['9', '13', '9']

#### T1


condition=`T1_S1`；request_id=`ssmv2_26b87210e46d06fda474e562`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
TARGET: S1. QUERY: What is the value of register R at the target state?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 13}
```


Actual raw output：

```text
{"value": 9}
```


Gold S0/S1/S2=['9', '13', '9']

#### T2


condition=`T2_S1`；request_id=`ssmv2_2e0d9b6a9b0547e95050afa2`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
QUERY: What is the value of register R immediately after Action 1 but before Action 2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 13}
```


Actual raw output：

```text
{"value": 13}
```


Gold S0/S1/S2=['9', '13', '9']

#### T3


condition=`T3_S1`；request_id=`ssmv2_7e9b3c53abce186c05e41acd`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
STATE DEFINITIONS: S0 is before both actions. S1 is immediately after Action 1 and before Action 2. S2 is immediately after Action 2, applied to S1.
TARGET: S1. QUERY: What is the value of register R at the target state?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 13}
```


Actual raw output：

```text
{"value": 13}
```


Gold S0/S1/S2=['9', '13', '9']

#### T4


condition=`T4_S1`；request_id=`ssmv2_86840a8352d207ce930218d9`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
STATE DEFINITIONS: S0 is before both actions. S1 is immediately after Action 1 and before Action 2. S2 is immediately after Action 2, applied to S1.
TARGET: S1. QUERY: What is the value of register R at the target state?
Do not return S2. Return S1 only.
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 13}
```


Actual raw output：

```text
{"value": 13}
```


Source artifact: `./phase7/gpt_review_snapshot_8210943/04_B2_TARGET_CONTRACT_RESULTS.csv`  
Source hash: `bf63f33eeaa0127123ecd2dc0dff9a969b059ed23474f8bd7f72c61ea89b663a`  
Rows / metric names: Case4 全程序哈希最小，不以问法改善幅度选样.


### Case 5: I1 SELECT no-rescue（不要求必须null）


block=5；case=88293ae5071523dc7f99c7e3；world=arkitscenes:43896339；gold=1；baseline=2；patched=2；rescue=False；null=False；invalid=False。

#### Recipient


condition=`BASE_S2`；request_id=`ssmv2_9fc7f7939aa638c5ddf0a0bf`；world=`arkitscenes:43896339`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: tables. COUNTING SCOPE: the tables counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new tables.
STATE_NOTE: No state value is supplied here.
ACTION_2: remove exactly 2 counted tables.
TARGET: S2
QUERY: How many tables are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


Actual raw output：

```text
{"value":2}
```


#### Informative donor


condition=`INFORMATIVE_S0_S2`；request_id=`ssmv2_f7aeec06db64f1e00ca701fc`；world=`arkitscenes:43896339`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: tables. COUNTING SCOPE: the tables counted in the reference image, not a whole-room census.
ORACLE INITIAL FACT: the target count in S0 is exactly 1.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new tables.
STATE_NOTE: No state value is supplied here.
ACTION_2: remove exactly 2 counted tables.
TARGET: S2
QUERY: How many tables are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


block=9；case=88293ae5071523dc7f99c7e3；world=arkitscenes:43896339；gold=1；baseline=2；patched=2；rescue=False；null=False；invalid=False。

#### Recipient


condition=`BASE_S2`；request_id=`ssmv2_9fc7f7939aa638c5ddf0a0bf`；world=`arkitscenes:43896339`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: tables. COUNTING SCOPE: the tables counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new tables.
STATE_NOTE: No state value is supplied here.
ACTION_2: remove exactly 2 counted tables.
TARGET: S2
QUERY: How many tables are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


Actual raw output：

```text
{"value":2}
```


#### Informative donor


condition=`INFORMATIVE_S0_S2`；request_id=`ssmv2_f7aeec06db64f1e00ca701fc`；world=`arkitscenes:43896339`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: tables. COUNTING SCOPE: the tables counted in the reference image, not a whole-room census.
ORACLE INITIAL FACT: the target count in S0 is exactly 1.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new tables.
STATE_NOTE: No state value is supplied here.
ACTION_2: remove exactly 2 counted tables.
TARGET: S2
QUERY: How many tables are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/I1/reports/selected/snapshot_8210758/DIAGNOSTIC_MATRIX.csv`  
Source hash: `bec344daec08bacf8b4aa61c655a5464cece63e8eabb79f0684204ad7274f900`  
Rows / metric names: Case5 SELECT主A固定case哈希；两个冻结窗口原输出.


## 16. Paper-ready Main Tables：正文使用索引


| Table | 本文件中的完整数据 | 正文边界 |
| --- | --- | --- |
| Main Table 1 | §3 E0-A + E0-B | 所有完整模型；CI缺失显式标注；test-only另列 |
| Main Table 2 | §7 B1 Behavioral Bridge + paired rescue/harm | B01/B02/B05/B06/B07/B08/B09是核心，其他行附录 |
| Main Table 3 | §6 W0 + 下方Operationalization Gap | 跨请求条件化，不是同次内部轨迹 |
| Main Table 4 | §10 Non-count总表 | 只支持测试过的简单坐标变换 |
| Main Table 5 | §11 R1核心表 + §12 I2 + §14 SELECT | readability与causality分开，NO_GO保留 |


| Model | total sequences | B02 correct | B01 wrong given B02 correct | Type A seq/world | B05 rescue \| Type A | non-tautological rescue / eligible gap |
| --- | --- | --- | --- | --- | --- | --- |
| qwen35_4b | 160 | 104/160; W=52 | 64/104; W=51 | 35/30 | 35/35 (definition) | 35/64 |
| qwen35_9b | 160 | 100/160; W=50 | 50/100; W=37 | 50/37 | 50/50 (definition) | 50/50 |
| qwen35_27b | 160 | 96/160; W=48 | 11/96; W=8 | 11/8 | 11/11 (definition) | 11/11 |


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/W0/cases.jsonl`  
Source hash: `37a25b5dda9bcbb0d2b5981129abc5fd00e20519a733d4f39eb7da52f4a7619d`  
Rows / metric names: Main Table3；各条件已有CI见§6，worlds分别指出各事件世界数.


## 17. Figure Data Summaries


### Figure A：Availability → Utilization → Rescue

使用Main Table3完整整数计数；事件可视化不是模型内部流程追踪，条件化CI见§6。

### Figure B：Explicit-state vs sham paired effects

Count 的历史B05−B07不是位置/状态匹配对照（S0动作前 vs S1动作后），仅附录描述；不能与新版S0 matched sham等同。以下count差为新增POSTHOC_DESCRIPTIVE聚合，CI算法见§10；非count沿用已存配对CI。

| Model | contrast | net/N | worlds | effect | 95% CI | status |
| --- | --- | --- | --- | --- | --- | --- |
| qwen35_4b | count historical UNMATCHED B05−B07 | 61/160 | 80 | 38.12% | [26.8750, 48.7500]% | POSTHOC_DESCRIPTIVE; not role-specific proof |
| qwen35_4b | noncount matched explicit−sham | -1/47 | 47 | -2.13% | [-19.1489, 14.8936]% | EXISTING_FROZEN_STATISTIC |
| qwen35_9b | count historical UNMATCHED B05−B07 | 112/160 | 80 | 70.00% | [61.8750, 77.5000]% | POSTHOC_DESCRIPTIVE; not role-specific proof |
| qwen35_9b | noncount matched explicit−sham | 28/47 | 47 | 59.57% | [40.4255, 76.5957]% | EXISTING_FROZEN_STATISTIC |
| qwen35_27b | count historical UNMATCHED B05−B07 | 65/160 | 80 | 40.62% | [30.6250, 50.6250]% | POSTHOC_DESCRIPTIVE; not role-specific proof |
| qwen35_27b | noncount matched explicit−sham | 33/47 | 47 | 70.21% | [57.4468, 82.9787]% | EXISTING_FROZEN_STATISTIC |


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/W0/cases.jsonl`  
Source hash: `37a25b5dda9bcbb0d2b5981129abc5fd00e20519a733d4f39eb7da52f4a7619d`  
Rows / metric names: paired sameworld/sequence B05−B07（历史不匹配控制，事后统计）.


Source artifact: `./phase7/gpt_review_snapshot_8210943/14a_NONCOUNT_MATCHED_CONTRASTS.csv`  
Source hash: `7551ea99875af87241e5f12e560713f1b3d55d1fa80b91ba3d36cbe722321dae`  
Rows / metric names: noncount matched contrast.


### Figure C：W1 target semantics

使用§9完整表中的S1行：4B 37/96→96/96、9B 0/96→96/96、27B 0/96→96/96；后者均分别指T2/T3/T4，每个16家族，全部CI保留在§9。

### Figure D：Mechanism decision


| Block | LOCALIZE specific [CI] | LOC seq/world | SELECT specific [CI] | SEL seq/world | SELECT rescue | decision |
| --- | --- | --- | --- | --- | --- | --- |
| 9 | 0.04030526447713782 [0.0109, 0.0700] | 25/20 | 0.03565944947019618 [-0.0034, 0.0792] | 17/14 | 0/17 | NO_GO |
| 5 | 0.018502443269608194 [-0.0115, 0.0512] | 25/20 | 0.01948770543250638 [-0.0118, 0.0506] | 17/14 | 0/17 | NO_GO |


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/I1/selection/SELECT_DECISION.json`  
Source hash: `4b979943ef0dedbf274b2cbfd3939662a992c7bc8b42595ef012bf7bdb3051d7`  
Rows / metric names: LOCALIZE来自选层数据，不作为独立确认.


## 18. Counterevidence and Scope Boundaries


- 4B非count explicit−sham=-1/47，95% CI跨0；不能声称三模型一致正向救援。

- 9B在DEPTH中explicit=0/7、sham=2/7；非count总体优势并非每个family一致。

- 9B B06仅104/160（65%）；不能概括为只缺少S1或只要中间值都能修复。

- W1中原S1极端失败高度依赖target语义；其他target反例与数值碰撞仍在。

- R1未稳定超越surface baseline；存在class coverage不足/常量变量不可识别；readability不是causal use。

- I2 0/384；ΔlogP(CF)区间跨零；16技术控制未解决，同目标概率缺口保留。

- I1 SELECT两窗口specificity下界未过0，主A救援0/17，reverse无答案破坏。

- 无损伤不等于选择性：局部干预也可能太弱、位置不对、范围不够或与实际计算不对应。

- 绝对donor值匹配不等于新增复制；本报告未因解释限制重设冻结gate。

- I3未运行；跨规模内部机制验证未运行。跨模型行为表不能替代二者。

- noncount只覆盖简单二元坐标反射+identity；不验证一般3D/embodied或复杂运动。

- 局部patch失败不能证明机制不存在，也不能证明机制一定distributed。

- 独立fact正确不等于同一次完整任务内部一定已形成并使用正确state。

- E0全量all-split与诊断发现集不等于新test；世界、序列、请求、干预次数不能互换。

- 新family和Type-A-like汇总为事后描述；不成为原主检验或按表现选择的新面板。

- 人工审核豁免不伪造人工VERIFIED；本MD没有图片，接收方不可假称重审视觉gold。

- 全对/全错bootstrap可能零宽；没有总体零风险保证，多窗口/多变量描述性比较不作统一显著性宣传。



## 19. Claim–Evidence Matrix


| Claim ID | Paper claim | Status | Primary evidence | Counterevidence | Scope |
| --- | --- | --- | --- | --- | --- |
| C1 | Models can independently recover relevant spatial facts. | SUPPORTED | §6/7 B02 correct counts and world CIs | B02未全对 | 测试的初值事实与范围 |
| C2 | Independently available facts do not guarantee successful downstream state transformation. | SUPPORTED | §6 TypeA与条件错误率 | 跨请求不证明内部持有S0 | 共同发现world |
| C3 | Explicit initial-state representations can rescue sequential reasoning. | PARTIALLY_SUPPORTED | §7 B05−B01配对救援 | 4B亦有harm/nonrescue；oracle不定位机制 | 测试任务与模型 |
| C4 | Rescue exceeds matched sham in 9B/27B for tested non-count coordinate transformations. | SUPPORTED | §10 paired Δ及CI | 4B反例；小family | 47个二元坐标world |
| C5 | Original B2 S1 failures are strongly target-prompt dependent. | SUPPORTED | §9 相同程序四问法 | 部分S2失败仍在 | 96程序/16家族 |
| C6 | The tested single-token S1 interchange mechanism is unsupported. | SUPPORTED | §12 0/384+ΔLP CI | 技术控制缺口；其他机制未排除 | 仅冻结mapping的否定性结论 |
| C7 | Tested local S0-rescue windows do not validate a selective causal interface. | SUPPORTED | §14 NO_GO、0/17 | 不能证明所有局部机制不存在 | 两个冻结位置 |
| C8 | Beyond-count evidence is bounded to tested transformations; broader 3D generalization is unproven. | PARTIALLY_SUPPORTED | §10 三模型非count及family表 | 4B无稳定优势；其他3D未测 | 仅简单坐标变换 |
| C9 | Failure is specifically due to internal state selection/binding. | UNRESOLVED | 行为提出候选问题 | 目标语义、输入使用、更新计算、patch无效未排除 | 不作为确定机制结论 |
| C10 | A compact causal state circuit has been identified. | NOT_SUPPORTED | I1 NO_GO / I2 negative | R1可读性不足与控制缺口 | 禁止正文宣称已找到电路 |


## Appendix A: Prompt Templates（实际运行文本）


### A0. SYSTEM_SSM 与媒体布局


```text
You are evaluating spatial facts from supplied observations. Use the specified reference image, scope and named state. Candidate statements are propositions to check, not observations. An irrelevant register describes a separate bookkeeping entry, not the scene. Hypothetical actions change only their named branch. Preserve the initial state and unrelated facts. If the supplied evidence does not determine the requested value, return null. Return only the requested JSON, with no reasoning or markdown, within 512 output tokens.
```


B1/W1/非count/I1/I2若system完全相同引用SYSTEM_SSM；不同system会逐例全文列出。实际user媒体先逐项呈现，再插入payload.text；具体插入实现附后。所有诊断value任务不要求reason；E0单独要求label/confidence/reason。不能把E0解释评分规则套进value exact-match实验。

Source artifact: `./SpaceConflict/research/state_binding_phase_a1/core_execution_v3/pipeline_v3.py`  
Source hash: `082346a960e52be44e4f0f47cae62455ddc601821f32eacd3cc6758aab2ab2bf`  
Rows / metric names: 实际process实现；payload媒体与text装配，未重新处理图像.


```python
    def messages(self,r):
        if set(r['payload'])!={'system','text','media'}: raise ValueError('UNSANITIZED_PAYLOAD_FIELDS')
        msgs=self.protocol.messages_for(dict(level='L1',claim_text='',media=r['payload']['media']),self.campaign['media_budget'])
        msgs[0]['content']=r['payload']['system']
        msgs[1]['content'][-1]=dict(type='text',text=r['payload']['text'])
        rendered=self.processor.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True,enable_thinking=False)
        if '<think>' in rendered and '</think>' not in rendered: raise ValueError('THINKING_MODE_OPEN')
        return msgs,rendered
```


媒体前文本前缀的真实构造如下；诊断Pipeline随后用payload.text替换最后一个text块，因此不会把旧E0的label/confidence/reason后缀附到value任务上。

```python
def messages_for(sample, budget):
    content = []
    for i, media in enumerate(sample.get('media') or [], 1):
        kind = media.get('kind', 'image')
        role = media.get('role') or f'media_{i}'
        content.append(dict(type='text', text=f'Evidence {kind} {i} ({role}):'))
        if kind == 'image':
            content.append(dict(type='image', image=media['path'], min_pixels=budget['min_pixels'], max_pixels=budget['max_pixels']))
        elif kind == 'video':
            content.append(dict(type='video', video=media['path'], nframes=budget['video_frames'], min_pixels=budget['min_pixels'], max_pixels=budget['video_max_pixels']))
        elif kind == 'video_frames':
            content.append(dict(type='video', video=media['paths'], sample_fps=media.get('sample_fps', 2.0), min_pixels=budget['min_pixels'], max_pixels=budget['video_max_pixels']))
        else:
            raise ValueError(f'UNSUPPORTED_MEDIA_KIND:{kind}')
    if sample['level'] == 'L4':
        prompt = l4_prompt(sample)
    else:
        prompt = ((sample.get('media_context', '')+'\n\n') if sample.get('media_context') else '') + (
            f"Spatial claim:\n{sample['claim_text']}\n\n"
            f"Accessible evidence: {len(sample.get('media') or [])} media item(s) supplied above.\n\n"
            'Return exactly one JSON object with this schema:\n'
            '{"label":"SUPPORTED|CONTRADICTORY|UNKNOWN","confidence":0.0,"reason":"brief explanation"}')
    content.append(dict(type='text', text=prompt + FORMAT_SUFFIX))
    return [dict(role='system', content=SYSTEM_PROMPT), dict(role='user', content=content)]
```


Source artifact: `artifacts/model_results/qwen35_scale_512_20260906/code/protocol.py`  
Source hash: `cbcf16297983bec324d49676d99e8dfe0b27bfc0dc1f2cc629b6c4879cc88e32`  
Rows / metric names: 实际诊断pipeline继承的媒体标记与插入次序.


### A1. E0：冻结输出中的真实 rendered prompts / schema


#### E0 L1 exact rendered example


sample_id=`sc_pair_000158ec29bbd385948bd1ca_neg`；media数量=1；插入次序见rendered中的Evidence标记；prompt_version=ordered_frames_bare_json_512_v1。

```text
<|im_start|>system
You are evaluating a spatial claim using only the supplied visual evidence and, when present, the stated hypothetical intervention. Classify the claim as exactly one of SUPPORTED, CONTRADICTORY, or UNKNOWN. SUPPORTED means the accessible evidence entails the claim. CONTRADICTORY means it explicitly refutes the claim. UNKNOWN means both the claim and its negation remain possible from the accessible evidence. Missing information is not negative evidence. Return JSON only.<|im_end|>
<|im_start|>user
Evidence image 1 (frame_0):<|vision_start|><|image_pad|><|vision_end|>Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.

Spatial claim:
Let entity A denote the blue bbox target, and let entity B denote the red bbox target. In the current image of the actual scene, from the perspective declared in the source question, the entity A is below the entity B.

Accessible evidence: 1 media item(s) supplied above.

Return exactly one JSON object with this schema:
{"label":"SUPPORTED|CONTRADICTORY|UNKNOWN","confidence":0.0,"reason":"brief explanation"}

Output formatting requirement: Return only the JSON object itself. Do not use Markdown, backticks, code fences, or text outside the object. Start with { and end with }. Use exactly the keys label, confidence, and reason. Your entire response, including the answer and explanation, must not exceed 512 output tokens. Be concise and finish the JSON within this limit. Output label first, then confidence, then reason. Generation stops at 512 tokens; only the retained output is scored, and any content beyond the limit is ignored.<|im_end|>
<|im_start|>assistant
<think>

</think>
```


Gold定义：源benchmark private gold的SUPPORTED/CONTRADICTORY/UNKNOWN；此处展示接口，不把正确标签加入user prompt。标签判断依据对应输入可访问证据，L4含明确干预分支。

Source artifact: `artifacts/model_results/spatial_world_state/sws_20260909_v1/e0_refresh_20260910_v3/raw/E0_existing_snapshot/qwen35_9b/predictions_000.jsonl`，line=644  
Source hash: raw_record_sha256=`837083a78e8fb248df1699e20fc11a696887b7f2aafb28f3dea2bc7077215da1`（引用冻结索引，非整文件hash）


#### E0 L2 exact rendered example


sample_id=`sc_pair_003bb2ef5e6eed13d7ab0607_neg`；media数量=1；插入次序见rendered中的Evidence标记；prompt_version=ordered_frames_bare_json_512_v1。

```text
<|im_start|>system
You are evaluating a spatial claim using only the supplied visual evidence and, when present, the stated hypothetical intervention. Classify the claim as exactly one of SUPPORTED, CONTRADICTORY, or UNKNOWN. SUPPORTED means the accessible evidence entails the claim. CONTRADICTORY means it explicitly refutes the claim. UNKNOWN means both the claim and its negation remain possible from the accessible evidence. Missing information is not negative evidence. Return JSON only.<|im_end|>
<|im_start|>user
Evidence image 1 (frame_0):<|vision_start|><|image_pad|><|vision_end|>Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.

Spatial claim:
Let entity A denote the object marked by bounding box [472, 171, 999, 857], and let entity B denote the object marked by bounding box [0, 2, 382, 993]. The entity A is to the left of the entity B in the current image of the actual scene, from the perspective declared in the source question.

Accessible evidence: 1 media item(s) supplied above.

Return exactly one JSON object with this schema:
{"label":"SUPPORTED|CONTRADICTORY|UNKNOWN","confidence":0.0,"reason":"brief explanation"}

Output formatting requirement: Return only the JSON object itself. Do not use Markdown, backticks, code fences, or text outside the object. Start with { and end with }. Use exactly the keys label, confidence, and reason. Your entire response, including the answer and explanation, must not exceed 512 output tokens. Be concise and finish the JSON within this limit. Output label first, then confidence, then reason. Generation stops at 512 tokens; only the retained output is scored, and any content beyond the limit is ignored.<|im_end|>
<|im_start|>assistant
<think>

</think>
```


Gold定义：源benchmark private gold的SUPPORTED/CONTRADICTORY/UNKNOWN；此处展示接口，不把正确标签加入user prompt。标签判断依据对应输入可访问证据，L4含明确干预分支。

Source artifact: `artifacts/model_results/spatial_world_state/sws_20260909_v1/e0_refresh_20260910_v3/raw/E0_existing_snapshot/qwen35_9b/predictions_000.jsonl`，line=646  
Source hash: raw_record_sha256=`e896e0424f8cc1c86fc41fc987981a356c3f8aeb89ac7125178944ca43d2ef5f`（引用冻结索引，非整文件hash）


#### E0 L3 exact rendered example


sample_id=`sc_pair_0054fb1f6ba7235cebfdf6a2_neg`；media数量=3；插入次序见rendered中的Evidence标记；prompt_version=ordered_frames_bare_json_512_v1。

```text
<|im_start|>system
You are evaluating a spatial claim using only the supplied visual evidence and, when present, the stated hypothetical intervention. Classify the claim as exactly one of SUPPORTED, CONTRADICTORY, or UNKNOWN. SUPPORTED means the accessible evidence entails the claim. CONTRADICTORY means it explicitly refutes the claim. UNKNOWN means both the claim and its negation remain possible from the accessible evidence. Missing information is not negative evidence. Return JSON only.<|im_end|>
<|im_start|>user
Evidence image 1 (frame_0):<|vision_start|><|image_pad|><|vision_end|>Evidence image 2 (frame_1):<|vision_start|><|image_pad|><|vision_end|>Evidence image 3 (frame_2):<|vision_start|><|image_pad|><|vision_end|>Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.

Spatial claim:
Let entity A denote the red bbox target, and let entity B denote the observer primary view. In the current image of the actual scene, from the perspective declared in the source question, the entity B is in front of the entity A.

Accessible evidence: 3 media item(s) supplied above.

Return exactly one JSON object with this schema:
{"label":"SUPPORTED|CONTRADICTORY|UNKNOWN","confidence":0.0,"reason":"brief explanation"}

Output formatting requirement: Return only the JSON object itself. Do not use Markdown, backticks, code fences, or text outside the object. Start with { and end with }. Use exactly the keys label, confidence, and reason. Your entire response, including the answer and explanation, must not exceed 512 output tokens. Be concise and finish the JSON within this limit. Output label first, then confidence, then reason. Generation stops at 512 tokens; only the retained output is scored, and any content beyond the limit is ignored.<|im_end|>
<|im_start|>assistant
<think>

</think>
```


Gold定义：源benchmark private gold的SUPPORTED/CONTRADICTORY/UNKNOWN；此处展示接口，不把正确标签加入user prompt。标签判断依据对应输入可访问证据，L4含明确干预分支。

Source artifact: `artifacts/model_results/spatial_world_state/sws_20260909_v1/e0_refresh_20260910_v3/raw/E0_existing_snapshot/qwen35_9b/predictions_000.jsonl`，line=648  
Source hash: raw_record_sha256=`98a98cc9ff22d810a81ae7f1d92c9819a2f7882ed9932b8ac5058519829c6635`（引用冻结索引，非整文件hash）


#### E0 L4 exact rendered example


sample_id=`sc_hypo3d_l4_v2_024ae9fa7a8f26c7f194:candidate_0`；media数量=5；插入次序见rendered中的Evidence标记；prompt_version=ordered_frames_bare_json_512_v1。

```text
<|im_start|>system
You are evaluating a spatial claim using only the supplied visual evidence and, when present, the stated hypothetical intervention. Classify the claim as exactly one of SUPPORTED, CONTRADICTORY, or UNKNOWN. SUPPORTED means the accessible evidence entails the claim. CONTRADICTORY means it explicitly refutes the claim. UNKNOWN means both the claim and its negation remain possible from the accessible evidence. Missing information is not negative evidence. Return JSON only.<|im_end|>
<|im_start|>user
Evidence image 1 (camera_view):<|vision_start|><|image_pad|><|vision_end|>Evidence image 2 (top_view_label):<|vision_start|><|image_pad|><|vision_end|>Evidence image 3 (top_view_no_label):<|vision_start|><|image_pad|><|vision_end|>Evidence image 4 (top_view_no_label_rotated):<|vision_start|><|image_pad|><|vision_end|>Evidence image 5 (top_view_with_label_rotated):<|vision_start|><|image_pad|><|vision_end|>Hypothetical intervention:
The towel beside the light has been removed.

Spatial claim:
After the change, there are 1 towel in the scene.

Accessible visual evidence: 5 image(s) supplied above.

Return exactly one JSON object with this schema:
{"label":"SUPPORTED|CONTRADICTORY|UNKNOWN","confidence":0.0,"reason":"brief explanation"}

Output formatting requirement: Return only the JSON object itself. Do not use Markdown, backticks, code fences, or text outside the object. Start with { and end with }. Use exactly the keys label, confidence, and reason. Your entire response, including the answer and explanation, must not exceed 512 output tokens. Be concise and finish the JSON within this limit. Output label first, then confidence, then reason. Generation stops at 512 tokens; only the retained output is scored, and any content beyond the limit is ignored.<|im_end|>
<|im_start|>assistant
<think>

</think>
```


Gold定义：源benchmark private gold的SUPPORTED/CONTRADICTORY/UNKNOWN；此处展示接口，不把正确标签加入user prompt。标签判断依据对应输入可访问证据，L4含明确干预分支。

Source artifact: `artifacts/model_results/spatial_world_state/sws_20260909_v1/e0_refresh_20260910_v3/raw/E0_existing_snapshot/qwen35_9b/predictions_000.jsonl`，line=1  
Source hash: raw_record_sha256=`7a0e998ee629aae6cc7dc0870562347068da68bc11abaa45d10dd84ef7fae4e9`（引用冻结索引，非整文件hash）


E0用greedy、512生成token；对保留前缀计分，截断本身不判无效；有效label不因reason/confidence不完整而抹去。该规则为retained_prefix_512_v1/outer_json_fence_v1，与诊断value解析器分开。各模型实际revision/decode见下表。

| Model | N | revision | decode | prompt_version |
| --- | --- | --- | --- | --- |
| gemma4_31b_it | 18934 | 842da3794eaa0b77d5f08bae87a17459d91ff475 | {"do_sample": false, "max_new_tokens": 512} | ordered_frames_bare_json_512_v1 |
| internvl35_14b | 24196 | 226b96d5912e69159abc0384cefcbd51487fdce0 | {"do_sample": false, "max_new_tokens": 512} | ordered_frames_bare_json_512_v1 |
| internvl35_8b | 24196 | 741a7d03020411e666c6109218ab71e08151ef86 | {"do_sample": false, "max_new_tokens": 512} | ordered_frames_bare_json_512_v1 |
| mimo_vl_7b_rl | 24196 | 460c34be0c6cfe79b6b311647ae9112784f80b73 | {"do_sample": false, "max_new_tokens": 512} | ordered_frames_bare_json_512_v1 |
| qwen25vl_32b | 24196 | 7cfb30d71a1f4f49a57592323337a4a4727301da | {"do_sample": false, "max_new_tokens": 512} | ordered_frames_bare_json_512_v1 |
| qwen25vl_7b | 24196 | cc594898137f460bfe9f0759e9844b3ce807cfb5 | {"do_sample": false, "max_new_tokens": 512} | ordered_frames_bare_json_512_v1 |
| qwen35_27b | 24196 | fc05daec18b0a78c049392ed2e771dde82bdf654 | {"do_sample": false, "max_new_tokens": 512} | ordered_frames_bare_json_512_v1 |
| qwen35_4b | 24196 | 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a | {"do_sample": false, "max_new_tokens": 512} | ordered_frames_bare_json_512_v1 |
| qwen35_9b | 24196 | c202236235762e1c871ad0ccb60c8ee5ba337b9a | {"do_sample": false, "max_new_tokens": 512} | ordered_frames_bare_json_512_v1 |
| qwen3vl_2b_thinking | 24196 | 33e0ad94c327808ebc7d3bbc97e78e600f1eeecd | {"do_sample": false, "max_new_tokens": 512} | ordered_frames_bare_json_512_v1 |
| qwen3vl_8b_instruct | 24196 | 0c351dd01ed87e9c1b53cbc748cba10e6187ff3b | {"do_sample": false, "max_new_tokens": 512} | ordered_frames_bare_json_512_v1 |
| qwen3vl_8b_thinking | 21055 | 92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b | {"do_sample": false, "max_new_tokens": 512} | ordered_frames_bare_json_512_v1 |


Source artifact: `artifacts/model_results/spatial_world_state/sws_20260909_v1/e0_refresh_20260910_v3_1/tables/actual_protocols.csv`  
Source hash: `65db48473bc62fdee0dcc7eefdb47d8851034a0bc735b71d8b07dd74dfaeb052`  
Rows / metric names: 实际冻结协议，不使用残留Industry max_new_tokens字段.


### A2. B01–B17 与 protected queries

核心固定实例来自Case1同一world/sequence；缺少在当前public请求中的历史复用condition会明确标注，不重构原prompt。B01/B02/B03/B05–B12/B17为正文核心或关键控制；B00/B04/B13–B16及保护为附录控制；旧B07历史版没有改写成新S0 sham。

#### B00

HISTORICAL_SOURCE_ONLY / exact public request not in this batch; no reconstructed prompt.

#### B01


condition=`B01`；request_id=`ssm_80cb5e10d39c811cf9f15e2b`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new cabinets.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 3 new cabinets.
TARGET: S2
QUERY: How many cabinets are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 6}
```


#### B02


condition=`B02`；request_id=`ssm_5decbe8d053b588bdc998eb0`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
TARGET: S0
QUERY: How many cabinets are in the reference-image counting scope in state S0?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


#### B03


condition=`B03`；request_id=`ssm_f31ec80f2a955c98dd199a48`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new cabinets.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 3 new cabinets.
TARGET: S1
QUERY: How many cabinets are in the reference-image counting scope in state S1?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 3}
```


#### B04


condition=`B04`；request_id=`ssm_580b56da2b929438b9c9f9b5`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new cabinets.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 3 new cabinets.
QUERY: Which named state is the input to ACTION_2? Return its state name.
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is one of these exact strings: ["S0", "S1", "S2"]; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["S0", "S1", "S2"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "S1"}
```


#### B05


condition=`B05`；request_id=`ssm_0ddf40044883c5f822a94f5d`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
ORACLE INITIAL FACT: the target count in S0 is exactly 1.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new cabinets.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 3 new cabinets.
TARGET: S2
QUERY: How many cabinets are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 6}
```


#### B06


condition=`B06`；request_id=`ssm_a0c37f74a3e31380f52be728`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new cabinets.
STATE_NOTE: ORACLE CHECKPOINT: the target count in S1 is exactly 3.
ACTION_2: add exactly 3 new cabinets.
TARGET: S2
QUERY: How many cabinets are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 6}
```


#### B07


condition=`B07`；request_id=`ssm_9d91b8626910bd9ef546f8e0`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new cabinets.
STATE_NOTE: IRRELEVANT REGISTER: an unrelated bookkeeping entry is exactly 3. This is not a scene count or state update.
ACTION_2: add exactly 3 new cabinets.
TARGET: S2
QUERY: How many cabinets are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 6}
```


#### B08


condition=`B08`；request_id=`ssm_dc1702a17cbea1c6a27c3eae`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SYMBOLIC PROGRAM ONLY; no image evidence is required. The target counted set initially has exactly 1 members in S0.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new members.
ACTION_2: add exactly 3 new members.
QUERY: What is the count in S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 6}
```


#### B09


condition=`B09`；request_id=`ssm_23d4bffe7fbbbcd67b7e7b70`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
EXPLICIT SYMBOLIC INPUT: state X has exactly 3 members. Apply one action to X: add exactly 3 new members.
QUERY: What is the resulting count?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 6}
```


#### B10


condition=`B10`；request_id=`ssm_a9e53a96f09d87e3460c9267`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
ORACLE COMPLETE STATE TABLE: S0=1; S1=3; S2=6.
TARGET: S0
QUERY: How many cabinets are in the reference-image counting scope in state S0?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


#### B11


condition=`B11`；request_id=`ssm_24e1e85dc376339d7ad0aaff`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
ORACLE COMPLETE STATE TABLE: S0=1; S1=3; S2=6.
TARGET: S1
QUERY: How many cabinets are in the reference-image counting scope in state S1?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 3}
```


#### B12


condition=`B12`；request_id=`ssm_98890f7813b52cae82d6f59e`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
ORACLE COMPLETE STATE TABLE: S0=1; S1=3; S2=6.
TARGET: S2
QUERY: How many cabinets are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 6}
```


#### B13


condition=`B13`；request_id=`ssm_de9607667048d72a0f7bdb6e`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
COUNTERFACTUAL SYMBOLIC INPUT: This is a separate hypothetical input, not an observation of the image.
EXPLICIT SYMBOLIC INPUT: state X has exactly 2 members. Apply one action to X: add exactly 3 new members.
QUERY: What is the resulting count?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 5}
```


#### B14


condition=`B14`；request_id=`ssm_6773423a2fd865992d80611f`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
COUNTERFACTUAL SYMBOLIC INPUT: This is a separate hypothetical input, not an observation of the image.
EXPLICIT SYMBOLIC INPUT: state X has exactly 4 members. Apply one action to X: add exactly 3 new members.
QUERY: What is the resulting count?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 7}
```


#### B15


condition=`B15`；request_id=`ssm_72869d001bdac4b26d668ff4`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new cabinets.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 3 new cabinets.
TARGET: S0
QUERY: How many cabinets are in the reference-image counting scope in state S0?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


#### B16


condition=`B16`；request_id=`ssm_678066705b3f97d4d04f12d7`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new cabinets.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 3 new cabinets.
TARGET: S2
QUERY: How many mirrors are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


#### B17


condition=`B17`；request_id=`ssm_ec6502a921fb38b069112a1f`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
Apply only the following first action to S0 to obtain S1. All other categories remain unchanged; do not recount occlusion.
ACTION_1: add exactly 2 new cabinets.
TARGET: S1
QUERY: How many cabinets are in the reference-image counting scope in state S1?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 3}
```


#### PROTECTED_PRE_SUPPLEMENT


condition=`PROTECTED_PRE_SUPPLEMENT`；request_id=`ssm_600f3cb7fe9708134c94e3fc`；world=`arkitscenes:47334110`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: cabinets. COUNTING SCOPE: the cabinets counted in the reference image, not a whole-room census.
TARGET: S0
QUERY: How many mirrors are in the reference-image counting scope in state S0?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_b1b2_20260911_v1/batches/B1/public_inputs/requests.jsonl`  
Source hash: `9ea31e1f13d8f99a24b4e7b4921ccad2cdefa1ac794517adc80a42f5817bfcc1`  
Rows / metric names: Case1同world/sequence的实际条件实例.


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_b1b2_20260911_v1/batches/B1/private_gold/request_gold.jsonl`  
Source hash: `832779655a09cac710756b120d943349cabec7bec0748a87651e0deeb6faed52`  
Rows / metric names: expected/proof；状态初值源fact，S1=A1(S0), S2=A2(S1), protected unchanged.


### A3. W1 T1–T4 × TARGET=S0/S1/S2

与Case4同一程序；下列12个真实完整prompt仅变动实际冻结的target/wording条件。gold来自同一独立符号程序计算。

#### T1_S0


condition=`T1_S0`；request_id=`ssmv2_82981f98a0adcd0ce108beb2`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
TARGET: S0. QUERY: What is the value of register R at the target state?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 9}
```


#### T2_S0


condition=`T2_S0`；request_id=`ssmv2_0377ec8d063ed8001b31c469`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
QUERY: What is the value of register R before Action 1 and before Action 2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 9}
```


#### T3_S0


condition=`T3_S0`；request_id=`ssmv2_c6b0424bdcea56de299fc02f`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
STATE DEFINITIONS: S0 is before both actions. S1 is immediately after Action 1 and before Action 2. S2 is immediately after Action 2, applied to S1.
TARGET: S0. QUERY: What is the value of register R at the target state?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 9}
```


#### T4_S0


condition=`T4_S0`；request_id=`ssmv2_f24e1b801259d8fbd7406e93`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
STATE DEFINITIONS: S0 is before both actions. S1 is immediately after Action 1 and before Action 2. S2 is immediately after Action 2, applied to S1.
TARGET: S0. QUERY: What is the value of register R at the target state?
Do not return S2. Return S0 only.
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 9}
```


#### T1_S1


condition=`T1_S1`；request_id=`ssmv2_26b87210e46d06fda474e562`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
TARGET: S1. QUERY: What is the value of register R at the target state?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 13}
```


#### T2_S1


condition=`T2_S1`；request_id=`ssmv2_2e0d9b6a9b0547e95050afa2`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
QUERY: What is the value of register R immediately after Action 1 but before Action 2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 13}
```


#### T3_S1


condition=`T3_S1`；request_id=`ssmv2_7e9b3c53abce186c05e41acd`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
STATE DEFINITIONS: S0 is before both actions. S1 is immediately after Action 1 and before Action 2. S2 is immediately after Action 2, applied to S1.
TARGET: S1. QUERY: What is the value of register R at the target state?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 13}
```


#### T4_S1


condition=`T4_S1`；request_id=`ssmv2_86840a8352d207ce930218d9`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
STATE DEFINITIONS: S0 is before both actions. S1 is immediately after Action 1 and before Action 2. S2 is immediately after Action 2, applied to S1.
TARGET: S1. QUERY: What is the value of register R at the target state?
Do not return S2. Return S1 only.
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 13}
```


#### T1_S2


condition=`T1_S2`；request_id=`ssmv2_4d57b71002f91550496b16ac`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
TARGET: S2. QUERY: What is the value of register R at the target state?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 9}
```


#### T2_S2


condition=`T2_S2`；request_id=`ssmv2_16f896977e4a5beaed11f17e`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
QUERY: What is the value of register R immediately after Action 2 has acted on the result of Action 1?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 9}
```


#### T3_S2


condition=`T3_S2`；request_id=`ssmv2_448c4ebf0b11df60dc81851a`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
STATE DEFINITIONS: S0 is before both actions. S1 is immediately after Action 1 and before Action 2. S2 is immediately after Action 2, applied to S1.
TARGET: S2. QUERY: What is the value of register R at the target state?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 9}
```


#### T4_S2


condition=`T4_S2`；request_id=`ssmv2_f70b6d01633bd59ec11756e9`；world=`ssm_symbolic_e248788c2ee70fd46ed6`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 9. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 4 new register units.
ACTION_2: remove exactly 4 counted register units.
STATE DEFINITIONS: S0 is before both actions. S1 is immediately after Action 1 and before Action 2. S2 is immediately after Action 2, applied to S1.
TARGET: S2. QUERY: What is the value of register R at the target state?
Do not return S1. Return S2 only.
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 9}
```


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/batches/W1_TARGET/public_inputs/requests.jsonl`  
Source hash: `f4d0ca5054d64c5d5c8e7fd9acf1c82f57703734ca37a9e24c9fb5ad73028147`  
Rows / metric names: same-program完整12条件实例.


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/batches/W1_TARGET/private_gold/request_gold.jsonl`  
Source hash: `8e37372ec6308b4661d81e2ebea05d19560215ea230e1b867b9f05c412bd9fb7`  
Rows / metric names: proof.program/s1/s2/expected.


### A4. Non-count 四条件 × horizontal / vertical / depth

各family选SHA256(world)最小，不按结果选。sham与explicit携带相同relation值、处于相同context区域，sham只描述无关marker并否认其属于场景；语义角色不同，不能声称token长度完全相等。gold为源直接关系S0、reflection翻转、identity保持，不用模型补gold。

State gold S0/S1/S2={"s0": "LEFT_OF", "s1": "RIGHT_OF", "s2": "RIGHT_OF"}

#### HORIZONTAL DIRECT_S0


condition=`DIRECT_S0`；request_id=`ssmv2_8b210875e488ff65a96282be`；world=`scannet:scene0604_01`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 1 个媒体块，再插入以下text；roles=["frame_0"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: current_media. REFERENCE FRAME: source_question_declared_perspective. TARGET VIEW: primary_view. Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.
All images show S0, the original observed scene.
IMAGE ORDER: 1=frame_0
TARGET: S0
Use the named state and reference frame. QUERY: Along the horizontal (left/right) axis, what is the relation of the red bbox target to the blue bbox target?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["LEFT_OF", "RIGHT_OF"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["LEFT_OF", "RIGHT_OF"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "LEFT_OF"}
```


State gold S0/S1/S2={"s0": "LEFT_OF", "s1": "RIGHT_OF", "s2": "RIGHT_OF"}

#### HORIZONTAL FULL_TRANSITION


condition=`FULL_TRANSITION`；request_id=`ssmv2_6ad319f2064d7c7822bac75a`；world=`scannet:scene0604_01`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 1 个媒体块，再插入以下text；roles=["frame_0"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: current_media. REFERENCE FRAME: source_question_declared_perspective. TARGET VIEW: primary_view. Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.
All images show S0, the original observed scene.
IMAGE ORDER: 1=frame_0
S0 is the original frame. Action 1 produces S1. Action 2 acts on S1 to produce S2. These are coordinate-frame transformations, not new images or physical movements.
ACTION_1: Reverse only the horizontal coordinate axis of the named reference frame; preserve the objects and their identities.
ACTION_2: Leave the transformed frame and objects unchanged.
TARGET: S2
Use the named state and reference frame. QUERY: Along the horizontal (left/right) axis, what is the relation of the red bbox target to the blue bbox target?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["LEFT_OF", "RIGHT_OF"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["LEFT_OF", "RIGHT_OF"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "RIGHT_OF"}
```


State gold S0/S1/S2={"s0": "LEFT_OF", "s1": "RIGHT_OF", "s2": "RIGHT_OF"}

#### HORIZONTAL EXPLICIT_S0


condition=`EXPLICIT_S0`；request_id=`ssmv2_bf45c2815efc6162dd83c38e`；world=`scannet:scene0604_01`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 1 个媒体块，再插入以下text；roles=["frame_0"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: current_media. REFERENCE FRAME: source_question_declared_perspective. TARGET VIEW: primary_view. Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.
All images show S0, the original observed scene.
IMAGE ORDER: 1=frame_0
ORACLE INITIAL FACT: In S0, the red bbox target has relation LEFT_OF to the blue bbox target.
S0 is the original frame. Action 1 produces S1. Action 2 acts on S1 to produce S2. These are coordinate-frame transformations, not new images or physical movements.
ACTION_1: Reverse only the horizontal coordinate axis of the named reference frame; preserve the objects and their identities.
ACTION_2: Leave the transformed frame and objects unchanged.
TARGET: S2
Use the named state and reference frame. QUERY: Along the horizontal (left/right) axis, what is the relation of the red bbox target to the blue bbox target?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["LEFT_OF", "RIGHT_OF"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["LEFT_OF", "RIGHT_OF"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "RIGHT_OF"}
```


State gold S0/S1/S2={"s0": "LEFT_OF", "s1": "RIGHT_OF", "s2": "RIGHT_OF"}

#### HORIZONTAL MATCHED_SHAM


condition=`MATCHED_SHAM`；request_id=`ssmv2_848ce63a85a356096d5ceb0c`；world=`scannet:scene0604_01`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 1 个媒体块，再插入以下text；roles=["frame_0"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: current_media. REFERENCE FRAME: source_question_declared_perspective. TARGET VIEW: primary_view. Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.
All images show S0, the original observed scene.
IMAGE ORDER: 1=frame_0
UNRELATED REGISTER: A separate bookkeeping entry stores the relation code LEFT_OF; it is not a fact about these objects.
S0 is the original frame. Action 1 produces S1. Action 2 acts on S1 to produce S2. These are coordinate-frame transformations, not new images or physical movements.
ACTION_1: Reverse only the horizontal coordinate axis of the named reference frame; preserve the objects and their identities.
ACTION_2: Leave the transformed frame and objects unchanged.
TARGET: S2
Use the named state and reference frame. QUERY: Along the horizontal (left/right) axis, what is the relation of the red bbox target to the blue bbox target?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["LEFT_OF", "RIGHT_OF"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["LEFT_OF", "RIGHT_OF"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "RIGHT_OF"}
```


State gold S0/S1/S2={"s0": "ABOVE", "s1": "BELOW", "s2": "BELOW"}

#### VERTICAL DIRECT_S0


condition=`DIRECT_S0`；request_id=`ssmv2_9395bb1994a81f5e1b377906`；world=`scannetpp:053a94cf68`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 1 个媒体块，再插入以下text；roles=["frame_0"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: current_media. REFERENCE FRAME: source_question_declared_perspective. TARGET VIEW: primary_view. Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.
All images show S0, the original observed scene.
IMAGE ORDER: 1=frame_0
TARGET: S0
Use the named state and reference frame. QUERY: Along the vertical (above/below) axis, what is the relation of the red bbox target to the blue bbox target?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["ABOVE", "BELOW"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["ABOVE", "BELOW"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "ABOVE"}
```


State gold S0/S1/S2={"s0": "ABOVE", "s1": "BELOW", "s2": "BELOW"}

#### VERTICAL FULL_TRANSITION


condition=`FULL_TRANSITION`；request_id=`ssmv2_83c62d5d8680d1b65ed31355`；world=`scannetpp:053a94cf68`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 1 个媒体块，再插入以下text；roles=["frame_0"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: current_media. REFERENCE FRAME: source_question_declared_perspective. TARGET VIEW: primary_view. Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.
All images show S0, the original observed scene.
IMAGE ORDER: 1=frame_0
S0 is the original frame. Action 1 produces S1. Action 2 acts on S1 to produce S2. These are coordinate-frame transformations, not new images or physical movements.
ACTION_1: Reverse only the vertical coordinate axis of the named reference frame; preserve the objects and their identities.
ACTION_2: Leave the transformed frame and objects unchanged.
TARGET: S2
Use the named state and reference frame. QUERY: Along the vertical (above/below) axis, what is the relation of the red bbox target to the blue bbox target?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["ABOVE", "BELOW"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["ABOVE", "BELOW"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "BELOW"}
```


State gold S0/S1/S2={"s0": "ABOVE", "s1": "BELOW", "s2": "BELOW"}

#### VERTICAL EXPLICIT_S0


condition=`EXPLICIT_S0`；request_id=`ssmv2_991788af378e87a2f12a179a`；world=`scannetpp:053a94cf68`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 1 个媒体块，再插入以下text；roles=["frame_0"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: current_media. REFERENCE FRAME: source_question_declared_perspective. TARGET VIEW: primary_view. Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.
All images show S0, the original observed scene.
IMAGE ORDER: 1=frame_0
ORACLE INITIAL FACT: In S0, the red bbox target has relation ABOVE to the blue bbox target.
S0 is the original frame. Action 1 produces S1. Action 2 acts on S1 to produce S2. These are coordinate-frame transformations, not new images or physical movements.
ACTION_1: Reverse only the vertical coordinate axis of the named reference frame; preserve the objects and their identities.
ACTION_2: Leave the transformed frame and objects unchanged.
TARGET: S2
Use the named state and reference frame. QUERY: Along the vertical (above/below) axis, what is the relation of the red bbox target to the blue bbox target?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["ABOVE", "BELOW"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["ABOVE", "BELOW"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "BELOW"}
```


State gold S0/S1/S2={"s0": "ABOVE", "s1": "BELOW", "s2": "BELOW"}

#### VERTICAL MATCHED_SHAM


condition=`MATCHED_SHAM`；request_id=`ssmv2_814c50a6ef448559be5c0bb1`；world=`scannetpp:053a94cf68`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 1 个媒体块，再插入以下text；roles=["frame_0"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: current_media. REFERENCE FRAME: source_question_declared_perspective. TARGET VIEW: primary_view. Source bounding-box coordinates, when written in the claim, use the normalized 0–1000 xyxy scale. Colored outlines identify only the source-annotated targets in each supplied view. frame_0 is the primary view; other frame numbers retain their original source indices.
All images show S0, the original observed scene.
IMAGE ORDER: 1=frame_0
UNRELATED REGISTER: A separate bookkeeping entry stores the relation code ABOVE; it is not a fact about these objects.
S0 is the original frame. Action 1 produces S1. Action 2 acts on S1 to produce S2. These are coordinate-frame transformations, not new images or physical movements.
ACTION_1: Reverse only the vertical coordinate axis of the named reference frame; preserve the objects and their identities.
ACTION_2: Leave the transformed frame and objects unchanged.
TARGET: S2
Use the named state and reference frame. QUERY: Along the vertical (above/below) axis, what is the relation of the red bbox target to the blue bbox target?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["ABOVE", "BELOW"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["ABOVE", "BELOW"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "BELOW"}
```


State gold S0/S1/S2={"s0": "BEHIND", "s1": "FRONT_OF", "s2": "FRONT_OF"}

#### DEPTH DIRECT_S0


condition=`DIRECT_S0`；request_id=`ssmv2_1dff2990eb316e6396802b07`；world=`ca_vqa_train:29289db3edf69519410d8855`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: reference_frame. REFERENCE FRAME: ca_vqa_reference_frame. TARGET VIEW: reference_frame:train_bundle_29289db3edf69519410d8855:record_214_frame_4. 
All images show S0, the original observed scene.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
TARGET: S0
Use the named state and reference frame. QUERY: Along the depth (front/behind) axis, what is the relation of the flower vase to the table?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["BEHIND", "FRONT_OF"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["BEHIND", "FRONT_OF"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "BEHIND"}
```


State gold S0/S1/S2={"s0": "BEHIND", "s1": "FRONT_OF", "s2": "FRONT_OF"}

#### DEPTH FULL_TRANSITION


condition=`FULL_TRANSITION`；request_id=`ssmv2_9cd9b08f60c924d6df002608`；world=`ca_vqa_train:29289db3edf69519410d8855`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: reference_frame. REFERENCE FRAME: ca_vqa_reference_frame. TARGET VIEW: reference_frame:train_bundle_29289db3edf69519410d8855:record_214_frame_4. 
All images show S0, the original observed scene.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
S0 is the original frame. Action 1 produces S1. Action 2 acts on S1 to produce S2. These are coordinate-frame transformations, not new images or physical movements.
ACTION_1: Reverse only the depth coordinate axis of the named reference frame; preserve the objects and their identities.
ACTION_2: Leave the transformed frame and objects unchanged.
TARGET: S2
Use the named state and reference frame. QUERY: Along the depth (front/behind) axis, what is the relation of the flower vase to the table?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["BEHIND", "FRONT_OF"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["BEHIND", "FRONT_OF"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "FRONT_OF"}
```


State gold S0/S1/S2={"s0": "BEHIND", "s1": "FRONT_OF", "s2": "FRONT_OF"}

#### DEPTH EXPLICIT_S0


condition=`EXPLICIT_S0`；request_id=`ssmv2_e47894e8db031058a6ef8dd1`；world=`ca_vqa_train:29289db3edf69519410d8855`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: reference_frame. REFERENCE FRAME: ca_vqa_reference_frame. TARGET VIEW: reference_frame:train_bundle_29289db3edf69519410d8855:record_214_frame_4. 
All images show S0, the original observed scene.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
ORACLE INITIAL FACT: In S0, the flower vase has relation BEHIND to the table.
S0 is the original frame. Action 1 produces S1. Action 2 acts on S1 to produce S2. These are coordinate-frame transformations, not new images or physical movements.
ACTION_1: Reverse only the depth coordinate axis of the named reference frame; preserve the objects and their identities.
ACTION_2: Leave the transformed frame and objects unchanged.
TARGET: S2
Use the named state and reference frame. QUERY: Along the depth (front/behind) axis, what is the relation of the flower vase to the table?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["BEHIND", "FRONT_OF"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["BEHIND", "FRONT_OF"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "FRONT_OF"}
```


State gold S0/S1/S2={"s0": "BEHIND", "s1": "FRONT_OF", "s2": "FRONT_OF"}

#### DEPTH MATCHED_SHAM


condition=`MATCHED_SHAM`；request_id=`ssmv2_1d4a5d7f5692e966a1b0a119`；world=`ca_vqa_train:29289db3edf69519410d8855`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
SCOPE: reference_frame. REFERENCE FRAME: ca_vqa_reference_frame. TARGET VIEW: reference_frame:train_bundle_29289db3edf69519410d8855:record_214_frame_4. 
All images show S0, the original observed scene.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
UNRELATED REGISTER: A separate bookkeeping entry stores the relation code BEHIND; it is not a fact about these objects.
S0 is the original frame. Action 1 produces S1. Action 2 acts on S1 to produce S2. These are coordinate-frame transformations, not new images or physical movements.
ACTION_1: Reverse only the depth coordinate axis of the named reference frame; preserve the objects and their identities.
ACTION_2: Leave the transformed frame and objects unchanged.
TARGET: S2
Use the named state and reference frame. QUERY: Along the depth (front/behind) axis, what is the relation of the flower vase to the table?
OUTPUT CONTRACT: Return one JSON object with only "value": one of ["BEHIND", "FRONT_OF"] or null if not determined.
Maximum 512 output tokens.
```


Output schema（实际请求字段）：

```json
{"domain": "enum", "kind": "value", "nullable": true, "values": ["BEHIND", "FRONT_OF"]}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": "FRONT_OF"}
```


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/batches/NONCOUNT/public_inputs/requests.jsonl`  
Source hash: `1b4379db699cdff77f7829abcfd5bbaa88d9f8843bd15ab4b050cf1b6fe0b360`  
Rows / metric names: 四条件×三个family实际实例，非新提示.


### A5. I2 symbolic recipient / donor


#### recipient


condition=`FINAL`；request_id=`ssm_d74032eab58f22b588ede813`；world=`ssm_symbolic_0b307b1c1464be1b7269`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 10. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: set the register value to exactly 2, replacing its previous value.
ACTION_2: add exactly 3 new register units.
TARGET: S2. QUERY: What is the value of register R at this state?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


#### donor


condition=`FINAL`；request_id=`ssm_62e04c3f8dc002f3e95e7f50`；world=`ssm_symbolic_042b59cdcfbbd6bf45bf`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 0 个媒体块，再插入以下text；roles=[]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
NON-SPATIAL SYMBOLIC REGISTER R. Its initial value in S0 is 10. Actions are cumulative; A2 acts on the result of A1.
ACTION_1: add exactly 2 new register units.
ACTION_2: remove exactly 1 counted register units.
TARGET: S2. QUERY: What is the value of register R at this state?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


该真实pair的private gold（仅供论文解释，不在模型prompt内）：

```json
{
  "recipient_program": {
    "a1": {
      "amount": 2,
      "kind": "SET"
    },
    "a2": {
      "amount": 3,
      "kind": "ADD"
    },
    "s0": 10,
    "source_type": "SYMBOLIC_CONTROL"
  },
  "recipient_s1": 2,
  "recipient_final_gold": 5,
  "donor_program": {
    "a1": {
      "amount": 2,
      "kind": "ADD"
    },
    "a2": {
      "amount": 1,
      "kind": "REMOVE"
    },
    "s0": 10,
    "source_type": "SYMBOLIC_CONTROL"
  },
  "donor_s1": 12,
  "donor_final_gold": 11,
  "expected_counterfactual": 15
}
```


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_b1b2_20260911_v1/i2_interchange_v1/private_gold/trials.jsonl`  
Source hash: `230267cc30e036c442a2f5491ea305efa944bfed564b950ad610037d4e8ad9ac`  
Rows / metric names: 首个固定PRIMARY trial gold；CF=recipient.A2(donor.S1).


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_b1b2_20260911_v1/i2_interchange_v1/public_inputs/requests.jsonl`  
Source hash: `0bb7e0043978df44aa753171faea925ee46b54e93e6ef68ec06244675468be1e`  
Rows / metric names: 按固定首个PRIMARY trial链接的实际symbolic prompts.


### A6. I1 recipient / donors / protected queries


recipient=BASE_S2，对应B01；informative=INFORMATIVE_S0_S2，对应B05；same-value sham=SHAM_S0_S2，语义即B07_MATCHED_V2，不是旧B07；success donor为另一world的历史Type C，同新split+动作类型+序列，优先不同final值再固定哈希；缺者保留未运行。reverse是B01 activation→B05 recipient，不是相反方向。S0/PROTECTED各自独立处理并用相同query donor，不能沿用S2 baseline。

#### PROTECTED BASE


condition=`BASE_PROTECTED`；request_id=`ssmv2_6cad09509d6d6092a55a9f92`；world=`arkitscenes:42897696`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: paintings. COUNTING SCOPE: the paintings counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: remove exactly 1 counted paintings.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 1 new paintings.
TARGET: S2
QUERY: How many lamps are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 2}
```


#### PROTECTED INFORMATIVE_S0


condition=`INFORMATIVE_S0_PROTECTED`；request_id=`ssmv2_b93e440ace9fd303d290599c`；world=`arkitscenes:42897696`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: paintings. COUNTING SCOPE: the paintings counted in the reference image, not a whole-room census.
ORACLE INITIAL FACT: the target count in S0 is exactly 1.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: remove exactly 1 counted paintings.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 1 new paintings.
TARGET: S2
QUERY: How many lamps are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 2}
```


#### PROTECTED SAME_VALUE_SHAM


condition=`SAME_VALUE_SHAM_PROTECTED`；request_id=`ssmv2_7dedcc06614ef6d08e5dbf9e`；world=`arkitscenes:42897696`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: paintings. COUNTING SCOPE: the paintings counted in the reference image, not a whole-room census.
UNRELATED REGISTER: its bookkeeping value is exactly 1, not the scene state.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: remove exactly 1 counted paintings.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 1 new paintings.
TARGET: S2
QUERY: How many lamps are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 2}
```


#### S0 BASE


condition=`BASE_S0`；request_id=`ssmv2_1a05fc130f438ce53dbac780`；world=`arkitscenes:42897696`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: paintings. COUNTING SCOPE: the paintings counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: remove exactly 1 counted paintings.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 1 new paintings.
TARGET: S0
QUERY: How many paintings are in the reference-image counting scope in state S0?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


#### S0 INFORMATIVE_S0


condition=`INFORMATIVE_S0_S0`；request_id=`ssmv2_016ace48a9c37e14e371df9e`；world=`arkitscenes:42897696`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: paintings. COUNTING SCOPE: the paintings counted in the reference image, not a whole-room census.
ORACLE INITIAL FACT: the target count in S0 is exactly 1.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: remove exactly 1 counted paintings.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 1 new paintings.
TARGET: S0
QUERY: How many paintings are in the reference-image counting scope in state S0?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


#### S0 SAME_VALUE_SHAM


condition=`SAME_VALUE_SHAM_S0`；request_id=`ssmv2_ded95fa1293f083355952fd6`；world=`arkitscenes:42897696`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: paintings. COUNTING SCOPE: the paintings counted in the reference image, not a whole-room census.
UNRELATED REGISTER: its bookkeeping value is exactly 1, not the scene state.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: remove exactly 1 counted paintings.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 1 new paintings.
TARGET: S0
QUERY: How many paintings are in the reference-image counting scope in state S0?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


#### S2 BASE


condition=`BASE_S2`；request_id=`ssmv2_32f57f1b33511b9a1a97b707`；world=`arkitscenes:42897696`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: paintings. COUNTING SCOPE: the paintings counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: remove exactly 1 counted paintings.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 1 new paintings.
TARGET: S2
QUERY: How many paintings are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


#### S2 INFORMATIVE_S0


condition=`INFORMATIVE_S0_S2`；request_id=`ssmv2_5ef558a68135eb4d512e942a`；world=`arkitscenes:42897696`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: paintings. COUNTING SCOPE: the paintings counted in the reference image, not a whole-room census.
ORACLE INITIAL FACT: the target count in S0 is exactly 1.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: remove exactly 1 counted paintings.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 1 new paintings.
TARGET: S2
QUERY: How many paintings are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


#### S2 SAME_VALUE_SHAM


condition=`SAME_VALUE_SHAM_S2`；request_id=`ssmv2_81e63f640296805835bdc31c`；world=`arkitscenes:42897696`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: paintings. COUNTING SCOPE: the paintings counted in the reference image, not a whole-room census.
UNRELATED REGISTER: its bookkeeping value is exactly 1, not the scene state.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: remove exactly 1 counted paintings.
STATE_NOTE: No state value is supplied here.
ACTION_2: add exactly 1 new paintings.
TARGET: S2
QUERY: How many paintings are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 1}
```


#### 实际 success donor S2（按panel原链接）


condition=`BASE_S2`；request_id=`ssmv2_53a6358969c87b7fb6e6d888`；world=`arkitscenes:42899685`。System=SYSTEM_SSM（Appendix A）。

媒体插入：user内容先按顺序插入 5 个媒体块，再插入以下text；roles=["reference_frame", "support_frame_1", "support_frame_2", "support_frame_3", "support_frame_4"]。模型processor展开后的图像token数随媒体而变，不把输入图数量等同token数。

User prompt（exact）：

```text
OBSERVED STATE S0: the supplied reference image. Support views do not add members to the counting scope.
IMAGE ORDER: 1=reference_frame, 2=support_frame_1, 3=support_frame_2, 4=support_frame_3, 5=support_frame_4
OBJECT: doors. COUNTING SCOPE: the doors counted in the reference image, not a whole-room census.
The following two actions are cumulative on one hypothetical counted set. A1 maps S0 to S1; A2 acts on S1 to produce S2, not independently on S0. The recorded S0 and all other categories remain unchanged. Only quantities are queried; do not recount occlusion after the edit.
ACTION_1: add exactly 2 new doors.
STATE_NOTE: No state value is supplied here.
ACTION_2: remove exactly 2 counted doors.
TARGET: S2
QUERY: How many doors are in the reference-image counting scope in state S2?
OUTPUT CONTRACT: Return exactly one JSON object with key "value". Its value is a nonnegative JSON integer, NOT a quoted string; use the JSON literal null, not the string "null", when undetermined. Even an undetermined answer must use the object {"value":null}, not bare null.
```


Output schema（实际请求字段）：

```json
{"domain": "count", "kind": "value", "nullable": true}
```


Gold expected（private gold，仅报告，不提供给模型）：

```json
{"value": 2}
```


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/I1/public_inputs/requests.jsonl`  
Source hash: `ba4cbb525eea0d7a9a80ddf8f9c562cd6bdf7e86d1e9aca20cb29392fcff7431`  
Rows / metric names: BASE/INFORMATIVE_S0/SHAM_S0 × S2/S0/PROTECTED + 实际success donor.


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_nextstage_v2_20260911/I1/public_inputs/panel.jsonl`  
Source hash: `3cfd3eda6cb607796a5fe0efbca145b5252eb40e2510e90323a929f89e78b216`  
Rows / metric names: 请求映射和success donor结构匹配定义.


#### Anchor 的真实token定位

在processor真实展开序列上定位，不把字符位置直接当token位置。P_CONTEXT_END=P_PRE：ACTION_1之前最后text token；P_A1_END：ACTION_1行结束前最后token；P_A2_END：ACTION_2行末；P_QUERY：OUTPUT CONTRACT之前最后token。I2 P_CHECKPOINT是STATE_NOTE行末；symbolic无STATE_NOTE时实际别名到P_A1。下列为实际运行定位函数原文。

```python
def token_anchors(pipe,batch,pres,body):
    text=pres['rendered_prompt'];tok=pipe.processor.tokenizer
    base=tok(text,add_special_tokens=False,return_offsets_mapping=True)
    actual=batch['input_ids'][0].tolist();mapping=[];j=0
    imageid=tok.convert_tokens_to_ids('<|image_pad|>')
    for tid in base['input_ids']:
        if j>=len(actual) or actual[j]!=tid:raise ValueError('EXPANDED_TOKEN_ALIGNMENT_FAILED')
        if tid==imageid:
            while j+1<len(actual) and actual[j+1]==imageid:j+=1
        mapping.append(j);j+=1
    if j!=len(actual):raise ValueError('EXPANDED_TOKEN_TAIL_MISMATCH')
    start=text.index(body)
    def boundary(marker,before=False):
        pos=body.find(marker)
        if pos<0:return None
        end=pos if before else body.find('\n',pos)
        if end<0:end=len(body)
        absolute=start+end
        inds=[i for i,(lo,hi) in enumerate(base['offset_mapping']) if hi<=absolute and hi>lo]
        return mapping[inds[-1]] if inds else None
    result={'P_PRE':boundary('ACTION_1:',True),'P_A1':boundary('ACTION_1:'),'P_CHECKPOINT':boundary('STATE_NOTE:'),
        'P_A2':boundary('ACTION_2:'),'P_QUERY':boundary('OUTPUT CONTRACT:',True)}
    aliases={}
    if result['P_CHECKPOINT'] is None and result['P_A1'] is not None:
        result['P_CHECKPOINT']=result['P_A1'];aliases['P_CHECKPOINT']='P_A1; NO_EXPLICIT_CHECKPOINT_SLOT_IN_SYMBOLIC_INPUT'
    return result,dict(base_token_ids=base['input_ids'],character_offsets=base['offset_mapping'],expanded_positions=mapping,aliases=aliases)
```


Source artifact: `./phase6/execution_ssm_internal_v1/representations.py`  
Source hash: `e722ebecc14fe5990fcf983332267d0df1b519aa9d1d61a67b831328fe5ce84c`  
Rows / metric names: token_anchors exact source.


Source artifact: `./phase7/execution_ssm_v2/i1_engine.py`  
Source hash: `7068826548e5bb9c488e1b8d82d2646728dd640a1324859c7ef43ee7f78a49c1`  
Rows / metric names: P_CONTEXT_END/P_A1_END/P_A2_END/P_QUERY 映射.


I1 patch为单个实际block output token，每个生成token都重放完整因果prefix、禁用cache；替换donor向量后继续原计算。技术门槛含cached/uncached、noop/self token等价及候选分数误差。前述记录是激活操作而非修改用户prompt来“修复答案”。

### A7. Output schemas 与 gold 定义汇总


| 模块 | 输出 | gold | reason评分 |
| --- | --- | --- | --- |
| E0 | label/confidence/reason JSON，SUPPORTED/CONTRADICTORY/UNKNOWN | 冻结benchmark标签 | 辅助judge另列，不参与这里ClaimAcc/PairAcc |
| B1/W1/I1/I2 count | {"value": nonnegative integer or null} | S0源fact，S1=A1(S0)，S2=A2(S1)；I2按donor S1与recipient A2计算CF | 不要求reason |
| Non-count | {"value": enum or null} | 源relation与固定反射/identity映射 | 不要求reason |
| B04等控制 | 具体schema见逐条件原请求 | 原private gold expected，不重新推测 | 以实际condition为准 |


512 token为生成输出上限，超出的未生成/未保留内容不评分；达到上限不自动判无效。所有保留输出按冻结解析器与typed gold评分。本文不重新运行parser。

## Appendix B: R1 全模型全固定层结果（完整关键附录）


保留全部1,365行聚合结果，不含逐样本activation。多数/combined surface/8层×2anchor均保留；空指标表示不可识别，不填0。同world层重复不构成更多world。下表selection_accuracy用于旧alpha选择，accuracy为旧eval；不能据eval改配置。

| Model | batch/condition | variable | method | layer/anchor | train/select/eval clusters | correct/N | eval worlds | accuracy [95% CI] | selection_acc | unseen classes rows | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen35_4b | B1/B01 | Z | N/A | N/A | 48/16/16 | N/A | N/A | N/A CI_NOT_AVAILABLE | N/A | N/A | STATE_VARIABLE_NOT_IDENTIFIABLE_CONSTANT_TRAIN_LABEL |
| qwen35_4b | B1/B06 | Z | N/A | N/A | 48/16/16 | N/A | N/A | N/A CI_NOT_AVAILABLE | N/A | N/A | STATE_VARIABLE_NOT_IDENTIFIABLE_CONSTANT_TRAIN_LABEL |
| qwen35_4b | B2/FINAL | Z | N/A | N/A | 10/3/3 | N/A | N/A | N/A CI_NOT_AVAILABLE | N/A | N/A | STATE_VARIABLE_NOT_IDENTIFIABLE_CONSTANT_TRAIN_LABEL |
| qwen35_4b | B2/FINAL | ENTITY | N/A | N/A | 10/3/3 | N/A | N/A | N/A CI_NOT_AVAILABLE | N/A | N/A | VARIABLE_NOT_SUPPLIED_IN_THIS_PANEL |
| qwen35_4b | B2/FINAL | PROTECTED | N/A | N/A | 10/3/3 | N/A | N/A | N/A CI_NOT_AVAILABLE | N/A | N/A | VARIABLE_NOT_SUPPLIED_IN_THIS_PANEL |
| qwen35_4b | B1/B01 | S0 | MAJORITY | N/A | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 87.5000]% | 0.40625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [37.5000, 81.2500]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 15.0/32 | 16 | 46.88% [25.0000, 68.7500]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [37.5000, 81.2500]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [40.6250, 84.3750]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [56.2500, 93.7500]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.28125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [50.0000, 93.7500]% | 0.5 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.3125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [50.0000, 93.7500]% | 0.375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.3125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [50.0000, 93.7500]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.34375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | S1 | MAJORITY | N/A | 48/16/16 | 10.0/32 | 16 | 31.25% [12.5000, 56.2500]% | 0.4375 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 22.0/32 | 16 | 68.75% [46.8750, 87.5000]% | 0.65625 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 12.0/32 | 16 | 37.50% [12.5000, 62.5000]% | 0.3125 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 7.0/32 | 16 | 21.88% [6.2500, 40.7031]% | 0.21875 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.3125 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 87.5000]% | 0.28125 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.375 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.3125 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 87.5000]% | 0.4375 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.375 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 87.5000]% | 0.4375 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.3125 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.40625 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.375 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.40625 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.375 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.375 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | MAJORITY | N/A | 48/16/16 | 11.0/32 | 16 | 34.38% [21.8750, 43.7500]% | 0.3125 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 23.0/32 | 16 | 71.88% [50.0000, 90.6250]% | 0.5625 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 9.0/32 | 16 | 28.12% [15.6250, 40.6250]% | 0.21875 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 10.0/32 | 16 | 31.25% [18.7500, 46.8750]% | 0.40625 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 9.0/32 | 16 | 28.12% [15.6250, 40.6250]% | 0.21875 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [37.5000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 11.0/32 | 16 | 34.38% [21.8750, 43.7500]% | 0.21875 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 84.3750]% | 0.46875 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 10.0/32 | 16 | 31.25% [18.7500, 43.7500]% | 0.28125 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [46.8750, 87.5000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 12.0/32 | 16 | 37.50% [28.1250, 46.8750]% | 0.25 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 23.0/32 | 16 | 71.88% [53.1250, 87.5000]% | 0.4375 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 14.0/32 | 16 | 43.75% [34.3750, 50.0000]% | 0.25 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [56.2500, 90.6250]% | 0.5625 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 13.0/32 | 16 | 40.62% [31.2500, 50.0000]% | 0.21875 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [40.6250, 78.1250]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 13.0/32 | 16 | 40.62% [31.2500, 50.0000]% | 0.25 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 17.0/32 | 16 | 53.12% [34.3750, 71.8750]% | 0.46875 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [50.0000, 93.7500]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 0.875 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 23.0/32 | 16 | 71.88% [59.3750, 84.3750]% | 0.6875 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [84.3750, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [50.0000, 93.7500]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 0.875 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | MAJORITY | N/A | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | ENTITY | MAJORITY | N/A | 48/16/16 | 4.0/32 | 16 | 12.50% [0.0000, 31.2500]% | 0.25 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.5625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 27.0/32 | 16 | 84.38% [65.6250, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [50.0000, 93.7500]% | 0.6875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 100.0000]% | 0.625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.75 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.75 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B01 | PROTECTED | MAJORITY | N/A | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.8125 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.78125 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.5625 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.6875 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [34.3750, 78.1250]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [34.3750, 81.2500]% | 0.78125 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.625 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.71875 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [34.3750, 81.2500]% | 0.71875 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 17.0/32 | 16 | 53.12% [28.1250, 75.0000]% | 0.8125 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.8125 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S0 | MAJORITY | N/A | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 87.5000]% | 0.71875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 100.0000]% | 0.75 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [34.3750, 81.2500]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 15.0/32 | 16 | 46.88% [25.0000, 68.7500]% | 0.40625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [56.2500, 93.7500]% | 0.5625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.78125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 100.0000]% | 0.78125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 87.5000]% | 0.5625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.75 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.46875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.5 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | S1 | MAJORITY | N/A | 48/16/16 | 10.0/32 | 16 | 31.25% [12.5000, 56.2500]% | 0.4375 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 96.8750]% | 0.96875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 12.0/32 | 16 | 37.50% [12.5000, 62.5000]% | 0.375 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [50.0000, 93.7500]% | 0.5625 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 100.0000]% | 0.8125 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 25.0/32 | 16 | 78.12% [59.3750, 93.7500]% | 0.8125 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [50.0000, 93.7500]% | 0.78125 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 25.0/32 | 16 | 78.12% [59.3750, 93.7500]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | MAJORITY | N/A | 48/16/16 | 11.0/32 | 16 | 34.38% [21.8750, 43.7500]% | 0.3125 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 24.0/32 | 16 | 75.00% [56.2500, 93.7500]% | 0.78125 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 7.0/32 | 16 | 21.88% [6.2500, 43.7500]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 15.0/32 | 16 | 46.88% [31.2500, 65.6250]% | 0.53125 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [56.2500, 93.7500]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 26.0/32 | 16 | 81.25% [65.6250, 93.7500]% | 0.8125 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 84.3750]% | 0.6875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [56.2500, 93.7500]% | 0.71875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 21.0/32 | 16 | 65.62% [46.8750, 84.3750]% | 0.6875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [43.7500, 81.2500]% | 0.46875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 23.0/32 | 16 | 71.88% [50.0000, 90.6250]% | 0.71875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 30.0/32 | 16 | 93.75% [84.3750, 100.0000]% | 0.96875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 25.0/32 | 16 | 78.12% [65.6250, 90.6250]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 0.96875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 23.0/32 | 16 | 71.88% [50.0000, 90.6250]% | 0.71875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | MAJORITY | N/A | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 0.90625 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | ENTITY | MAJORITY | N/A | 48/16/16 | 4.0/32 | 16 | 12.50% [0.0000, 31.2500]% | 0.25 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 12.0/32 | 16 | 37.50% [12.5000, 62.5000]% | 0.375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 100.0000]% | 0.5625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 100.0000]% | 0.5625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [50.0000, 93.7500]% | 0.625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 29.0/32 | 16 | 90.62% [75.0000, 100.0000]% | 0.75 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 100.0000]% | 0.5625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.78125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B1/B06 | PROTECTED | MAJORITY | N/A | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.8125 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 19.0/32 | 16 | 59.38% [34.3750, 81.2500]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.6875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.625 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.75 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.8125 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.5625 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.78125 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.625 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [34.3750, 81.2500]% | 0.71875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.5625 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [28.1250, 71.9531]% | 0.6875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.5625 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [28.1250, 71.8750]% | 0.6875 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.375 | 0 | ESTIMATED |
| qwen35_4b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 17.0/32 | 16 | 53.12% [31.2500, 75.0000]% | 0.8125 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S0 | MAJORITY | N/A | 10/3/3 | 0.0/18 | 3 | 0.00% [0.0000, 0.0000]% | 0.0 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 11.0/18 | 3 | 61.11% [16.6667, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 4.0/18 | 3 | 22.22% [0.0000, 50.0000]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 10/3/3 | 14.0/18 | 3 | 77.78% [66.6667, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 10/3/3 | 16.0/18 | 3 | 88.89% [83.3333, 100.0000]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 11.0/18 | 3 | 61.11% [50.0000, 66.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 16.0/18 | 3 | 88.89% [83.3333, 100.0000]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 10/3/3 | 13.0/18 | 3 | 72.22% [66.6667, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 10/3/3 | 16.0/18 | 3 | 88.89% [83.3333, 100.0000]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 13.0/18 | 3 | 72.22% [66.6667, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 11.0/18 | 3 | 61.11% [50.0000, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 10/3/3 | 11.0/18 | 3 | 61.11% [50.0000, 66.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 10/3/3 | 12.0/18 | 3 | 66.67% [50.0000, 100.0000]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 11.0/18 | 3 | 61.11% [50.0000, 66.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 11.0/18 | 3 | 61.11% [16.6667, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 10/3/3 | 12.0/18 | 3 | 66.67% [50.0000, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 10/3/3 | 10.0/18 | 3 | 55.56% [16.6667, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S1 | MAJORITY | N/A | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.3333333333333333 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 1.0/18 | 3 | 5.56% [0.0000, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | S2 | MAJORITY | N/A | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 4.0/18 | 3 | 22.22% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.2222222222222222 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 4.0/18 | 3 | 22.22% [16.6667, 33.3333]% | 0.2222222222222222 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 10/3/3 | 4.0/18 | 3 | 22.22% [0.0000, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 10/3/3 | 4.0/18 | 3 | 22.22% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.2222222222222222 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 4.0/18 | 3 | 22.22% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.2222222222222222 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 4.0/18 | 3 | 22.22% [16.6667, 33.3333]% | 0.2222222222222222 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.2777777777777778 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_4b | B2/FINAL | A1_AMOUNT | MAJORITY | N/A | 10/3/3 | 9.0/18 | 3 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 16.0/18 | 3 | 88.89% [66.6667, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 0.9444444444444444 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | MAJORITY | N/A | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.3333333333333333 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | MAJORITY | N/A | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | MAJORITY | N/A | 10/3/3 | 12.0/18 | 3 | 66.67% [66.6667, 66.6667]% | 0.6666666666666666 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_4b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | Z | N/A | N/A | 48/16/16 | N/A | N/A | N/A CI_NOT_AVAILABLE | N/A | N/A | STATE_VARIABLE_NOT_IDENTIFIABLE_CONSTANT_TRAIN_LABEL |
| qwen35_9b | B1/B06 | Z | N/A | N/A | 48/16/16 | N/A | N/A | N/A CI_NOT_AVAILABLE | N/A | N/A | STATE_VARIABLE_NOT_IDENTIFIABLE_CONSTANT_TRAIN_LABEL |
| qwen35_9b | B2/FINAL | Z | N/A | N/A | 10/3/3 | N/A | N/A | N/A CI_NOT_AVAILABLE | N/A | N/A | STATE_VARIABLE_NOT_IDENTIFIABLE_CONSTANT_TRAIN_LABEL |
| qwen35_9b | B2/FINAL | ENTITY | N/A | N/A | 10/3/3 | N/A | N/A | N/A CI_NOT_AVAILABLE | N/A | N/A | VARIABLE_NOT_SUPPLIED_IN_THIS_PANEL |
| qwen35_9b | B2/FINAL | PROTECTED | N/A | N/A | 10/3/3 | N/A | N/A | N/A CI_NOT_AVAILABLE | N/A | N/A | VARIABLE_NOT_SUPPLIED_IN_THIS_PANEL |
| qwen35_9b | B1/B01 | S0 | MAJORITY | N/A | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 87.5000]% | 0.40625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [34.3750, 81.2500]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [37.5000, 81.2500]% | 0.375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.5 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 17.0/32 | 16 | 53.12% [31.1719, 75.0000]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.46875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 23.0/32 | 16 | 71.88% [50.0000, 90.6250]% | 0.46875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 87.5000]% | 0.34375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 81.2500]% | 0.375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.34375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | S1 | MAJORITY | N/A | 48/16/16 | 10.0/32 | 16 | 31.25% [12.5000, 56.2500]% | 0.4375 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 22.0/32 | 16 | 68.75% [46.8750, 87.5000]% | 0.65625 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.15625 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.25 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.3125 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 81.2500]% | 0.4375 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [40.6250, 81.3281]% | 0.40625 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [37.5000, 81.2500]% | 0.40625 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.625 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [37.5000, 81.2500]% | 0.53125 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.5625 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.46875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.5625 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.375 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 81.2500]% | 0.5625 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | MAJORITY | N/A | 48/16/16 | 11.0/32 | 16 | 34.38% [21.8750, 43.7500]% | 0.3125 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 23.0/32 | 16 | 71.88% [50.0000, 90.6250]% | 0.5625 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 8.0/32 | 16 | 25.00% [12.5000, 37.5000]% | 0.21875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 13.0/32 | 16 | 40.62% [25.0000, 59.3750]% | 0.34375 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 12.0/32 | 16 | 37.50% [28.1250, 46.8750]% | 0.25 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [37.5000, 75.0000]% | 0.375 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 9.0/32 | 16 | 28.12% [15.6250, 40.6250]% | 0.21875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 17.0/32 | 16 | 53.12% [34.3750, 71.8750]% | 0.34375 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 9.0/32 | 16 | 28.12% [15.6250, 40.6250]% | 0.21875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [34.3750, 75.0000]% | 0.4375 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 11.0/32 | 16 | 34.38% [21.8750, 43.7500]% | 0.28125 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 17.0/32 | 16 | 53.12% [34.3750, 71.8750]% | 0.4375 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 11.0/32 | 16 | 34.38% [21.8750, 43.7500]% | 0.3125 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [40.6250, 84.3750]% | 0.40625 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 12.0/32 | 16 | 37.50% [28.1250, 46.8750]% | 0.28125 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [40.6250, 84.3750]% | 0.46875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 11.0/32 | 16 | 34.38% [21.8750, 43.7500]% | 0.28125 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [37.5000, 75.0000]% | 0.375 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 29.0/32 | 16 | 90.62% [75.0000, 100.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [84.3750, 100.0000]% | 0.875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 0.96875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 29.0/32 | 16 | 90.62% [75.0000, 100.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | MAJORITY | N/A | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 0.875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | ENTITY | MAJORITY | N/A | 48/16/16 | 4.0/32 | 16 | 12.50% [0.0000, 31.2500]% | 0.25 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 29.0/32 | 16 | 90.62% [75.0000, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.6875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.75 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.6875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.6875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 100.0000]% | 0.75 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.84375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B01 | PROTECTED | MAJORITY | N/A | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.8125 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.78125 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.8125 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 15.0/32 | 16 | 46.88% [25.0000, 71.8750]% | 0.6875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.8125 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.6875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.6875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 13.0/32 | 16 | 40.62% [18.7500, 65.6250]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.8125 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.6875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 13.0/32 | 16 | 40.62% [18.7500, 65.6250]% | 0.71875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.625 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 15.0/32 | 16 | 46.88% [25.0000, 68.7500]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.6875 | 0 | ESTIMATED |
| qwen35_9b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.78125 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S0 | MAJORITY | N/A | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 87.5000]% | 0.71875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 87.5000]% | 0.5 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.53125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.46875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [50.0000, 93.7500]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.34375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | S1 | MAJORITY | N/A | 48/16/16 | 10.0/32 | 16 | 31.25% [12.5000, 56.2500]% | 0.4375 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 96.8750]% | 0.96875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.1875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [37.5000, 81.2500]% | 0.375 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.8125 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 25.0/32 | 16 | 78.12% [56.2500, 93.7500]% | 0.875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [56.2500, 93.7500]% | 0.6875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 23.0/32 | 16 | 71.88% [50.0000, 90.6250]% | 0.6875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 81.2500]% | 0.71875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 81.2500]% | 0.4375 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | MAJORITY | N/A | 48/16/16 | 11.0/32 | 16 | 34.38% [21.8750, 43.7500]% | 0.3125 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 24.0/32 | 16 | 75.00% [56.2500, 93.7500]% | 0.78125 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 15.0/32 | 16 | 46.88% [28.1250, 65.6250]% | 0.40625 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [50.0000, 84.3750]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [50.0000, 87.5000]% | 0.65625 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 23.0/32 | 16 | 71.88% [53.1250, 90.6250]% | 0.65625 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 84.3750]% | 0.71875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 84.3750]% | 0.65625 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [40.6250, 81.2500]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 17.0/32 | 16 | 53.12% [37.5000, 68.7500]% | 0.375 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.53125 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 30.0/32 | 16 | 93.75% [84.3750, 100.0000]% | 0.96875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [84.3750, 100.0000]% | 0.90625 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 0.96875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 0.96875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 0.96875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [84.3750, 100.0000]% | 0.96875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.53125 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | MAJORITY | N/A | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 0.9375 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | ENTITY | MAJORITY | N/A | 48/16/16 | 4.0/32 | 16 | 12.50% [0.0000, 31.2500]% | 0.25 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.6875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.5 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [50.0000, 93.7500]% | 0.625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [50.0000, 93.7500]% | 0.5625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.84375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B1/B06 | PROTECTED | MAJORITY | N/A | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.8125 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 19.0/32 | 16 | 59.38% [34.3750, 81.2500]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.6875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.6875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.71875 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.65625 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.5625 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 15.0/32 | 16 | 46.88% [25.0000, 71.8750]% | 0.65625 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.5625 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 48/16/16 | 12.0/32 | 16 | 37.50% [12.5000, 62.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.625 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [28.1250, 71.8750]% | 0.75 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.625 | 0 | ESTIMATED |
| qwen35_9b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [34.3750, 81.2500]% | 0.8125 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S0 | MAJORITY | N/A | 10/3/3 | 0.0/18 | 3 | 0.00% [0.0000, 0.0000]% | 0.0 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 11.0/18 | 3 | 61.11% [16.6667, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 6.0/18 | 3 | 33.33% [0.0000, 66.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 4.0/18 | 3 | 22.22% [0.0000, 50.0000]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 10/3/3 | 12.0/18 | 3 | 66.67% [66.6667, 66.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 10/3/3 | 16.0/18 | 3 | 88.89% [83.3333, 100.0000]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 9.0/18 | 3 | 50.00% [16.6667, 66.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 16.0/18 | 3 | 88.89% [83.3333, 100.0000]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 10/3/3 | 9.0/18 | 3 | 50.00% [16.6667, 66.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 10/3/3 | 15.0/18 | 3 | 83.33% [66.6667, 100.0000]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 9.0/18 | 3 | 50.00% [16.6667, 66.6667]% | 0.1111111111111111 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 10.0/18 | 3 | 55.56% [50.0000, 66.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 10/3/3 | 11.0/18 | 3 | 61.11% [50.0000, 66.6667]% | 0.1111111111111111 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 10/3/3 | 11.0/18 | 3 | 61.11% [50.0000, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 13.0/18 | 3 | 72.22% [66.6667, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 9.0/18 | 3 | 50.00% [33.3333, 66.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 10/3/3 | 13.0/18 | 3 | 72.22% [66.6667, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 10/3/3 | 12.0/18 | 3 | 66.67% [50.0000, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S1 | MAJORITY | N/A | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.3333333333333333 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 1.0/18 | 3 | 5.56% [0.0000, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.2222222222222222 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.2777777777777778 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | S2 | MAJORITY | N/A | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.2777777777777778 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.2222222222222222 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.2222222222222222 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 10/3/3 | 4.0/18 | 3 | 22.22% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.1111111111111111 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 4.0/18 | 3 | 22.22% [0.0000, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.1111111111111111 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_9b | B2/FINAL | A1_AMOUNT | MAJORITY | N/A | 10/3/3 | 9.0/18 | 3 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 16.0/18 | 3 | 88.89% [66.6667, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | MAJORITY | N/A | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.3333333333333333 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | MAJORITY | N/A | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | MAJORITY | N/A | 10/3/3 | 12.0/18 | 3 | 66.67% [66.6667, 66.6667]% | 0.6666666666666666 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 4/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 13/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 22/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_9b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 31/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | Z | N/A | N/A | 48/16/16 | N/A | N/A | N/A CI_NOT_AVAILABLE | N/A | N/A | STATE_VARIABLE_NOT_IDENTIFIABLE_CONSTANT_TRAIN_LABEL |
| qwen35_27b | B1/B06 | Z | N/A | N/A | 48/16/16 | N/A | N/A | N/A CI_NOT_AVAILABLE | N/A | N/A | STATE_VARIABLE_NOT_IDENTIFIABLE_CONSTANT_TRAIN_LABEL |
| qwen35_27b | B2/FINAL | Z | N/A | N/A | 10/3/3 | N/A | N/A | N/A CI_NOT_AVAILABLE | N/A | N/A | STATE_VARIABLE_NOT_IDENTIFIABLE_CONSTANT_TRAIN_LABEL |
| qwen35_27b | B2/FINAL | ENTITY | N/A | N/A | 10/3/3 | N/A | N/A | N/A CI_NOT_AVAILABLE | N/A | N/A | VARIABLE_NOT_SUPPLIED_IN_THIS_PANEL |
| qwen35_27b | B2/FINAL | PROTECTED | N/A | N/A | 10/3/3 | N/A | N/A | N/A CI_NOT_AVAILABLE | N/A | N/A | VARIABLE_NOT_SUPPLIED_IN_THIS_PANEL |
| qwen35_27b | B1/B01 | S0 | MAJORITY | N/A | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 87.5000]% | 0.40625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.25 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.34375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.3125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.40625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.5 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.53125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.5 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.5 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.5 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.59375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.4375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S0 | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.34375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | S1 | MAJORITY | N/A | 48/16/16 | 10.0/32 | 16 | 31.25% [12.5000, 56.2500]% | 0.4375 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 22.0/32 | 16 | 68.75% [46.8750, 87.5000]% | 0.65625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.375 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [28.1250, 71.8750]% | 0.25 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.375 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.34375 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.375 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.40625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 17.0/32 | 16 | 53.12% [31.2500, 75.0000]% | 0.40625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.5625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 23.0/32 | 16 | 71.88% [50.0000, 90.6250]% | 0.5625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.5625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S1 | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 81.2500]% | 0.625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | MAJORITY | N/A | 48/16/16 | 11.0/32 | 16 | 34.38% [21.8750, 43.7500]% | 0.3125 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 23.0/32 | 16 | 71.88% [50.0000, 90.6250]% | 0.5625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 9.0/32 | 16 | 28.12% [15.6250, 40.6250]% | 0.28125 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 15.0/32 | 16 | 46.88% [28.1250, 65.6250]% | 0.28125 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 10.0/32 | 16 | 31.25% [18.7500, 43.7500]% | 0.28125 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [37.5000, 75.0000]% | 0.53125 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 11.0/32 | 16 | 34.38% [21.8750, 43.7500]% | 0.34375 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 17.0/32 | 16 | 53.12% [31.2500, 75.0000]% | 0.53125 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 10.0/32 | 16 | 31.25% [18.7500, 43.7500]% | 0.28125 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [34.3750, 78.1250]% | 0.4375 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 10.0/32 | 16 | 31.25% [18.7500, 40.6250]% | 0.28125 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 17.0/32 | 16 | 53.12% [31.2500, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 10.0/32 | 16 | 31.25% [18.7500, 43.7500]% | 0.28125 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [40.6250, 78.1250]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 11.0/32 | 16 | 34.38% [21.8750, 43.7500]% | 0.3125 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [34.3750, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 10.0/32 | 16 | 31.25% [18.7500, 43.7500]% | 0.25 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | S2 | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [43.7500, 81.2500]% | 0.40625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.90625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 0.96875 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.90625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | MAJORITY | N/A | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | ENTITY | MAJORITY | N/A | 48/16/16 | 4.0/32 | 16 | 12.50% [0.0000, 31.2500]% | 0.25 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.75 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.75 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 100.0000]% | 0.75 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.6875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | ENTITY | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B01 | PROTECTED | MAJORITY | N/A | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.8125 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.78125 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 10.0/32 | 16 | 31.25% [12.5000, 56.2500]% | 0.625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 12.0/32 | 16 | 37.50% [12.5000, 62.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 12.0/32 | 16 | 37.50% [12.5000, 62.5000]% | 0.84375 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 15.0/32 | 16 | 46.88% [25.0000, 71.8750]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 12.0/32 | 16 | 37.50% [12.5000, 62.5000]% | 0.6875 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.625 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 8.0/32 | 16 | 25.00% [6.2500, 43.7500]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 17.0/32 | 16 | 53.12% [28.1250, 75.0000]% | 0.59375 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.8125 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [40.6250, 84.3750]% | 0.59375 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B01 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.78125 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S0 | MAJORITY | N/A | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 87.5000]% | 0.71875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 100.0000]% | 0.6875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.34375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.46875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.65625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 23.0/32 | 16 | 71.88% [50.0000, 90.6250]% | 0.71875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 25.0/32 | 16 | 78.12% [56.2500, 96.8750]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 21.0/32 | 16 | 65.62% [43.7500, 87.5000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [56.2500, 93.7500]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.9375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S0 | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [50.0000, 93.7500]% | 0.65625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | S1 | MAJORITY | N/A | 48/16/16 | 10.0/32 | 16 | 31.25% [12.5000, 56.2500]% | 0.4375 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 96.8750]% | 0.96875 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.5625 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [28.1250, 71.8750]% | 0.59375 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [56.2500, 93.7500]% | 0.71875 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 96.8750]% | 0.78125 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 25.0/32 | 16 | 78.12% [56.2500, 93.7500]% | 0.875 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [50.0000, 93.7500]% | 0.8125 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 25.0/32 | 16 | 78.12% [56.2500, 93.7500]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S1 | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.8125 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | MAJORITY | N/A | 48/16/16 | 11.0/32 | 16 | 34.38% [21.8750, 43.7500]% | 0.3125 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 24.0/32 | 16 | 75.00% [56.2500, 93.7500]% | 0.78125 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [34.3750, 65.6250]% | 0.65625 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [37.5000, 81.2500]% | 0.46875 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 19.0/32 | 16 | 59.38% [40.6250, 78.1250]% | 0.53125 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [56.2500, 90.6250]% | 0.65625 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 25.0/32 | 16 | 78.12% [56.2500, 93.7500]% | 0.71875 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 25.0/32 | 16 | 78.12% [59.3750, 93.7500]% | 0.6875 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 15.0/32 | 16 | 46.88% [40.6250, 50.0000]% | 0.46875 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 96.8750]% | 0.6875 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | S2 | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 24.0/32 | 16 | 75.00% [56.2500, 90.6250]% | 0.65625 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.84375 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 30.0/32 | 16 | 93.75% [84.3750, 100.0000]% | 0.96875 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 0.96875 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 0.96875 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | MAJORITY | N/A | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 28.0/32 | 16 | 87.50% [68.7500, 100.0000]% | 0.84375 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | MAJORITY | N/A | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 31.0/32 | 16 | 96.88% [90.6250, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 24.0/32 | 16 | 75.00% [62.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 32.0/32 | 16 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | ENTITY | MAJORITY | N/A | 48/16/16 | 4.0/32 | 16 | 12.50% [0.0000, 31.2500]% | 0.25 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 26.0/32 | 16 | 81.25% [62.5000, 100.0000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.75 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.75 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.5 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 22.0/32 | 16 | 68.75% [43.7500, 87.5000]% | 0.375 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.78125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.5625 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.8125 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | ENTITY | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 30.0/32 | 16 | 93.75% [81.2500, 100.0000]% | 0.875 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B1/B06 | PROTECTED | MAJORITY | N/A | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.8125 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 48/16/16 | 19.0/32 | 16 | 59.38% [34.3750, 81.2500]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.5625 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 48/16/16 | 10.0/32 | 16 | 31.25% [12.5000, 56.2500]% | 0.625 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.6875 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 48/16/16 | 13.0/32 | 16 | 40.62% [18.7500, 62.5000]% | 0.84375 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.625 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.625 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.65625 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.6875 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 48/16/16 | 14.0/32 | 16 | 43.75% [18.7500, 68.7500]% | 0.625 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 48/16/16 | 17.0/32 | 16 | 53.12% [28.1250, 78.1250]% | 0.5625 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 48/16/16 | 18.0/32 | 16 | 56.25% [31.2500, 81.2500]% | 0.625 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 48/16/16 | 15.0/32 | 16 | 46.88% [25.0000, 71.8750]% | 0.65625 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 48/16/16 | 20.0/32 | 16 | 62.50% [37.5000, 87.5000]% | 0.75 | 0 | ESTIMATED |
| qwen35_27b | B1/B06 | PROTECTED | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 48/16/16 | 16.0/32 | 16 | 50.00% [25.0000, 75.0000]% | 0.78125 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S0 | MAJORITY | N/A | 10/3/3 | 0.0/18 | 3 | 0.00% [0.0000, 0.0000]% | 0.0 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 11.0/18 | 3 | 61.11% [16.6667, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 14.0/18 | 3 | 77.78% [66.6667, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 6.0/18 | 3 | 33.33% [0.0000, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 12.0/18 | 3 | 66.67% [66.6667, 66.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 9.0/18 | 3 | 50.00% [16.6667, 66.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 9.0/18 | 3 | 50.00% [16.6667, 66.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 10/3/3 | 9.0/18 | 3 | 50.00% [16.6667, 66.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 10/3/3 | 11.0/18 | 3 | 61.11% [50.0000, 66.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 10/3/3 | 1.0/18 | 3 | 5.56% [0.0000, 16.6667]% | 0.05555555555555555 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 10/3/3 | 8.0/18 | 3 | 44.44% [0.0000, 66.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 33.3333]% | 0.05555555555555555 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 10/3/3 | 1.0/18 | 3 | 5.56% [0.0000, 16.6667]% | 0.16666666666666666 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 10/3/3 | 6.0/18 | 3 | 33.33% [0.0000, 83.3333]% | 0.1111111111111111 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S0 | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [0.0000, 33.3333]% | 0.1111111111111111 | 2 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S1 | MAJORITY | N/A | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.3333333333333333 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 1.0/18 | 3 | 5.56% [0.0000, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.2222222222222222 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 10/3/3 | 2.0/18 | 3 | 11.11% [0.0000, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S1 | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | S2 | MAJORITY | N/A | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.2222222222222222 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 4.0/18 | 3 | 22.22% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 10/3/3 | 4.0/18 | 3 | 22.22% [0.0000, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 10/3/3 | 4.0/18 | 3 | 22.22% [0.0000, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 10/3/3 | 5.0/18 | 3 | 27.78% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 10/3/3 | 3.0/18 | 3 | 16.67% [16.6667, 16.6667]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 10/3/3 | 4.0/18 | 3 | 22.22% [16.6667, 33.3333]% | 0.16666666666666666 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | S2 | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 10/3/3 | 7.0/18 | 3 | 38.89% [33.3333, 50.0000]% | 0.2777777777777778 | 5 | ESTIMATED_WITH_CLASS_COVERAGE_LIMIT |
| qwen35_27b | B2/FINAL | A1_AMOUNT | MAJORITY | N/A | 10/3/3 | 9.0/18 | 3 | 50.00% [50.0000, 50.0000]% | 0.5 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 16.0/18 | 3 | 88.89% [66.6667, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_AMOUNT | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | MAJORITY | N/A | 10/3/3 | 6.0/18 | 3 | 33.33% [33.3333, 33.3333]% | 0.3333333333333333 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_AMOUNT | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | MAJORITY | N/A | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A1_TYPE | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | MAJORITY | N/A | 10/3/3 | 12.0/18 | 3 | 66.67% [66.6667, 66.6667]% | 0.6666666666666666 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | WORD_NUMBER_BAG_PLUS_LENGTH | N/A | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 0/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 9/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 18/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 27/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 36/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 36/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 45/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 45/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 54/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 54/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 63/P_CHECKPOINT | 10/3/3 | 15.0/18 | 3 | 83.33% [83.3333, 83.3333]% | 0.8333333333333334 | 0 | ESTIMATED |
| qwen35_27b | B2/FINAL | A2_TYPE | RESIDUAL_LINEAR_RIDGE | 63/P_QUERY | 10/3/3 | 18.0/18 | 3 | 100.00% [100.0000, 100.0000]% | 1.0 | 0 | ESTIMATED |


Source artifact: `artifacts/model_results/sequential_state_mechanism/ssm_b1b2_20260911_v1/result_summary_20260911/R1_ALL_MODELS_ALL_RESULTS.csv`  
Source hash: `8468b3dacc757faf7234374a6e7f632dfe9a0324a8bfa516599cfe332842c007`  
Rows / metric names: 全部1365行；不挑最高层，不移除constant/unseen-class限制.


## 20. Lightweight Provenance and Acceptance


每个主要表后给出实际source path、SHA256和row/metric选择。相同来源在不同表重复引用不代表重复样本。少量E0原prompt使用冻结raw_record_sha256；不为输出报告复制巨大raw索引。附录只提供真实prompt实例和少量代表性输出，没有activation tensor、权重、全量raw或Slurm日志。

本报告新增的只是汇总视图：错误类别频数、family拆分、Type-A-like、count历史B05−B07描述性配对等显式POSTHOC项；旧指标/CI原样读取。事后CI为world bootstrap 5000/seed20260912，无多重检验校正。不把sum(delta)/N当二元正确数；world-macro numerator亦非整数正确world。

```json
{
  "no_new_model_inference": true,
  "no_historical_writes": true,
  "final_decision": "NO_GO",
  "localize_windows": 32,
  "i2_primary_grid_cells": 24,
  "w1_all_target_rows": 36,
  "r1_full_rows": 1365,
  "noncount_worlds": {
    "HORIZONTAL": 34,
    "VERTICAL": 6,
    "DEPTH": 7
  },
  "exact_prompt_instances": 78,
  "source_files": 51,
  "representative_case_groups": 5,
  "full_e0_models": 10,
  "not_run_branches": [
    "I3",
    "CROSS_SCALE_INTERNAL_VALIDATION",
    "SEPARATE_LENGTH_ONLY_BASELINE",
    "I2_SAME_VALUE_UNRELATED_REGISTER"
  ]
}
```


缺失字段不补造：扩展E0模型的bootstrap CI、独立length/bag基线、未运行I3/跨scale内部测试、未通过等价控制的响应。旧ZIP中的SELECT RUNNING快照不再作为最新结论，最终结果以本文§14及SELECT_DECISION为准。
