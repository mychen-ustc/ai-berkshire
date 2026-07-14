---
name: model-registry
description: "AI Berkshire skill: 模型登记册. Source: skills/model-registry.md."
---

## Codex adapter note

This skill is generated from `skills/model-registry.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 模型登记册

治理量化模型的假设/局限/校验状态：$ARGUMENTS。P4·治理。

## 解决什么

机构模型风险治理（对标监管的 SR 11-7）：**任何"产出会进入投资决策的数字"的模型都必须在册**。`tools/model_registry.py`（零依赖）登记每个模型的用途、核心假设、已知局限、数据源、校验状态、上次校验日、复校周期、负责人。登记册本身入库（`config/model_registry.json`）作为可追溯的审计轨迹。

回答三个自省与监管都会问的问题：这个数字哪个模型算的、假设与失效条件是什么？上次校验多久了、还在有效期吗？报告用到的模型是不是都还"已校验"、没过期没弃用？

## 执行流程
```bash
python3 tools/model_registry.py init                 # 用当前工具链播种(15个核心模型)
python3 tools/model_registry.py audit --today 2026-07-14   # 过期/实验中/无测试 体检
python3 tools/model_registry.py show --id tail_risk        # 看单个模型假设与局限
python3 tools/model_registry.py validate --id tail_risk --date 2026-07-14 --by MartinChen
```
- **audit**：三类问题模型——🔴过期(超复校周期仍在用)、🧪实验中(产出未定稿)、⚠️无测试。
- **show**：把该模型的**核心假设**与**已知局限**摊开——局限不是缺陷，是使用边界。
- 新模型上线先 `add` 登记（默认 experimental），通过测试与复核后 `validate` 转 validated。

## 原则
- **无登记不上线**：报告里引用的每个量化数字，其模型都应在册且在有效期内。
- 局限要诚实写全（VaR 不含黑天鹅、DCF 对终值敏感、min-var 对协方差误差敏感……）——这才是治理的价值。
- 复校周期按模型敏感度设：风险/估值模型 180 天，基座/治理类 365 天。

## 相关
`report-audit`(报告门禁引用在册状态) · `error-library`(错误模式) · `decision-journal`(校准) · 各被登记的量化工具
