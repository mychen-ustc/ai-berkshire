---
name: catalysts
description: "AI Berkshire skill: 事件/催化剂日历. Source: skills/catalysts.md."
---

## Codex adapter note

This skill is generated from `skills/catalysts.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 事件/催化剂日历

排出未来催化剂时间线：$ARGUMENTS。P3 运营骨架。

## 解决什么

把"未来会发生什么"排成时间线，驱动监控与复盘节奏。用 `tools/catalysts.py`（零依赖）：美股财报日(Finnhub) + 手动催化剂(从 watchlist 的 next_catalyst 汇总)，合并排序、临近(≤14天)高亮。

## 执行流程
```bash
python3 tools/catalysts.py earnings AAPL,GOOGL,NVDA          # 美股财报日 + EPS预期
python3 tools/catalysts.py upcoming --symbols "AAPL,GOOGL" --days 60
python3 tools/catalysts.py upcoming --from-watchlist --days 90   # 汇总 watchlist 催化剂
```

## 与其它工具的闭环
`watchlist-pipeline`(催化剂来源) · `earnings-review`(财报日到→精读) · `news-engine`(A股近期公告事件) · `decision-journal`(催化剂兑现校准)

## 原则
- 美股财报日来自 Finnhub(需 key)；**A股前瞻财报日暂无稳定免费源**，用 news-engine 补近期已发生事件(诚实缺口)。
- 手动催化剂靠人工维护(格式 `YYYY-MM-DD 描述`)。
- 日历只提示"何时关注"，不预测结果。
