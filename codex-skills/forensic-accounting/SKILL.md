---
name: forensic-accounting
description: "AI Berkshire skill: 会计取证：给财报验伤，防踩雷. Source: skills/forensic-accounting.md."
---

## Codex adapter note

This skill is generated from `skills/forensic-accounting.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 会计取证：给财报验伤，防踩雷

对 $ARGUMENTS 做会计造假与暴雷预警筛查。

## 这个 skill 解决什么

`financial_rigor` 有 Benford 但无成体系的取证。`/forensic-accounting` 用 `tools/forensic.py`（零依赖）成套验伤——**防守价值极高：避开一个雷 = 少亏 50%**。尤其适用于高成长/强周期/小盘/新上市这类"业绩太好看"的标的。

## 执行流程

按 `skills/financial-data.md` 取近两年关键财务项（两源交叉），然后：

### 1. 盈利质量（最快、最常用）
```bash
python3 tools/forensic.py quality --ni {净利润} --cfo {经营现金流} --ta {总资产}
```
- 应计比率 (NI−CFO)/TA 高 → 盈利未由现金支撑；
- **净利润为正但经营现金流为负 → 纸面利润暴雷前兆**（如存储/工程/地产常见）。

### 2. Beneish M-Score（盈余操纵概率，8 变量）
```bash
python3 tools/forensic.py mscore --dsri .. --gmi .. --aqi .. --sgi .. --depi .. --sgai .. --tata .. --lvgi ..
```
各指数为当年/上年比值；M > −1.78 提示可能操纵。重点看应收/收入(DSRI)、毛利(GMI)、总应计(TATA)。

### 3. Altman Z-Score（破产风险）
```bash
python3 tools/forensic.py altman --wc-ta .. --re-ta .. --ebit-ta .. --mve-tl .. --sales-ta ..
```
&gt;2.99 安全 · 1.81–2.99 灰色 · &lt;1.81 困境。

## 红旗清单（人工补充，工具之外）
应收/存货增速远超营收、经营现金流持续 &lt; 净利润、商誉占净资产高、频繁变更审计/会计估计、关联交易与体外循环、大股东高质押/减持、非经常损益撑利润。

## 原则
- 取证是**证伪**工具：目的不是证明干净，而是尽力找出可能的问题（芒格：反过来想）。
- 触发任一红旗 → 回原始财报/附注核实，不得直接使用；宁可错杀，不可踩雷。

## 相关
`financial-data`（取数交叉验证）· `investment-research`（第四步·芒格逆向）· `earnings-review`（一手财报）· `master-lens`（塔勒布生存镜片）
