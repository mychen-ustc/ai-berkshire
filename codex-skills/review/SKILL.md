---
name: review
description: "AI Berkshire skill: 定期复盘：投资组合与 watchlist 的心跳. Source: skills/review.md."
---

## Codex adapter note

This skill is generated from `skills/review.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 定期复盘：投资组合与 watchlist 的心跳

对 $ARGUMENTS（默认当前账本）跑一轮定期复盘。P3 运营节奏。

## 解决什么

把"研究—持有—复盘"从一次性动作变成**固定节奏**，并做**三层五面全面诊断**供人工校验是否更新组合/观察名单。`tools/review.py`（零依赖、纯 Python、无需 LLM，可挂 cron）：

## 执行流程
```bash
python3 tools/review.py --from-ledger data/portfolio/transactions.csv --weekly [--html]
python3 tools/review.py --daily        # 盘前轻量：告警 + 今日到期 + ≤7天催化剂
python3 tools/review.py --quarterly     # 季度：+ 归因/IPS 复审提醒
bash scripts/install-review-cron.sh     # 装 cron：每周一 + 每季首日自动跑
```

输出（行动清单置顶，三层五面）：
- **🎯 执行摘要 + 行动清单**：市场判断 + 到期复审 / 临近催化剂 / 触发红线 / 反转观察。
- **① 市场五面摘要**：宏观 regime(基本面) · 大盘指数趋势(技术面) · A股涨跌停广度(资金面) · 三市场恐惧贪婪+VIX(情绪面) · 财报季密度(消息面) → **市场结论(是否调整敞口)**。
- **② 组合层**：有效独立因子 + PC1 + 因子倾斜。
- **③ 逐持仓五面诊断**：每只摘出 基本/技术/资金/情绪/消息 + 综合告警(🔴技术转弱/主力派发/盈利下修 · 🟡极度贪婪 · 🟢极度恐惧) + 对照 watchlist 红线。
- **④ Watchlist 诊断**：非持仓/退出标的的五面 + **反转信号**(极度恐惧+主力吸筹→候选；再+趋势转多→确认)。
- **⑤ 到期复审 / 催化剂　⑥ 组合 & Watchlist 更新建议**（自动汇总，须人工拍板）。

## 与运营节奏的闭环
1. `watchlist` 录入持仓(论点/红线/复审日) → 2. **`/review` 定期跑**(cron 每周) → 3. 行动清单驱动:红线触发→深研/减仓、复审到期→更新论点、催化剂临近→财报精读 → 4. 决策写回 `watchlist set/catalyst` 与 `decision-journal`。

## 原则
- **红线是提示、须人工判断**：review 只做机械信号刷新(技术/资金/情绪/预期)，是否行动由人定。
- **复盘非预测**：信号聚合帮你不漏事、按节奏走;五面皆叠加层、不替代基本面。
- **含真实持仓**：报告存 reports/private/reviews/(gitignore)、不入库。

## 相关
`portfolio-scan`(复用其采集) · `watchlist-pipeline`(到期/红线来源) · `catalysts`(催化剂) · `decision-journal`(决策留痕) · `sell-discipline`(红线触发后的卖出纪律)
