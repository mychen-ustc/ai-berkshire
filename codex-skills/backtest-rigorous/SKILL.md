---
name: backtest-rigorous
description: "AI Berkshire skill: 回测严谨化层. Source: skills/backtest-rigorous.md."
---

## Codex adapter note

This skill is generated from `skills/backtest-rigorous.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 回测严谨化层

把 Tier 1 数据地基接入回测，量化并修正三种偏差：$ARGUMENTS。T2-3。

## 解决什么

`backtest.py` 做"点时价格 + 含成本"信号检验，但自己诚实标注三个缺口。`backtest_rigorous.py`（零依赖）把 Tier 1 三库接进来补上，并**量化每种偏差的大小**——回测的价值一半在结果、一半在"知道结果被高估了多少"。

| 偏差 | 接入的库 | 修正 |
|---|---|---|
| **幸存者偏差** | `delisting` | 构造"当时在市"池(含后来退市的)、计入退市终值收益；报告 幸存者池 vs 全域 的高估幅度 |
| **前视偏差** | `pit_financials` | 用"当时已披露"的基本面取估值/因子信号，估值类信号才可被诚实检验 |
| **复权错误** | `corporate_actions` | 拆股/分红对原始价格收益的修正(拆股不再被误读为暴跌) |

## 执行流程
```bash
# 审计一个回测配置对三种偏差的暴露(查 Tier 1 库,报告需哪些修正)
python3 tools/backtest_rigorous.py audit --symbols "AAPL,LEHMQ,GOOGL,NVDA" --start 2007-01-01 --end 2009-12-31
# 量化幸存者偏差(全域含退市终值 vs 幸存者池)
python3 tools/backtest_rigorous.py survivorship --full "AAPL=0.5,LEHMQ=-1.0,GOOGL=0.8" --survivors "AAPL=0.5,GOOGL=0.8"
```
- **audit**：报告区间内退市的名字(幸存者)、有无点时财务(可否检验估值信号)、有无公司行动(需否复权)。
- **survivorship**：漏掉雷曼(-100%)让幸存者池 +65% vs 真实 +10% → **虚高 55%**，量级一目了然。

## 与 backtest 的分工
- `backtest`：跑价格信号策略(动量/趋势)的收益/回撤。
- `backtest-rigorous`：给回测**打严谨性补丁**——先 audit 看偏差暴露，再对结果做幸存者/复权修正、对信号做点时化。二者配合：先 rigorous audit，再 backtest 跑，最后 rigorous 量化偏差。

## 原则与诚实边界
- **"引擎已建"到"引擎在用"的关键一跳**：Tier 1 库建好了，接入回测才兑现价值。
- **严谨性取决于库的完整度**：Tier 1 靠手工/增量补录——库覆盖不全时"无偏差"可能只是"没数据"，audit 会显式提示。
- 幸存者修正需退市样本+终值收益；点时信号需 available_at 准确；复权分红项需当时价格。

## 相关
`backtest`(价格信号) · `delisting`/`pit_financials`/`corporate_actions`(Tier1三库) · `factor-library`(信号来源) · `data-foundation`
