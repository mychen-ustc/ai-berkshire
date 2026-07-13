---
name: consensus
description: "AI Berkshire skill: 一致预期跟踪：你的判断 vs 市场共识. Source: skills/consensus.md."
---

## Codex adapter note

This skill is generated from `skills/consensus.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 一致预期跟踪：你的判断 vs 市场共识

对 $ARGUMENTS 拉取卖方一致预期与前瞻估值。

## 这个 skill 解决什么

价格常由**预期修正方向**驱动，而非绝对水平。`/consensus` 用 `tools/consensus.py`（零依赖）拉 A 股卖方一致预期，回答：机构覆盖多少、评级偏乐观还是谨慎、未来几年 EPS 预期增速多快、结合现价的前瞻 PE/PEG——**市场是否已把成长充分定价**。核心用途是量化"你的判断和 consensus 差多少"。

## 执行流程
```bash
python3 tools/consensus.py analyze 600519
python3 tools/consensus.py analyze 300750 --json
```

输出：机构覆盖数、评级分布（买入/增持/中性/减持/卖出）与倾向、前瞻 EPS 序列（当年实际 + 未来 3 年预测）与同比增速、EPS CAGR、前瞻 PE、PEG，以及反向解读（高度一致乐观/PEG 过高的定价警示）。

## 与其它工具的闭环
1. `/investment-research`+`dcf` 出**你自己的**估值与增长假设 → 2. **`/consensus` 看市场共识预期** → 3. 差异即认知差：你更乐观（可能有 edge）还是更悲观（可能漏看利空）→ 4. 结论与差异写入 `decision-journal`，事后用实际 EPS 校准谁对。

## 原则
- **卖方一致预期系统性偏乐观**：卖出评级极少，"买入占比 100%" 是常态而非强信号；反而要警惕"高度一致乐观 = 预期已充分定价"。
- **EPS 是预测、非事实**：预测会被反复修正；用它看方向与市场情绪，不当确定数。
- **本版本是最新快照**：尚无"盈利修正动量"时间序列（修正在往上还是往下调，是更强的信号，待补 P4-4）。
- **仅 A 股**（东财）；美股一致预期需 Finnhub/FMP 等带 key 的源（Yahoo 已 crumb 锁），本版本未接入。
- 一致预期辅助看认知差，**永不替代自己的估值与研究**。

## 相关
`investment-research`(自己的判断) · `dcf`(自己的估值) · `earnings-review`(实际 vs 预期) · `decision-journal`(认知差留痕与校准)
