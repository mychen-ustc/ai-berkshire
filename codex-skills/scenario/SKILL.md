---
name: scenario
description: "AI Berkshire skill: 情景与概率引擎. Source: skills/scenario.md."
---

## Codex adapter note

This skill is generated from `skills/scenario.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 情景与概率引擎

对 $ARGUMENTS 做牛/基/熊情景的概率加权与赔率。P4 深度建模。

## 解决什么

把"牛/基/熊 + 主观概率"变成可计算的期望，用 `tools/scenario.py`（零依赖）：概率加权价值(EV)、期望回报、非对称赔率(上行/下行)、亏损概率。让 `decision-journal` 的概率字段可算、可事后 Brier 校准。

## 执行流程
```bash
python3 tools/scenario.py eval --price 100 --scenarios "bull:0.30:160,base:0.50:110,bear:0.20:60"
```
输出：各情景回报、EV、期望回报、最好/最坏、亏损概率、非对称赔率(≥1.5 上行占优)。

## 与其它工具的闭环
`dcf`/`comps`/`statement-model`(各情景目标价的来源) · `position-sizing`(赔率→凯利仓位) · `decision-journal`(概率留痕→Brier 校准) · `master-lens`(马克斯·概率思维)

## 原则
- **概率是主观判断、非事实**；EV 对概率与目标价高度敏感——务必做敏感性、勿单点。
- 用来**结构化思考 + 事后校准**，非精确预测；非对称(上行>下行)才是价值投资的赔率优势所在。
