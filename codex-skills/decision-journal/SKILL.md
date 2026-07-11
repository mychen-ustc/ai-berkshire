---
name: decision-journal
description: "AI Berkshire skill: 决策日志：记录每个买卖决策，事后校准\"你到底准不准\". Source: skills/decision-journal.md."
---

## Codex adapter note

This skill is generated from `skills/decision-journal.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 决策日志：记录每个买卖决策，事后校准"你到底准不准"

对 $ARGUMENTS 记录一次投资决策，或复盘已了结决策的校准情况。

## 这个 skill 解决什么

研究界普遍**只记结论、不记决策质量**。机构自我进化的核心是：**把每个决策的论点、概率、触发器写下来，事后用结果检验当初的判断到底准不准**（决策校准）。把"我觉得七成会涨"变成可问责、可复盘的量化记录。

工具：`tools/decision_journal.py`（零依赖）。真实记录存 `data/portfolio/decisions.jsonl`（gitignore，不入库）。

## 执行流程

### 记录决策（买入/卖出/放弃前必做）
先过**镜子测试**（≤200字说清 5 件事，说不清就不买），并对"论点成立"赋一个概率：

```bash
python3 tools/decision_journal.py add \
  --date {今天} --action BUY --symbol {代码} --price {价} --currency {币} \
  --size {目标仓位%} --conviction {1-5} --p-base {P(论点成立)0-1} --target {基准目标价} \
  --horizon {月} --thesis "{≤200字：生意/护城河/管理层/价格/最坏情况}" \
  --triggers "{卖出触发器1}" "{触发器2}"
```

必须回答（缺一不可，呼应 `investment-checklist` 与 `docs/INVESTMENT-MANDATE.md` 风险预算）：
- 论点一句话是什么？P(论点成立)=多少？（诚实赋概率，别都写 0.9）
- 目标价与持有期？仓位是否符合 IPS 单一/行业上限？
- **卖出触发器**：什么情况下认错离场？（无触发器 = 没想清楚就买）

### 了结决策（触发器命中 / 到期 / 论点证伪）
```bash
python3 tools/decision_journal.py resolve --id {N} --date {日期} --price {了结价}
```

### 定期校准复盘（季度/年度）
```bash
python3 tools/decision_journal.py calibrate
```
输出 **Brier 分数**（0=完美，0.25=瞎猜）、总命中率、**校准表**（预测概率 vs 实际命中，看你系统性高估还是低估）、按信心分层命中率。

## 输出要求
1. 记录时必须包含论点、概率、触发器三要素，缺失要显式提示。
2. 校准复盘要**诚实面对高估**：如果"你说 80% 会成的事实际只成了 50%"，直说——这正是这个 skill 的价值。
3. 客观、不粉饰；坏决策比好决策更该记录（错题库）。

## 相关
- `investment-checklist`：买入前六关 + 镜子测试（决策的输入）
- `performance-attribution`：收益归因（决策的结果）
- `tools/ledger.py`：实际成交账本（与决策日志互为印证）
