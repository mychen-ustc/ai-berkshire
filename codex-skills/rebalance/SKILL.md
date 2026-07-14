---
name: rebalance
description: "AI Berkshire skill: 再平衡引擎. Source: skills/rebalance.md."
---

## Codex adapter note

This skill is generated from `skills/rebalance.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 再平衡引擎

由当前账本 + 目标权重生成调仓订单：$ARGUMENTS。P4-11。

## 解决什么

把手写调仓脚本产品化。`tools/rebalance.py`（零依赖）：给当前账本 + 目标权重 → 计算买卖股数、多币种换汇提示、交易成本估计，生成可执行调仓 CSV。目标之外的持仓自动清仓。

## 执行流程
```bash
python3 tools/rebalance.py --from-ledger data/portfolio/transactions.csv \
    --target "VOO=21,BRK.B=15,GOOGL=14,KO=13,AAPL=9,AXP=9,COST=6,603986=4" \
    --fx "USD=1,HKD=0.128,CNY=0.14" --cost-bps 10 --out reports/private/transactions.new.csv
```
输出：每只 现→目标股数、动作(BUY/SELL/🔴清仓)、换手额、成本估计、**跨币种换汇缺口提示**，`--out` 生成追加到账本的调仓 CSV。

## 与组合构建闭环
1. `portfolio-optimizer`（risk-parity/min-variance）给目标权重 → 2. `tail-risk`/`factor-model` 校验目标的风险/伪分散 → 3. **`/rebalance` 落到订单** → 4. 人工确认(税/流动性/择时) → 执行后账本更新 → `security-master` 记录、`review` 跟踪。

## 原则
- **报价折算股数、实际成交会滑动**；下单前核对最新价。
- **跨币种买卖需另加换汇行**（工具提示某币种现金缺口）——如清仓港股释放 HKD、买美股需 USD。
- 成本为线性估计(bps×换手额)，未含冲击成本(大额/小盘看 `tail-risk` 流动性)。
- 再平衡是**决策与纪律的执行**，须人工确认——工具算账、人拍板。

## 相关
`portfolio-optimizer`(目标权重) · `tail-risk`/`factor-model`(校验) · `ledger`(事实源) · `sell-discipline`(卖出纪律) · `review`(执行后跟踪)
