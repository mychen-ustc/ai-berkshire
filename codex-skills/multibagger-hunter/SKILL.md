---
name: multibagger-hunter
description: "AI Berkshire skill: 十倍股猎手：在共识之前找到高潜力赢家. Source: skills/multibagger-hunter.md."
---

## Codex adapter note

This skill is generated from `skills/multibagger-hunter.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 十倍股猎手：在共识之前找到高潜力赢家

对 $ARGUMENTS 从结构性趋势/热点板块出发，系统化挖掘可能有 10 倍空间的高潜力标的。

## 这个 skill 解决什么

项目现有 skill 几乎都在分析**大盘、已被充分覆盖、市场已定价**的名字——这些几乎不可能是下一个 10 倍股。`/multibagger-hunter` 补上"在共识之前发现赢家"的引擎（路线图最大 Alpha 空白）。

> ⚠️ **先立纪律**：10 倍股极稀有、失败率极高。这是**投机性 alpha 卫星**，按塔勒布杠铃/帕伯莱非对称——**小仓位、一篮子、允许多数归零、靠个别赢家拉动**。单只 ≤ IPS `alpha_sleeve_single_max_pct`(3%)、合计 ≤ `alpha_sleeve_total_max_pct`(15%)。**绝不重仓。**

## 执行流程

### 1. 定结构性顺风（联网找当期趋势）
从长期趋势出发（AI 算力/应用、人形机器人、创新药出海、存储超级周期、国产半导体替代、低空经济…）。用 `WebSearch` 找当期最强主线 + 拐点信号（量产/渗透率/政策）。

### 2. 建候选池（三个角度，别只看龙头）
- **龙头**（确定性高但 runway 有限——大象难 10 倍）
- **上游"卖铲子"**（卖水人，比整机稳）
- **小市值/早期玩家**（runway 最大、失败率最高）——**10 倍最可能来自这里**
经 `tools/datalayer.py`（行情）+ `/quality-screen` / `/industry-funnel` 缩小。

### 3. 十倍股 DNA 打分（10 维，逐条对照）
① 小市值基数 ② 长雪道(大 TAM+低渗透+S 曲线早期) ③ 可复制单位经济 ④ 高速可持续增长 ⑤ 戴维斯双击潜力 ⑥ 卓越资本配置创始人 ⑦ 隐藏期权(第二曲线) ⑧ 被市场忽视/看错 ⑨ 结构性顺风 ⑩ 赢家通吃早期。
**龙头 ≠ 10 倍股**：已大市值的龙头 10x 空间有限，须明确标注。

### 4. 每个候选深筛（投前必做）
- `/investment-research`（八模块深研，含估值/护城河/管理层/风险）
- `tools/forensic.py`（M-Score/Z-Score/应计——**防雷，尤其小盘/高成长/强周期**）
- `tools/dcf.py reverse`（当前价已隐含多高增长？低于你的判断=还有空间）

### 5. 仓位与组合（venture/杠铃）
`tools/position_sizing.py`：小仓位；一篮子多笔而非集中；允许单只归零，靠赢家拉动整体。

### 6. 诚实警示（不可省）
- 幸存者偏差极强（事后看都显而易见）、绝大多数会失败。
- 10 倍是**可能性**不是预测/预期；归零同样可能。
- 区分"高潜力"与"高估值故事股"——PS/PE 已透支极高预期的，10x 已被 price 进去。

## 输出
候选清单 + 10 维 DNA 评分 + 多空 + 建议仓位；默认写入 `reports/`。含真实持仓/规模的组合层放 `reports/private/`。

## 相关
`quality-screen` `industry-funnel`（筛）· `investment-research`（深研）· `forensic-accounting`（防雷）· `position_sizing`（定仓）· `master-lens`（塔勒布/帕伯莱镜片）
