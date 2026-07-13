---
name: us-consensus
description: "AI Berkshire skill: 美股一致预期：评级、前瞻 EPS、修正动量. Source: skills/us-consensus.md."
---

## Codex adapter note

This skill is generated from `skills/us-consensus.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 美股一致预期：评级、前瞻 EPS、修正动量

对 $ARGUMENTS（美股）拉取卖方一致预期与盈利修正方向。consensus.py 的美股版。

## 这个 skill 解决什么

补齐"A股有、美股缺"的一致预期口径。`/us-consensus` 用 `tools/us_consensus.py`（零依赖）合并两个免费源：机构评级趋势、EPS beat/miss 历史、前瞻一致 EPS 与**盈利修正方向**——量化"你的判断 vs 市场共识"。价格常由预期修正方向驱动，这是关键的叠加信息。

## 执行流程
```bash
python3 tools/us_consensus.py analyze AAPL
python3 tools/us_consensus.py analyze NVDA --json
```
输出：机构评级分布与倾向（Finnhub）、近 8 季 EPS beat 率与惊喜（Finnhub）、前瞻一致 EPS 高/中/低与估计家数、EPS CAGR、**近 4 周修正上调/下调家数 → 上修/下修**（Nasdaq）、前瞻 PE/PEG、反向解读。

## 数据源与 key
- **Finnhub**（免费 key）：评级趋势 + EPS beat/miss + metric。key 读环境变量 `FINNHUB_API_KEY` 或 `config/secrets.local.json`（已 gitignore、永不入库）。无 key 时自动降级为仅 Nasdaq 前瞻。
- **Nasdaq API**（无 key）：前瞻一致 EPS + 修正动量。非官方后端接口、免费但可能变动，已 try/except 优雅降级。

## 与其它工具的闭环
1. `/investment-research`+`dcf` 出**你自己**的估值与增长假设 → 2. **`/us-consensus` 看市场共识 + 修正方向** → 3. 认知差 = 你 vs consensus；修正在上修=动能正、下修=留意转弱 → 4. 结论写入 `decision-journal`，用实际 EPS 事后校准。美股持仓可再叠加 `/edgar-13f` 看机构在买卖什么。

## 原则
- **卖方系统性偏乐观**：卖出评级少，"看多 100%" 是常态；高度一致乐观 = 预期已充分定价，反而警惕。
- **EPS 为预测非事实**；用它看方向与情绪，不当确定数。
- **目标价/深度预期 Finnhub 免费档不含**（付费），自动跳过；Nasdaq 非官方、脆弱。
- 一致预期辅助看认知差，**永不替代自己的估值与研究**。

## 相关
`consensus`(A股版) · `edgar-13f`(机构实际在买啥) · `dcf`(自己的估值) · `earnings-review`(实际 vs 预期) · `decision-journal`(认知差校准)
