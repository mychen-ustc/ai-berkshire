---
name: factor-risk
description: "AI Berkshire skill: 因子风险分解. Source: skills/factor-risk.md."
---

## Codex adapter note

This skill is generated from `skills/factor-risk.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 因子风险分解

把组合波动分解为各命名因子贡献 + 特异风险：$ARGUMENTS。Barra 式风险模型。

## 解决什么

`factor-library` 给**因子暴露**;`factor-risk` 补最后一块——**风险归因**:回答"我的组合波动到底来自哪个因子、多少是选股独有的特异风险"。

方法(单期暴露横截面因子模型,Fama-MacBeth 式)：
1. 每期横截面 OLS：个股收益 = Σ 暴露×因子收益 + 特异 → 解出因子收益(需股票数 N>因子数 K)。
2. 因子协方差 F = cov(因子收益);特异方差 D = var(残差)。
3. 组合方差 = (w'X)·F·(w'X)'[因子] + Σw²D[特异];拆因子占比 + 每因子贡献。

## 执行流程
```bash
python3 tools/factor_risk.py analyze \
    --symbols "GOOGL,AXP,KO,COST,NDAQ,AAPL,MSFT,NVDA,META,AMZN" \
    --weights "GOOGL=25,AXP=15,..." --period 2y
```
输出:因子风险vs特异风险占比 + 每因子方差贡献(负=对冲降险)。实测 v10 类组合:因子风险45%(动量主导+60%)/特异55%。

## 前置：需足够 universe + EDGAR 覆盖
- **N>K**：横截面回归需**股票数 > 6 因子**,故 universe 要 ≥~10 只全覆盖美股。
- 全覆盖=同时有 consensus(价值/成长)+ EDGAR 点时(质量/规模);先 `edgar_financials ingest` 摄取。

## 诚实边界
- 单期暴露模型(暴露取当前值),因子收益由 OLS 估计——**暴露漂移/共线性**会失真。
- 因子协方差随窗口漂移;美股为主(因子覆盖);**不含黑天鹅**(与 tail_risk 合看)。
- 这是"风险来自哪"的诊断,非"未来风险"的保证。

## 相关
`factor-library`(暴露) · `factor-model`(PCA伪分散) · `tail-risk`(尾部) · `quant-metrics`(五指标) · `portfolio-optimizer`
