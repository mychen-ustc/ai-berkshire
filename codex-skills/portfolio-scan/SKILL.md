---
name: portfolio-scan
description: "AI Berkshire skill: 组合全景体检：一键五面 + 组合层. Source: skills/portfolio-scan.md."
---

## Codex adapter note

This skill is generated from `skills/portfolio-scan.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 组合全景体检：一键五面 + 组合层

对 $ARGUMENTS（账本或组合）一键跑全景体检。

## 这个 skill 解决什么

此前每次端到端分析都要手写驱动脚本串联工具。`/portfolio-scan` 用 `tools/portfolio_scan.py`（零依赖）把它**产品化**：一条命令串起——

- **逐持仓五面**：技术面(technicals) × 资金面(moneyflow，A/H 含主力资金流) × 情绪面(sentiment)，`--deep` 再加消息面(A股公告催化剂)/一致预期(美股)。
- **组合层**：多因子 PCA(factor_model 伪分散检测) + 市场情绪(涉及的市场) + 宏观 regime(macro_regime)。
- 输出结构化 JSON、文本摘要、可选**综合 HTML 报告**。

## 执行流程
```bash
python3 tools/portfolio_scan.py --from-ledger reports/private/x.csv --fx "USD=1,HKD=0.128,CNY=0.14" --html out.html
python3 tools/portfolio_scan.py --symbols "AAPL,GOOGL,600519,0700.HK"          # 等权
python3 tools/portfolio_scan.py --symbols "..." --weights "AAPL=30,..." --deep   # 加催化剂/一致预期(慢)
```

## 原则
- **只聚合、不下单**：给多面读数与组合结构，最终判断仍回到基本面与人工审批。
- **五面皆叠加层**：技术/资金/情绪/消息辅助择时与验证认知差，永不替代基本面与估值。
- **含真实持仓的输出走 reports/private/**（已 gitignore）；--from-ledger 读真实账本时尤其注意。
- 每个持仓只取一次 OHLCV 派生技术/资金/情绪，省流量；单只失败不阻断整体（标记 error）。

## 相关
`portfolio-review`(定性综合决策) · `factor-model`/`portfolio_risk`(组合层) · `technical-analysis`/`money-flow`/`sentiment`(五面) · `macro-regime`(背景板)
