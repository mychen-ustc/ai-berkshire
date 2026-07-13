---
name: money-flow
description: "AI Berkshire skill: 资金面分析：谁在买，吸筹还是派发. Source: skills/money-flow.md."
---

## Codex adapter note

This skill is generated from `skills/money-flow.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 资金面分析：谁在买，吸筹还是派发

对 $ARGUMENTS 给出客观的资金流读数，用来**验证或证伪**（不是产生）投资论点。

## 定位（最重要）

资金面回答的是"**聪明钱在做什么**"：主力在吸筹还是派发？量价是否背离？它是叠加层——**先有基本面理由，再看资金面是否配合**：

- 基本面看好 + 资金面确认流入 → 论点被市场投票，择时可更从容。
- 基本面看好 + 资金面持续流出 → 要么市场还没发现（机会），要么你漏看了利空（复核）。
- 基本面存疑 + 资金面派发（顶背离）→ 强化回避。

资金面**不能单独构成买入理由**——追资金流本身就是投机。

## 两类口径（诚实区分可得性）

**① 价量代理（全市场通用，由 OHLCV 计算）**
- MFI(14)：成交量加权 RSI，>80 资金过热、<20 枯竭。
- CMF(20)：蔡金资金流，>0 净流入、<0 净流出。
- OBV / A-D 线：能量潮与累积/派发线的近端方向。
- **量价背离**：价创新高但 OBV 不跟 = 派发预警🔴；价创新低但 OBV 未创新低 = 吸筹迹象🟢。

**② A/H 主力资金流（东财逐笔单量分类，单位元）**
- 超大单/大单 = 主力；中单/小单 = 散户。
- 主力近1/5/10日净额、窗口累计、连续净流入天数、主力占成交比。
- **结构识别**：超大单进+散户出 = 典型吸筹；超大单出+散户接 = 典型派发。
- ⚠️ 美股无逐笔"主力"口径，只能用①。

**③ 北向资金**：沪深港通自 **2024-08 起停止实时净流入披露**，本工具不拟合该失效口径（避免用作废数据误导），改以主力资金流 + 价量代理替代。

## 执行流程
```bash
python3 tools/moneyflow.py analyze 600519 --days 60   # A股：价量代理 + 主力资金流
python3 tools/moneyflow.py analyze 0700.HK            # 港股：同上
python3 tools/moneyflow.py analyze AAPL               # 美股：仅价量代理
python3 tools/moneyflow.py analyze --csv data/x.csv   # 离线 OHLCV（仅价量代理）
```

## 与其它工具/skill 的闭环
1. `/investment-research` 出基本面论点 →
2. `/money-flow` 看资金是否配合（主力吸筹/派发、量价是否背离）→
3. `/technical-analysis` 看趋势与择时（资金面与技术面互印证）→
4. `/portfolio-review` 综合决策。

## 原则
- **看趋势不看单日**：单日大额常受打新、指数调仓、大宗交易、季末窗口干扰。
- 两个口径**可能分歧**（如价量代理示净流出、但近5日主力转净流入）——如实呈现分歧，不硬凑一致结论；分歧本身是信息。
- 主力资金流是**事后统计的单量分类估算**，非真实席位持仓（真实席位看龙虎榜/大股东变动，属另一层）。
- 资金面**滞后**且噪声大；它确认或质疑论点，但从不替代基本面与估值。

## 相关
`technical-analysis`（技术面·互为印证） · `investment-research`（基本面·先行） · `forensic-accounting`（现金流验伤） · `master-lens`（段永平：别被市场情绪带节奏）
