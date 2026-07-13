---
name: portfolio-optimizer
description: "AI Berkshire skill: 组合优化器：约束下的纪律化权重. Source: skills/portfolio-optimizer.md."
---

## Codex adapter note

This skill is generated from `skills/portfolio-optimizer.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 组合优化器：约束下的纪律化权重

对 $ARGUMENTS 给出价值投资约束下的建议权重。

## 这个 skill 解决什么

`portfolio-review` 是定性体检；`/portfolio-optimizer` 用 `tools/portfolio_optimizer.py`（零依赖）给**透明、可解释 + 硬约束**的权重建议——不是黑箱均值方差，而是逆波动(风险平价近似) + IPS 单一上限硬约束。

## 执行流程
```bash
python3 tools/portfolio_optimizer.py optimize --from-datalayer "600519,0700.HK,AAPL,VOO" \
    --method inverse-vol --period 5y   # 上限默认读 config/investment-policy.json
```
- **逆波动**：波动越低权重越高，让各标的风险贡献更均衡（低波资产不再被埋没）。
- **等权**：`--method equal`，朴素基准。
- **IPS 上限**：超限者封顶，超出部分按比例再分配（迭代收敛）；`--cap` 可覆盖。
- 输出各标的年化波动、原始权重、上限后权重、HHI/有效持仓数。

## 与其它工具的闭环
1. `/portfolio-optimizer` 给建议权重 →
2. `tools/portfolio_risk.py` 对结果体检(波动/回撤/相关性/集中度) →
3. `tools/position_sizing.py` 对单只用凯利/赔率校验仓位 →
4. `/portfolio-review` 综合决策与再平衡。

## 原则
- 这是**纪律化配置**，非收益最大化；逆波动降低单点风险，但不预测收益。
- 优化只在**已通过质量与估值筛选**的候选内进行——别优化一篮子烂公司的权重。
- 相关性高的资产即使各自波动低，也不能靠"分散"错觉重仓（结合 portfolio_risk 的相关性矩阵看）。

## 相关
`portfolio-review` · `portfolio_risk.py`(诊断) · `position_sizing.py`(单只定仓) · `master-lens`(达利欧·分散)
