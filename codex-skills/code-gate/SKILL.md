---
name: code-gate
description: "AI Berkshire skill: 代码质量硬门禁. Source: skills/code-gate.md."
---

## Codex adapter note

This skill is generated from `skills/code-gate.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 代码质量硬门禁

零依赖 AST 静态检查，提交前拦截致命 bug 类：$ARGUMENTS。

## 解决什么

与 `report-audit`(报告门禁)对称——这是**代码门禁**。专治本项目反复踩的坑：**循环变量遮蔽外层同名变量**(如 `for horizon in...` 覆盖了之前的 horizon 字典、`for market,fn in...` 覆盖 market 字典),两次让复盘静默崩溃(TypeError)。单元测试(测纯函数)测不到这类集成层 bug,故静态检查兜底。

检查项：
- **loop-shadow(🔴 error,阻断)**：for 循环变量遮蔽同函数更早的**意义赋值**，且该名**只此一处**作循环目标(非临时名复用)、循环后**仍被读取**——精化三条件避免误报,只揪真 bug。
- **unused-import(🟡 warn)**：导入未使用。
- **syntax(🔴)**：语法错误。

## 执行流程
```bash
python3 tools/code_gate.py check --path tools/               # 扫目录(退出码 0=无error,1=有)
python3 tools/code_gate.py check --path tools/review.py --errors-only
```
**建议每次改工具后、提交前跑一遍**(退出码接 pre-commit/CI)。

## 精化逻辑(为何不误报)
真 bug(horizon/market)三特征缺一不可：① 有更早的**简单名赋值**(下标 `a[s]=`/属性不算绑定)；② 该名在函数内**仅此一处**作循环/推导目标(跨循环复用的 s/k/i/d 是约定临时名,跳过)；③ 循环**之后**仍读取该名(值已被覆盖)。实测 64 工具**零误报**。

## 相关
`report-audit`(报告门禁,对称) · `model-registry`(模型治理) · `lineage`(可追溯) — 共同构成"输出+代码+数据"三重治理。
