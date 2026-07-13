---
name: scuttlebutt
description: "AI Berkshire skill: 闲聊法调研：把二手财报升级为一手信息优势. Source: skills/scuttlebutt.md."
---

## Codex adapter note

This skill is generated from `skills/scuttlebutt.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 闲聊法调研：把二手财报升级为一手信息优势

对 $ARGUMENTS 生成菲利普·费雪"闲聊法(scuttlebutt)"一手调研清单。

## 这个 skill 解决什么

机构真正的信息 edge 来自**一手调研**，不是读财报。费雪的闲聊法：遍访客户、供应商、竞争对手、离职员工，拼出财报看不到的真相。本 skill 把它清单化、可执行——也是 `investment-research` C 级公司"第一性原理"的操作版。

## 执行流程

### 1. 生成四类访谈对象的问题清单
- **客户**：为什么买它而不是竞品？会不会换？愿意为它涨价吗？复购/粘性来自什么？
- **供应商/渠道/经销商**：它的议价力如何？回款账期？订单趋势(环比)？库存健康吗？
- **竞争对手**：谁最难缠？它的真实弱点？价格战激烈吗？
- **离职员工**：管理层真实为人与决策风格？组织/文化问题？研发/交付的真实瓶颈？

### 2. 费雪 15 要点（重点覆盖 AI/财报最难判断的项）
销售组织质量、研发转化效率、利润率可持续性与趋势、管理层诚信与深度、劳资关系、对短期利润的态度、长期成长跑道、是否有"护城河式"的独特性。

### 3. 渠道验证与另类数据（可行时）
门店/终端走访、App 下载/评分、招聘岗位、招投标、行业展会、专家网络访谈（合规前提下）。

### 4. 记录模板与证伪
每条发现标注来源与可信度；刻意寻找**与公司叙事矛盾**的信号（芒格：反过来想）。

## 原则
- 一手信息 > 二手研报 > 公司 PR。
- 合规红线：不打探内幕/未公开重大信息；只做公开可得的调研。
- 与 `decision-journal` 联动：把一手发现写进买入论点，事后校准是否成立。

## 相关
`investment-research`（第一性原理/一手验证清单）· `management-deep-dive`（管理层）· `news-pulse`（事件）· `decision-journal`（论点记录）
