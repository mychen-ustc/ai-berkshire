# 数据血缘与复现日志

追溯"某结论由哪版工具+哪批数据算出"，校验可复现性：$ARGUMENTS。T2-4。

## 解决什么

`model-registry` 管"模型有哪些、假设与校验"；`lineage`（`tools/lineage.py`，零依赖）管**"某个数字/结论到底由哪版工具、消费了哪批数据算出"**——让任何历史结论可追溯、可重放、可审计。杜绝"当时算出是这个数，现在没人知道怎么来的"。

核心是**可复现签名**：对 (工具版本 + 输入 + 参数) 做确定性 SHA256。日后重算——签名一致→结果应复现；数据被修订(input as_of 变)/工具升级→签名不同，并精确告诉你**哪一部分变了**。

## 执行流程
```bash
# 记录一次输出的血缘(报告/优化流程结束时调用)
python3 tools/lineage.py record --output v10-组合优化 --tool portfolio_optimizer --version 0.3 \
    --inputs "VOO@yahoo@2026-07-14,GOOGL@yahoo@2026-07-14" --params "method=risk-parity,period=2y" \
    --result "年化+24.6%/回撤-12.7%"
# 追溯来龙去脉
python3 tools/lineage.py trace --output v10-组合优化
# 校验现在能否逐位复现
python3 tools/lineage.py verify --output v10-组合优化 \
    --inputs "VOO@yahoo@2026-07-20,..." --params "..." --version 0.4
```
- **verify** 输出示例："🔴 无法逐位复现——工具版本 0.3→0.4 · 输入 VOO 2026-07-14→2026-07-20 · 参数 period 2y→5y"。
- record 会交叉核对工具是否已在 `model_registry`，未登记则提示。

## 与治理链的闭环
`model-registry`(模型登记) → `lineage`(输出↔输入链路+签名) → `report-audit`(发布门禁) → `decision-journal`(决策登记)。四者构成"可追溯、可问责、可复现"的治理闭环。

## 原则与诚实边界
- **签名不含时间**：只哈希 版本+输入+参数，才能确定性复现；computed_at 仅记录不入签名。
- **"不可复现"不是错误，是审计事实**：依赖的数据/工具变了，结论须重新出具而非沿用旧结论。
- 血缘质量取决于录入完整度——输入的 source/as_of 要如实填(datalayer 已为每次取数盖 as_of/fetched_at 戳，可直接引用)。

## 相关
`model-registry`(模型版本) · `report-audit`(门禁) · `decision-journal`(决策) · `datalayer`(as_of/fetched_at 戳) · `data-foundation`(点时数据)
