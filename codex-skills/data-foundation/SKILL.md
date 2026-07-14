---
name: data-foundation
description: "AI Berkshire skill: 数据地基：点时财务 + 公司行动 + 退市样本. Source: skills/data-foundation.md."
---

## Codex adapter note

This skill is generated from `skills/data-foundation.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 数据地基：点时财务 + 公司行动 + 退市样本

时间感知的数据底座：$ARGUMENTS。Tier 1（路线图最高优先级瓶颈）。

## 解决什么

工具再多，喂"当下快照"就永远做不了**可信的历史研究**。这三块地基让 backtest/factor/comps 摆脱三种系统性偏差：

| 工具 | 防哪种偏差 | 核心 |
|---|---|---|
| `pit_financials.py`（T1-1） | **前视偏差** | 存财报 + **披露日(available_at)**，历史查询只返回"当时已知"的数据 |
| `corporate_actions.py`（T1-2） | **复权/接续错误** | 拆股/分红/更名的复权因子与代码接续，历史收益才准确 |
| `delisting.py`（T1-3） | **幸存者偏差** | 退市/破产样本 + "当时在市"股票池，回测不在赢家里挑赢家 |

## 执行流程
```bash
# T1-1 点时财务：录入(available_at=披露日,非会计期末) → 无前视查询
python3 tools/pit_financials.py record --symbol GOOGL --metric revenue \
    --period 2025Q4 --value 96469 --available-at 2026-02-04 --source 10-K
python3 tools/pit_financials.py asof --symbol GOOGL --metric revenue --date 2026-01-15  # Q4未发→排除

# T1-2 公司行动：拆股/分红/更名 → 复权因子/持仓调整
python3 tools/corporate_actions.py record --symbol NVDA --type split --date 2024-06-10 --ratio 10
python3 tools/corporate_actions.py factor --symbol NVDA --date 2024-01-01              # 价格×0.1/股数×10

# T1-3 退市样本：录破产/并购 → 当时在市池 + 幸存者体检
python3 tools/delisting.py record --symbol LEHMQ --delisted 2008-09-15 --reason bankruptcy --terminal-return -1.0
python3 tools/delisting.py survivorship-check --date 2008-06-01
```

## 为什么是最高优先级
- **它是唯一卡住多条线的瓶颈**：backtest 检验估值信号、factor_library 的质量/规模因子、comps 历史分位——全都依赖点时数据。
- **一次做实、三个下游同时解锁真实性**；L4 的工具喂 L2 的数据 = 给跑车加劣质油。

## 原则与诚实边界
- **available_at 是灵魂**：录入财报务必填"披露日"而非"会计期末"——录错就退化成有前视的普通库。
- **引擎 vs 数据**：这三个工具是正确的**查询引擎**；数据靠手工/增量补录，非全市场数据库——覆盖不全时体检偏乐观，需诚实标注。
- 复权因子分红项需当时价格(前复权近似)；退市库空时幸存者体检无意义。

## 相关
`security-master`(PIT标的属性,与本组互补) · `backtest`(接入后可检验估值信号) · `factor-library`(质量/规模因子待接) · `comps`(历史分位) · `ledger`(持仓复权)
