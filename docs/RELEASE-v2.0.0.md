# v2.0.0 · 机构级投研平台

> 从「投研 Skill 合集」跃迁为「机构级投研平台」：真实数据地基 + 因子/风险/回测 + 治理 + L5 运营化 + 13 位大师框架。自 v1.0.0（2026-04-07）起 **1345 提交**，**73 工具 · 519 回归测试全绿 · 41 登记模型 · 78 skill，全零依赖（纯 stdlib）**。

## 一句话

v1.0.0 是"给 Claude Code 的价值投资 Skill 合集"；v2.0.0 是**在真实数据上、自动运转、可追溯复现的机构级投研平台**。

## 🗄️ 数据地基（Tier 1，防三大偏差）
- `pit_financials` 点时财务库（`available_at`=披露日，无前视）；`corporate_actions` 三市场复权（美/港 Yahoo、A股东财分红送配）；`delisting` 退市样本（防幸存者）；`security_master` 证券主数据。
- 真数据摄取：`edgar_financials`（SEC EDGAR，25 美股 703 条）+ `ashare_financials`（东财业绩报表，13 A股，公告日=available_at）+ `ingest_universe` 一键摄取编排器 + 新鲜度清单。

## 📊 估值 / 因子 / 风险 / 回测
- 估值：`dcf`（全程 Decimal + reverse-DCF）· `comps` · `statement_model`（三表勾稽）· `industry_valuation` · `scenario` · `morningstar_fair_value`。
- **L3 交叉验证支柱**：`valuation_cross_check`（DCF↔comps↔市价三角）+ `signal_calibration`（信号前瞻收益 vs 基线 edge）。
- 因子：`factor_library` Barra 式六因子（价值/质量/成长/动量/低波/规模）+ `factor_risk` 组合风险归因 + `factor_model`。
- 风险：`portfolio_risk`（HHI/IPS/相关性）· `tail_risk`（VaR/CVaR/压力）· `quant_metrics`（Alpha/Beta/夏普/最大回撤/信息比率）。
- 回测：`backtest_rigorous`（量化幸存者/前视/复权三偏差）· `horizon_compare`（1/3/5/10/15/20 年 × 美 A 港指数）· `attribution`（Brinson）· `tca`（交易成本）。

## 🧭 五面研究 + 机会流水线（美/A/港三市场）
- 五面：`technicals` · `moneyflow`（主力资金）· `sentiment` · `news_engine` · `sector_rotation`。
- `pipeline` 三级机会流水线（T1 候选/T2 观察/T3 持仓 + 降级级联 + 多市场带印证线索：A股龙虎榜 / US 13F / 港股通南向）。

## 🏛️ 治理（L4）
- `model_registry`（41 模型，method/assumptions/limitations/tests/`--strict` 硬门禁）· `code_gate`（AST 循环变量遮蔽/语法）· `lineage`（可复现签名）· `report_audit`（报告门禁）· `error_library`（错误学习）· `decision_journal`（决策校准）。

## ⚙️ 运营化（L5，本版核心）
- `monitor`（数据源/cron 心跳/**自动运行审计**/数据新鲜度，🔴 非零退出）· `notify`（桌面/飞书·Slack webhook/告警日志，接 monitor/cron/CI 失败）· `run_audit`（每次自动运行留 run-id+git SHA+结果，可 `git checkout` 复跑）。
- `install-ingest-cron.sh`（周摄取 + 日 monitor 无人值守）· `.github/workflows/ci.yml`（每 push/PR 强制跑测试 + code_gate + 治理 `--strict`，**GitHub Actions 绿灯**）。
- **L5 四要件（自动运转 + 漂移监控 + 结果通知 + 可重放审计）全部落地——运营与编排域达 L5。**

## 👥 13 位大师框架
- 默认阵容 **4 核心（巴菲特/芒格/段永平/李录）+ 9 国际（马克斯/达利欧/费雪/林奇/卡拉曼/格雷厄姆/帕伯莱/博格/塔勒布）= 13 位镜头**，`master-lens` 镜头库 + "大师异见庭"（分歧不抹平）。

## 🔬 全链路能力诊断
- 12 域经对抗验证诊断评级（加权 3.3/5 起点 → 本版多域实质提升）；诊断即修复的止血批次；`docs/全链路能力诊断评级` + `docs/信号与策略路线图`。

## ⚠️ 行为变更（Behavioral）
- **多师分析默认 13 位（不再默认只用四大师）**：`investment-team`（4 核心 + 9 国际并行）、`earnings-team`、`investment-research` 等已改；收缩阵容须在报告显式标注取舍。
- `model_registry audit` 新增 `--strict`（validated 却无测试文件即非零退出，供 CI 硬门禁）。

## 🧱 诚实边界（不吹）
- 数据仍是"高置信起始集"：退市库仅 4 条 textbook、A 股成长因子刻意不做（无免费前瞻源）、免费数据源可能漏。
- 回测为历史重建、非未来保证；估值多为单源，重大结论需第二源交叉。
- 零依赖是卖点也是约束（显著性数学需手写或隔离 CI）。
- 私密数据（真实持仓/账本/候选池/点时库/血缘/审计）全部 gitignore，不入库。

---

*规模基线：73 工具 · 519 回归测试全绿 · 41 登记模型 · 78 skill · 全零依赖。*
*诚实边界与后续方向见 `docs/全链路能力诊断评级-20260716.md` 与 `docs/信号与策略路线图-20260717.md`。*
