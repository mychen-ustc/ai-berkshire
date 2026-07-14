---
name: factor-library
description: "AI Berkshire skill: 基本面因子库（命名因子）. Source: skills/factor-library.md."
---

## Codex adapter note

This skill is generated from `skills/factor-library.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 基本面因子库（命名因子）

对 $ARGUMENTS 算价值/成长/动量/低波的横截面因子暴露。T2-1。

## 解决什么

`factor-model`(PCA) 给的是统计因子(PC1/PC2 无经济含义)；`/factor-library`(`tools/factor_library.py`，零依赖)给**带经济含义的命名因子**——回答两个机构核心问题：

1. **组合到底在押哪些因子？** 名义分散≠因子分散——"你 9 只标的，实则重仓 成长+动量"。
2. **候选池里哪些标的目标因子得分高？** 因子化选股的起点。

方法（对标 Barra/MSCI 风格因子）：原始因子值 → 横截面 winsorize 去极值 → z-score 标准化 → 组合暴露 = Σ 权重×z。

## 执行流程
```bash
python3 tools/factor_library.py analyze --symbols "GOOGL,AXP,COST,NDAQ,KO,BRK.B" \
    --weights "GOOGL=28,AXP=11,COST=7,NDAQ=7,KO=21,BRK.B=26"
python3 tools/factor_library.py rank --symbols "..." --factor value --top 10   # 因子化选股
```
- **个股 z 分表**：每只在 价值/成长/动量/低波 上的横截面相对强弱。
- **组合因子暴露**：>0 超配、<0 低配，标出主导因子倾斜(你真正的押注)。
- **因子间相关**：>0.5 提示两个"命名因子"其实是同一押注。

## 数据源与诚实边界
- 价值 = 前瞻盈利收益率 1/fwd_pe（`us_consensus`，美股）
- 成长 = 预期 EPS CAGR（`us_consensus`）
- 动量 = 12-1 月价格收益 · 低波 = −年化波动（`datalayer`，全市场）
- **⬜ 质量(ROE)/规模(市值) 需点时基本面库(路线图 Tier 1)未接入**——诚实标注缺口，不编数据。
- ETF 无个股基本面、非美股一致预期未接 → 价值/成长会缺失(动量/低波仍可算)。
- z 分是横截面相对值，样本少时不稳；单因子排序仅是筛选起点，须结合质检与估值。

## 与其它工具的关系
- `factor-model`(PCA统计因子·有效独立赌注) + `factor-library`(命名基本面因子) = 互补：前者答"分散够不够"，后者答"押的是什么因子"。
- 组合优化前先看因子暴露(避免风险平价掩盖的因子集中)；选股时用 `rank` 定向筛因子。

## 相关
`factor-model`(PCA伪分散) · `portfolio-optimizer`(权重) · `comps`/`us-consensus`(因子输入) · `portfolio-optimization-report`(报告引用因子暴露)
