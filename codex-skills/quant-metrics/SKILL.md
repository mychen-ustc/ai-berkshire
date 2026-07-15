---
name: quant-metrics
description: "AI Berkshire skill: 量化五指标. Source: skills/quant-metrics.md."
---

## Codex adapter note

This skill is generated from `skills/quant-metrics.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 量化五指标

对 $ARGUMENTS 算 Alpha/Beta/夏普/最大回撤/信息比率并评价。

## 解决什么

脱离风险谈收益是耍流氓。`quant_metrics.py`(零依赖)算机构衡量"收益到底好不好"的五个核心指标，并给定性评价：

| 指标 | 含义 | 评价档 |
|---|---|---|
| **Beta β** | 对市场敏感度 | =1同步 · <0.8防御 · >1.2进攻 |
| **Alpha α** | 剔除β后的超额(詹森α) | >3%真超额 · <0靠β没本事 |
| **夏普比率** | 每单位总风险的超额 | >2优秀 · >1良好 · <0.5弱 |
| **最大回撤** | 峰谷最大跌幅(复利杀手) | <15%可控 · >30%大 |
| **信息比率 IR** | 相对基准超额/跟踪误差(主动技艺) | >1优秀 · >0.5良好 · <0跑输 |

## 执行流程
```bash
python3 tools/quant_metrics.py eval --from-datalayer "GOOGL=16,MTUM=14,VOO=14,..." \
    --benchmark SPY --period 2y --freq weekly --rf 0.04
```
输出五指标 + 评价，附跟踪误差与组合年化。

## 已内建到复盘与优化
- **`review.py --daily/--weekly/--quarterly`**：组合层自动算五指标 vs SPY 并评价(md+html)。
- **持仓优化报告**：`portfolio-optimization-report` 要求在尾部风险节附五指标评价(β防御性、α真超额、夏普/IR 效率)。

## 原则与诚实边界
- 基于历史区间、简单收益、单一基准；**α/β 随窗口漂移**，换基准/周期结论会变。
- 正 α 才是"真本事"——防御性组合(β<1)若还有正 α，说明超额非靠加杠杆(v10 实测 β0.76/α+10%即此类)。
- IR 衡量相对基准的主动技艺，>1 罕见且可能过拟合窗口；夏普/回撤看绝对风险效率。
- 指标是**结果的体检、非未来的保证**；不含黑天鹅(与 tail_risk 合看)。

## 相关
`portfolio-risk`(波动/相关) · `tail-risk`(VaR/CVaR) · `attribution`(收益归因) · `review`(复盘内建) · `portfolio-optimization-report`
