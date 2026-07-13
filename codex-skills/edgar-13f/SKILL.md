---
name: edgar-13f
description: "AI Berkshire skill: SEC 13F：机构大佬在买什么、加减了什么. Source: skills/edgar-13f.md."
---

## Codex adapter note

This skill is generated from `skills/edgar-13f.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# SEC 13F：机构大佬在买什么、加减了什么

对 $ARGUMENTS（机构 CIK/别名）拉取 SEC 13F 季度持仓与环比调仓。

## 这个 skill 解决什么

看一手披露的"聪明钱"——巴菲特、达利欧等机构上季末持有什么、加减/新建/清仓了什么。`/edgar-13f` 用 `tools/edgar_13f.py`（零依赖）直连 **SEC EDGAR 官方数据**（完全免费、无 key）。补 P4-8 资金面的美股版。它是叠加层——**启发与验证，永不替代自己的基本面研究**（别人的持仓不是你的买入理由）。

## 执行流程
```bash
python3 tools/edgar_13f.py holdings --fund berkshire --top 15   # 最新 13F Top 持仓
python3 tools/edgar_13f.py changes --fund berkshire             # 最近两期环比：新建/加/减/清仓
python3 tools/edgar_13f.py holdings --cik 1350694               # 用 CIK 直接指定
python3 tools/edgar_13f.py funds                                # 内置机构别名(伯克希尔/桥水/Scion/Pershing…)
```

## 数据源
- **SEC EDGAR**：`data.sec.gov/submissions` 找 13F-HR 归档 → `Archives/edgar` 取信息表 XML（infoTable）→ 按 cusip 合并持仓。官方、免费、无 key（仅需 UA 声明 + ≤10 req/s）。

## 与其它工具的闭环
1. `/edgar-13f changes` 看大佬调仓（如巴菲特加仓 Alphabet/清仓 Visa）→ 2. 作为**候选来源或论点验证**，不是买入信号 → 3. 对感兴趣标的走 `/investment-research`+`dcf` 自己研究 → 4. `/us-consensus` 看市场预期、`/technical-analysis` 看择时。

## 原则
- **13F 滞后**：季度末后最多 45 天才披露；反映"上季末持有"、非实时——大佬可能早已调仓。
- **只含美股多头**：不含做空、现金、海外、部分期权按名义列示；不代表全部风险敞口。
- **别人的持仓不是你的理由**：大佬也会错、成本与期限和你不同；13F 用来启发和交叉验证，不照抄。
- 官方数据、可长期依赖（不同于非官方接口）。

## 相关
`us-consensus`(市场预期) · `money-flow`/`holdings-tracker`(A股资金/龙虎榜) · `investment-research`(自己研究) · `master-lens`(大师框架)
