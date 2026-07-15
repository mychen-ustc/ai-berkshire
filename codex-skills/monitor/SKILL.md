---
name: monitor
description: "AI Berkshire skill: 运营监控与健康检查. Source: skills/monitor.md."
---

## Codex adapter note

This skill is generated from `skills/monitor.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 运营监控与健康检查

系统心跳监测：$ARGUMENTS。让机器出问题时"会喊你"。

## 解决什么

64 个工具 + cron 会跑，但没有监控——数据源挂了、cron 静默失败、数据变陈旧,没人知道。`monitor.py`(零依赖)是运营底线:从"会跑的脚本"变"可信赖的机构"。

四类检查：
1. **数据源健康**：canary 探测各市场行情(A股东财/美股Yahoo/港股东财) + SEC EDGAR 可达性/新鲜度。
2. **cron 心跳(dead-man's-switch)**：复盘日志多久没更新?超预期间隔 1.5× 即🔴(cron 可能已停)。
3. **数据新鲜度**：账本/watchlist/T1候选池/点时库 关键文件的更新时效。
4. **健康看板**：🟢/🟡/🔴 逐项 + 总体;有🔴则**非零退出码**(接 cron/CI 告警)。

## 执行流程
```bash
python3 tools/monitor.py check          # 全面体检(退出码 0=健康,1=有🔴)
python3 tools/monitor.py check --json
```
建议加入 cron(每日),🔴 时触发通知。

## 原则与诚实边界
- **行情新鲜度在交易时段外天然偏旧**——仅极端过期(>96h)才告警,避免夜间/周末误报。
- cron 心跳用日志 mtime 作 dead-man's-switch(周频预期);装 cron 后才有意义。
- 监控是**运营底线,非投资信号**;它保证"系统在正常运转",不判断"该不该买"。

## 相关
`install-review-cron.sh`(cron调度) · `review`(被监控的复盘) · `lineage`(可追溯) · `model-registry`(模型治理)
