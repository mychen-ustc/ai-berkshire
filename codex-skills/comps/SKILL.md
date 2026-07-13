---
name: comps
description: "AI Berkshire skill: 可比公司相对估值：贵还是便宜，看同业. Source: skills/comps.md."
---

## Codex adapter note

This skill is generated from `skills/comps.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 可比公司相对估值：贵还是便宜，看同业

对 $ARGUMENTS（可比同业列表）做 PE/PB/市值横截面 + PEG。

## 这个 skill 解决什么

DCF 是绝对估值；`/comps` 用 `tools/comps.py`（零依赖）给**相对估值**——把一只股票放进可比同业，看它相对同业中位的溢价/折价，与 DCF 互为交叉验证（"绝对 vs 相对"，两条腿都指向便宜才更可信）。

## 执行流程
```bash
python3 tools/comps.py analyze "600519,000858,000568,600809" --peg --anchor 600519   # 白酒
python3 tools/comps.py analyze "603986,688981,002049"                                 # 半导体
```
输出：每只 PE / PB / 市值 / 相对同业中位溢价折价%，`--peg` 加一致预期 EPS 增速与 PEG；标注同业最低估/最高估。数据来自腾讯行情（PE/PB/市值）+ 东财一致预期（PEG，复用 consensus）。

## 与其它工具的闭环
1. `dcf` 出**绝对**内在价值 → 2. **`/comps` 看相对同业贵贱** → 3. 二者都指向低估才加仓；背离时深究原因（是真便宜还是盈利要塌）→ 4. 结合 `consensus` 看增速预期、`forensic` 排雷。

## 原则
- **可比性由你判断**：本工具不做行业自动成员——把银行和白酒放一起没意义；同业要业务、周期、资本结构相近。
- **PE 低 ≠ 便宜**：可能是盈利即将下滑（分母要跌）导致的"价值陷阱"；洋河式高 PE+低 PB 常是盈利坑。务必结合增速与质量看。
- **仅 PE/PB/市值(+PEG)**：PS/EV-EBITDA 需营收/EV，本版本未接（不同盈利模式不可比时 PE 会误导）。
- **仅 A 股**（腾讯字段位）；港美股字段位不同、未接入；亏损（负 PE）已从中位剔除。
- 相对估值给**位置**，不给买卖结论；不单独下结论。

## 相关
`dcf`(绝对估值·交叉验证) · `consensus`(增速预期/PEG) · `forensic-accounting`(便宜是否有雷) · `industry-research`(可比性判断)
