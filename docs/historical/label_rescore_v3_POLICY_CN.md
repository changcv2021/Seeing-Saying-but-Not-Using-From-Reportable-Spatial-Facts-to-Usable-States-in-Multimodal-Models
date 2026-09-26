# label_rescore_v3：缺失分隔符的明确标签恢复

这是用户于 2026-09-25 授权的事后评分修正，不是原预注册协议；不得按新分数反复调整规则。

只移除 v2 对完整标签闭合引号之后字符的限制。示例 `{"label":"SUPPORTED"confidence:0.9...` 或 `{"label":"SUPPORTED"## Reasoning...` 已经完整输出标签，不应因为后续缺逗号被当作没有标签。

- 解析只接收原始回答、终止原因、token 数和运行错误。gold、模型、seed、level 不参与解析。
- 保留 v2 已识别的全部标签。新增恢复仅限回答开头对象的第一个、已闭合引号的大写枚举标签。
- 仍拒绝额外 quoted/unquoted label 字段（含 Unicode 转义 key，即使标签相同），不在解释中寻找答案，不补全部分标签，不猜测自由文本。
- 维持既有 outer-fence、EOS/stop/length 和 512-token 保留规则。不重推理，不修改任何 raw/gold/test。
- JSON/schema 合规率、reason、confidence 均沿用原始解析记录；标签恢复不能冒充格式修复或解释评分。
- 全部 5,608 test inputs 和原始 complete binary pair 分母保持不变；未恢复项继续计错。
- Base、五种旧方法各两个 seeds、preserved-L4 Full PSS 两个 seeds 使用完全同一规则。
- 每条记录须精确重现旧 v2 标签，保留 v2/v3、原文件/行号/hash、恢复字符区间和拒绝原因。每个模型记录冻结的旧结果与 raw hashes。
- 严格旧分数、v2、v3 并列披露。两 seed 未齐时不计算该方法的两 seed 均值或标准差。

本修复仅解决明确标签被格式边界漏读的问题，不证明所有未识别回答都正确，也不修复模型生成规范 JSON 的能力。
