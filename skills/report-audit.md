# 报告审计：AI 硬门禁 + 数据抽检

发布前双关卡把守报告质量：$ARGUMENTS。P4·治理。

## 解决什么

任何报告发布前必须过两道关（`tools/report_audit.py`，零依赖）：

**关卡一 · AI 硬门禁（gate）** — 结构性防线，先于数据核验：
- **来源可核**：量化断言附近须有来源标注；无源的具体数字 = 幻觉风险，统计来源覆盖率。
- **主观词拒答**：命中 CLAUDE.md 禁用的"我认为/显然/毫无疑问/绝对会"等 → 打回（引用块中的大师语录豁免）。
- **估计须标注**：前瞻/远期数字（含 `2027E` 记法）须标「估计」，不得冒充事实。
- **交叉验证**：关键数据应有 ≥2 来源。

**关卡二 · 数据抽检（extract → verdict）** — 抽 15% 财务数据点，双源比对，1% 容差判准出/打回。

## 执行流程
```bash
# 关卡一：发布前结构性门禁（退出码 0=通过, 1=打回，可接 CI）
python3 tools/report_audit.py gate --report reports/腾讯/腾讯-research-20260408.md

# 关卡二：抽检数据点 → Claude 从可靠信源取数填 fetched_value → 判决
python3 tools/report_audit.py extract --report reports/xxx.md
python3 tools/report_audit.py verdict --results '[{"id":1,"label":"营收","reported_value":7518,"unit":"亿","fetched_value":7518,"fetched_source":"macrotrends"}]'
```
先过 gate（结构），再过 extract/verdict（数值）。gate 通过不代表内容正确——仍须数值抽检 + 人工复核。

## 原则
- **门禁是启发式非语义理解**：它降低幻觉与无据断言的概率，是防线不是保证。
- 覆盖率<60%（且量化断言≥5行）、含主观词、>3处未标注估计、无交叉验证（量化≥10行）→ 任一即打回。
- 信源优先级：美股 macrotrends+stockanalysis / 港股 aastocks / A股 eastmoney+cninfo。

## 相关
`model-registry`(引用的模型须在册) · `error-library`(错误模式) · investment-research/earnings-review 等（发布前调用本审计）
