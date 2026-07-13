---
name: backtest
description: "AI Berkshire skill: 统一回测框架：信号有没有历史 edge. Source: skills/backtest.md."
---

## Codex adapter note

This skill is generated from `skills/backtest.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 统一回测框架：信号有没有历史 edge

对 $ARGUMENTS（标的池 + 策略）做点时、含成本的统一回测。

## 这个 skill 解决什么

技术面/动量/趋势信号"看起来有用"不等于"真有用"。`/backtest` 用 `tools/backtest.py`（零依赖）给所有信号一个**统一口径**的检验台：点时（信号只用历史、不看未来）+ 含交易成本 + 对基准比较。**所有 Alpha 策略跑同一引擎，结果才可比。**

## 执行流程
```bash
# 横截面动量：按回看收益排名持有前 N，月度再平衡
python3 tools/backtest.py run --from-datalayer "AAPL,GOOGL,MSFT,AMZN,NVDA,META,SPY" \
    --strategy momentum --lookback 12 --top 3 --benchmark SPY --freq monthly --period 5y --cost-bps 10
# 趋势择时：收盘 > SMA(n) 才持有，否则空仓
python3 tools/backtest.py run --from-datalayer "600519,000858,300750" --strategy trend --sma 30 --freq weekly
```

输出：CAGR / 年化波动 / 最大回撤 / Sharpe / 胜率 / 累计净值 / 平均换手，以及**对基准的超额年化**（✅跑赢 / ❌被成本吃掉或无 edge）。

## 与其它工具的闭环
1. `technicals` / `factor_model` 产出信号规则 → 2. **`/backtest` 检验该规则历史上是否含成本仍跑赢** → 3. 通过验证的信号才纳入 `sell-discipline`/`portfolio-optimizer` 的实盘规则 → 4. 用 `decision-journal` 记录规则上线并事后校准。

## 原则（诚实是底线）
- **幸存者偏差**：股票池是"当前还活着"的标的，未纳入退市/失败样本 → 结果偏乐观。跨全市场结论前必须接入退市库（路线图 P3-6）。
- **点时仅限价格**：信号只用历史价格；未接点时基本面，估值类信号无法在此检验。
- **过去有效 ≠ 未来有效**：拒绝过拟合——不要为了漂亮回测反复调参（数据窥探）；训练/验证/样本外要分离。
- 成本/滑点是简化线性模型；短窗口、少标的结果不稳。

## 相关
`technical-analysis`(信号来源) · `factor-model`(因子信号) · `sector-rotation` · `sell-discipline`(规则落地) · `decision-journal`(校准)
