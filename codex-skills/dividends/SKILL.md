---
name: dividends
description: "AI Berkshire skill: 分红入账. Source: skills/dividends.md."
---

## Codex adapter note

This skill is generated from `skills/dividends.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 分红入账

把真实分红按时点持股记入账本 DIV 交易：$ARGUMENTS。

## 解决什么

分析层(adjclose/前复权)已假设分红再投资，但**真实账本只记买卖、没记分红现金**。`dividends.py`(零依赖)回放账本，对每只持仓、每个除息日，按**当时实际持股 × 真实每股分红**(Yahoo events=div)算出收到的分红，记为账本 DIV 交易(现金入账 + 计入该 symbol 累计分红)。用真实分红数据，不编。

## 执行流程
```bash
python3 tools/dividends.py preview --from-ledger data/portfolio/transactions.csv          # 预览
python3 tools/dividends.py apply --from-ledger data/portfolio/transactions.csv [--tax 0.15] # 追加DIV(先自动备份)
```
- preview 按标的汇总应记分红 + 最近笔明细；apply 追加 DIV 行并备份原账本。
- 账本已内建 DIV 动作(现金 += 分红)；追加后 `ledger.py positions` 重建即见现金含分红。

## 原则与诚实边界
- **仅美股**(Yahoo 分红事件)；A股/港股(兆易)分红需东财数据，本版本未接。
- 记**除息日 × 当时持股**的应得分红；实际派息有延迟。
- 默认记**税前毛股息**；外国投资者美股股息有预扣税(~30%/协定~15%)，用 `--tax` 记税后。
- 默认现金入账(不自动 DRIP 再投资)；再投资需另下买单。
- ex-date 用 `interval=1d` 取准确日(1mo 会吸附月初)。

## 相关
`ledger`(DIV动作/事实源) · `corporate_actions`(分红/拆股记录) · `quant-metrics`/`horizon-compare`(总回报已含分红) · `performance`(TWR/XIRR)
