---
name: industry-chain
description: "AI Berkshire skill: 产业链图谱. Source: skills/industry-chain.md."
---

## Codex adapter note

This skill is generated from `skills/industry-chain.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 产业链图谱

上下游/替代关系图，找"卖铲人" + 传导路径：$ARGUMENTS。T3-3。

## 解决什么

`industry_chain.py`(零依赖)维护产业链结构图，支持两类研究：
1. **"卖铲子"发现**：一个主题(如 AI)最确定的受益者常在**上游**(给淘金者卖铲子的)，而非最热的下游应用。图谱帮你从主题顺藤摸到上游卖铲人。
2. **传导路径**：一个环节的景气/冲击如何沿链条传导(AI应用→云算力→AI服务器→GPU→晶圆代工→光刻机)。

图谱是**参考知识**(公开产业结构)，存 `config/industry_chain.json`(入库可版本化)，播种 AI/半导体链示例，可 add-edge 扩充。

## 执行流程
```bash
python3 tools/industry_chain.py init                          # 播种 AI 链
python3 tools/industry_chain.py shovels --theme AI应用 --min-depth 3   # 上游卖铲人(按深度)
python3 tools/industry_chain.py path --from AI应用 --to 光刻机   # 传导路径
python3 tools/industry_chain.py neighbors --node GPU           # 某环节上下游/替代
python3 tools/industry_chain.py add-edge --from HBM --to 先进封装 --type 上游
```
- **shovels**：深度越大=离应用越远、越基础设施、越"卖铲人"(实测 AI应用→GPU/HBM/晶圆代工/光刻机)。

## 原则与诚实边界
- **结构图非景气数据**：只有关系、无实时份额/景气；节点是"环节/公司类别"，落到具体标的仍需自下而上研究 + 估值。
- **卖铲子不等于稳赚**：上游确定性高，但也要看竞争格局与估值(卖铲人若过度竞争/估值透支同样亏)。
- 关系是人工整理的定性图，非全产业链数据库——覆盖取决于补录。

## 相关
`industry-research`/`industry-funnel`(行业研究) · `sector-rotation`(景气轮动) · `radar`(机会发现) · `multibagger-hunter`(新兴赢家)
