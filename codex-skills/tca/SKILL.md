---
name: tca
description: "AI Berkshire skill: 交易成本分析 TCA. Source: skills/tca.md."
---

## Codex adapter note

This skill is generated from `skills/tca.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 交易成本分析 TCA

估一笔单/一篮子的全交易成本，事后算执行落差：$ARGUMENTS。T3-1。

## 解决什么

`rebalance` 的成本只算线性佣金/税。真实成本还有两块：**价差**(每笔付半价差)、**冲击**(大额单推动价格，∝√(订单/ADV))。`tca.py`(零依赖)把三块拆开，让你下单前就知道"这笔能不能这么大、要不要拆单"。事后再用**执行落差**衡量"想做的 vs 做到的"。

一笔占 ADV 30% 的小盘单，冲击成本可能是佣金的十几倍——这正是 rebalance 报"成本$57"漏掉的。

## 执行流程
```bash
python3 tools/tca.py estimate --notional 900000 --adv 3000000 --daily-vol 0.04 --spread-bps 20
python3 tools/tca.py basket --file orders.csv          # CSV: symbol,notional,adv,daily_vol,spread_bps
python3 tools/tca.py shortfall --decision-price 100 --exec-price 100.4 --qty 5000 --side buy
```
- **estimate**：佣金+价差+冲击分解，参与率>20%🔴/>10%🟡 预警，并估拆单天数。
- **basket**：一篮子调仓逐笔标红/黄，汇总总成本。
- **shortfall**：决策价 vs 成交均价的滑点(bps + 现金)。

## 与 rebalance 的分工
`rebalance` 生成订单(股数/换汇/线性成本) → `tca estimate/basket` 给订单打**真实成本**补丁(含冲击) → 参与率过大则拆单 → 执行后 `tca shortfall` 复盘。

## 原则与诚实边界
- **冲击平方根定律**：impact_bps = coef×日波动×√(订单/ADV)——大额/小盘/高波尤甚。
- coef 与价差为估计,真实成本依赖流动性/时段;小额单(占ADV<1%)冲击可忽略,别过度优化。
- 长期看,执行落差累积会显著侵蚀收益,须纳入策略成本(与回测成本口径一致)。

## 相关
`rebalance`(订单) · `tail-risk`(流动性天数) · `backtest-rigorous`(回测成本口径) · `portfolio-optimizer`
