---
name: horizon-compare
description: "AI Berkshire skill: 多周期收益对比表. Source: skills/horizon-compare.md."
---

## Codex adapter note

This skill is generated from `skills/horizon-compare.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 多周期收益对比表

对 $ARGUMENTS 按 1/3/5/10/15/20 年多尺度列核心指标并对比美/A/港指数。

## 解决什么

`horizon_compare.py`(零依赖)把组合核心指标(总回报/最终余额/年化/最大回撤/Sharpe/Alpha/Beta/IR)按多个时间尺度列表，并与**美股(QQQ/SPY)、A股(沪深300)、港股(恒生2800)** 主要指数对比。回答"这个组合在不同周期下相对大盘到底强在哪"。

## 执行流程
```bash
python3 tools/horizon_compare.py --from-datalayer "GOOGL=16,MTUM=14,VOO=14,..." \
    --benchmarks "QQQ,SPY,sh000300,2800.HK" --rf 0.04 [--md]
```
三张表：① 组合多周期表现 ② 年化收益 vs 指数 ③ 最大回撤 vs 指数。已内建到 `review.py --weekly/--quarterly` 的第八节(md+html)。

## ★两条诚实边界（必须随表呈现）
1. **数据边界**：组合回测受**最年轻持仓**限制——v10 因兆易(2016 上市)只有 ~10 年共同历史，故 **15/20 年组合列"数据不足"**；指数有 20 年+仍对比。
2. **时代错置/幸存者偏差**：用"今天的持仓"回测历史 = 假设你当年就持有这些且都活到今天，**系统性高估**。这是"当前组合的历史特征画像"，**非你当年真实收益**。

## 技术要点
- 全程**月度对齐**(跨市场周频星期锚不同，YYYY-MM 键才能对齐)；≤10 年用 10y 周频重采样，15/20 年指数用 max 月频。
- CAGR/最大回撤跨频率可比；不含黑天鹅、单一无风险利率。
- v10 实测：1年 CAGR+39.9%/Sharpe2.27、3年+27.3%、5年+16.3%，各周期年化均超 QQQ/SPY，β0.5-0.6 防御。

## 相关
`quant-metrics`(五指标) · `review`(内建第八节) · `backtest-rigorous`(偏差) · `portfolio-optimization-report`
