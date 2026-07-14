---
name: error-library
description: "AI Berkshire skill: 错误模式库与学习闭环. Source: skills/error-library.md."
---

## Codex adapter note

This skill is generated from `skills/error-library.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 错误模式库与学习闭环

沉淀犯过的错、事前验尸、从决策中学习：$ARGUMENTS。P4·治理。

## 解决什么

机构自我进化的最后一环：把"犯过的错"变成可复用的模式库，并在每次新决策前强制过一遍**事前验尸(premortem)**——这些坑你以前踩过，这次别再踩。`tools/error_library.py`（零依赖）三件事：

1. **错误模式目录**（`config/error_patterns.json`，入库）——价值投资 10 大经典陷阱（价值陷阱/成长陷阱/护城河误判/管理层轻信/宏观择时/锚定/确认/近因/过度下注/流动性忽视），每种含【事前信号】【规避清单】【哪位大师警告过】。
2. **事后验尸**——给已了结但"未中/亏损"的决策打错误模式标签（存 `data/portfolio/postmortems.jsonl`，私有）。
3. **学习报告**——统计各模式发生频次 + 结合 Brier 校准指出系统性偏差（如"成长股上系统性过度自信 +18%"）。

## 执行流程
```bash
python3 tools/error_library.py init                  # 播种目录(10种模式)
python3 tools/error_library.py checklist --verbose   # 事前验尸清单(下单前必过)
python3 tools/error_library.py tag --decision 3 --pattern growth_trap --lesson "低估了竞争,下次先证伪护城河"
python3 tools/error_library.py learn                 # 频次 + 自信校准偏差
```
- **checklist**：下单前逐条自问，任一「事前信号」命中 → 必须在决策日志 thesis 中回应，否则不下单。
- **learn**：`预测概率均值 − 实际命中率`>0 即系统性过度自信，给出主动下调幅度建议；再按信心档看落空率。

## 原则
- 验尸的价值在 `--lesson`：写下「下次怎么做不一样」，否则只是记账。
- 与 `decision-journal` 闭环：journal 记录 P(论点成立) → resolve → 未中的用本库 tag 归类 → learn 出系统性偏差 → 下次决策前 checklist 拦截。
- 频次排前的模式，优先在投研 skill 里建硬防线。

## 相关
`decision-journal`(Brier校准) · `model-registry`(模型治理) · `master-lens`(大师原则) · `sell-discipline`(卖出纪律)
