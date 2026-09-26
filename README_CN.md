# SpaceConflict 代码与数据

论文标题：Seeing, Saying, but Not Using: From Reportable Spatial Facts to Usable States in Multimodal Models。

本目录是独立导出副本，不覆盖原研究仓库、原始数据、gold、预测、检查点或历史评分。代码许可证按项目所有者选择为 MIT；上游数据不自动改为 MIT。

## 直接查看

- `README.md`：英文项目首页与目录导航。
- `artifacts/model_results/full_multimodel_20260908_v1/`：24,196 条完整 benchmark 的题目及答案。
- `artifacts/model_results/pss_20260922_v1/approved_v2/data/test/private_gold.jsonl`：5,608 条固定 test 的公开答案。文件历史命名仍有 private，但本包明确公开。
- `phase8/`：真实训练、SFT 数据准备、采样、推理、评分源代码。
- `results/sft/`：13 组 test 的汇总结果，不含逐题回答和逐题评分记录。
- `verification/`：首次完整导出的历史验收，以及本次精简包的数据、完整性与接口检查记录。

## 本次精简范围

按要求移除模型逐题回答/评分记录，以及诊断实验输入和答案。完整 benchmark 题目与 gold、固定 train/dev/test、训练监督数据、代码和结果汇总表不变。原研究项目中的实验记录未删除。

诊断代码保留，但相关诊断数据不随包提供。历史 13 组结果曾从原始回答重算验收；如需再次复现，须另外提供原始预测目录，不能仅凭本精简包重算这些历史结果。使用者仍可用 `tools/score.py` 对自己生成的预测评分。

## 隐私处理范围

本仓库公开托管在 changcv2021 账号下，因此不是匿名托管。以下处理针对文件内容中的私人信息，不隐去公开仓库所有者身份。

移除作者身份线索、个人绝对路径、实验室内部 endpoint、硬编码凭据及特定账户。保留上游数据集名称、公开模型 ID、研究所需样本/世界 ID 和合法第三方署名。没有复制 `.git` 历史、聊天记录、个人邮件、密钥文件、原始图片、模型权重或全部下载缓存。

历史文件中的路径已改为本目录下的相对路径或外部资源占位位置。历史 freeze/hash 回执仅作原实验溯源，不能因匿名化后的文件 hash 不同就伪造原验收通过。详见 `docs/PORTABILITY.md`。

本仓库不声称所有 GPU 实验已经在公开副本上重跑。公开 test gold 增加了本地复现便利性，同时意味着它不再是隐藏答案评测集。发布前技术核查见 verification/PUBLICATION_PRECHECK_20260926.json；历史验收文件保留原有含义。MIT 不覆盖上游数据，也不代表源数据衍生标注已完成许可核验，详见 DATA_TERMS.md。
