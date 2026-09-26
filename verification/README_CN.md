# 导出验收记录

首次完整导出状态：PASS（历史记录，不代表精简包仍包含原始预测）。

- 所有源码 Python 语法、JSON/JSONL 语法已检查。
- 检查作者身份、个人路径、邮箱、内部 endpoint 与凭据字面量；不记录密钥原文。
- 核对 train/dev/test 与完整 benchmark 的全部 gold、ID、题目和媒体角色/hash。
- 执行固定 parser、采样计划、preserved-L4 exposure 的回归测试。
- 从原始回答重算 13 组模型的 held-out test 指标并与历史 v3 逐项核对。
- 未运行 GPU 训练或新模型推理；未调用付费 API；未对外发布。

历史详细结果见 EXPORT_ACCEPTANCE.json；当时原始预测尚在完整包内。之后按要求移除公开副本中的逐题回答/评分、诊断输入/答案，历史报告不改写。

本次精简范围及重新检查结果见 SLIM_ACCEPTANCE_20260926.json。复现历史 13 组评分现在需要通过 --predictions-dir 另外提供原始预测；其公开汇总表仍保留。源数据与第三方许可见 ../DATA_TERMS.md。
本次是已知身份/凭据模式检查，不宣称能排除所有推断性再识别风险。
