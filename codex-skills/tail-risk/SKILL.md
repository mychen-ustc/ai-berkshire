---
name: tail-risk
description: "AI Berkshire skill: 尾部与流动性风险 + 压力测试. Source: skills/tail-risk.md."
---

## Codex adapter note

This skill is generated from `skills/tail-risk.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 尾部与流动性风险 + 压力测试

对 $ARGUMENTS（组合/账本）做机构级极端与生存风险评估。P4-3。

## 解决什么

`portfolio_risk` 给"常态"风险(波动/回撤/相关性)；`/tail-risk` 用 `tools/tail_risk.py`（零依赖）补"极端与生存"风险——**机构的立身之本**：

- **VaR / CVaR**：历史法 + 参数法(含 Acklam 逆正态，不依赖 scipy)，95%/99%，日/周/期口径 + 年化。CVaR(ES) 看"破 VaR 后平均亏多少"。
- **压力测试引擎**：历史/假设市场冲击(beta 映射)、反向压力测试(要亏 X% 需多大冲击)、单一最大持仓下跌/归零。
- **流动性风险**（--from-ledger）：按 ADV(日均成交额) 估 20% 参与率下的清算天数。

## 执行流程
```bash
python3 tools/tail_risk.py analyze --from-ledger data/portfolio/transactions.csv --fx "USD=1,HKD=0.128,CNY=0.14" --benchmark VOO
python3 tools/tail_risk.py analyze --from-datalayer "VOO,AAPL,GOOGL" --weights "VOO=40,AAPL=30,GOOGL=30" --benchmark VOO
```

## 与风控闭环
1. `portfolio_risk`(常态) + `factor_model`(伪分散) + **`/tail-risk`(极端/流动性)** 三件套看全风险画像 → 2. 对照 IPS 风险预算 → 3. 越限则 `portfolio-optimizer`/`sell-discipline` 降险。

## 原则（诚实是底线）
- **VaR 只是常态极端、不含黑天鹅**：2008/2020 实际损失远超模型 VaR；用 CVaR + 压力情景 + 现金缓冲兜底，不迷信单一 VaR 数字。
- 历史/假设情景用 **beta 线性映射**，低估极端时的相关性跳升与非线性——是下限估计、非精确。
- 流动性用 ADV 近似；小资金在大盘股里流动性无忧，但**大 AUM/小盘/集中持仓**才是该模块发力处。
- 风控是**生存底线、非收益预测**；VaR 不替代回撤/流动性/尾部情景，须合看。

## 相关
`portfolio-risk`(常态风险) · `factor-model`(因子/伪分散) · `portfolio-optimizer`(降险) · `sell-discipline`(越限减仓) · `master-lens`(塔勒布·生存)
