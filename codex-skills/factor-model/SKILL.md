---
name: factor-model
description: "AI Berkshire skill: 多因子风险模型：真分散还是伪分散. Source: skills/factor-model.md."
---

## Codex adapter note

This skill is generated from `skills/factor-model.md` so Claude Code and Codex users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current Codex thread.
- When the source mentions Claude-only surfaces such as Task, Agent, WebSearch, Bash, Read, or Write, use the closest Codex capability available in this session: subagents when available, web search when needed, shell commands for local tools, and normal file edits for workspace files.
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`; if the current thread starts outside the repo, locate the actual checkout path first instead of assuming a fixed home-directory path.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

# 多因子风险模型：真分散还是伪分散

对 $ARGUMENTS（组合/标的列表）做因子暴露与风险集中度分解。

## 这个 skill 解决什么

回答机构风控的分水岭问题：**"这份分散是真的吗？超额是 alpha 还是 beta？风险压在哪个共同因子上？"** `portfolio_risk` 看总波动与两两相关；`/factor-model` 用 `tools/factor_model.py`（零依赖）做更深一层——收益相关矩阵的 PCA，把"名义 10 只持仓"还原成"几个真正独立的赌注"。

## 执行流程
```bash
python3 tools/factor_model.py analyze --from-datalayer "VOO,AAPL,GOOGL,BRK.B,COST,KO,AXP,603986,9660.HK,06082.HK" \
    --weights "VOO=14,AAPL=12,..." --benchmark VOO --freq weekly --period 2y
python3 tools/factor_model.py analyze --from-ledger reports/private/xxx.csv --fx "USD=1,HKD=0.128,CNY=0.14"
```

输出：
- **风险集中度（PCA）**：名义持仓数 vs **有效独立因子数**（participation ratio）、PC1 方差占比（单一共同因子主导度）、PC1–3 累计。判定 🟢真分散 / 🟡中度集中 / 🔴伪分散。
- **PC1 主导因子载荷**：谁在被同一个共同因子驱动（通常 PC1≈市场）。
- **系统性暴露**：组合对基准的 beta 与 R²（多少收益由市场解释）。
- **特征因子倾斜**：动量(12-1月) / 波动 的组合加权 z 分（偏动量/反转、偏高波/低波）。

## 与其它工具的闭环
1. `portfolio_optimizer` 给权重 → 2. `portfolio_risk` 看波动/回撤/相关性 → 3. **`/factor-model` 看因子暴露与伪分散** → 4. 若 PC1 过高或有效因子数骤降，回到优化器加因子/行业约束（P4-2）。

## 原则
- **PC 是统计因子**，需事后解读：PC1 常≈市场，PC2/3 可能是行业/地域/风格——不要臆断命名。
- **价值/质量/成长/规模因子需横截面基本面库**，本工具当前只做价量/收益驱动的因子（诚实缺口，见路线图 P4-1）。
- 相关性/特征值在**短窗口不稳**；新股截断会放大 PC1 主导度——先看窗口期数再下结论。
- 因子模型**诊断风险结构，不预测收益**；它告诉你"风险压在哪"，不告诉你"买什么"。

## 相关
`portfolio-review` · `portfolio_risk.py`(波动/相关性) · `portfolio-optimizer`(加约束) · `master-lens`(达利欧·真分散)
