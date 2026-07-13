# 宏观 regime：美林时钟定位组合旋钮

给一个描述性的宏观状态盘：增长 × 通胀定位投资时钟象限 + 流动性 + 利率。

## 定位（最重要）

`/macro-regime` 用 `tools/macro_regime.py`（零依赖）给宏观**背景板**，用途是**明确宏观只影响哪些决策**（现金区间、行业暴露、久期），**绝不用来在自下而上研究里随意改个股估值假设**——这是价值投资者用宏观的正确姿势（芒格/巴菲特不预测宏观，但会据 regime 调整整体谨慎度）。

## 执行流程
```bash
python3 tools/macro_regime.py now
python3 tools/macro_regime.py now --json
```
输出：
- **美林投资时钟象限**：增长(PMI) × 通胀(CPI) → 复苏🟢/过热🟠/滞胀🔴/衰退🔵，及各象限历史倾向的资产。
- **读数**：PMI（制造业/非制造业，荣枯线 50）、CPI（同比升温/回落、环比）、M2/M1 同比与剪刀差（<0 资金活化不足）、美债 10Y（全球无风险利率锚）。

数据：中国 PMI/CPI/M2 来自东财宏观；10Y 来自 Yahoo ^TNX。

## 与其它工具的闭环
1. `/macro-regime` 定当前象限 → 2. 象限只调**组合层旋钮**：如滞胀→抬现金/降久期/避高估值、复苏→顺周期成长可积极 → 3. 用 `portfolio-optimizer`/`sell-discipline` 落到仓位 → 4. 个股仍走自下而上（`investment-research`/`dcf`），**不因宏观改个股假设**。

## 原则
- **regime 是事后描述、非预测**：单月 PMI/CPI 有噪声、方向可能反复；象限"利好资产"是历史统计倾向、**不是择时信号**。
- **只调组合旋钮，不改个股估值**：这是与"宏观投机"的根本区别。
- 中国 10Y 未直接接入（用美债 10Y 作全球利率锚，诚实缺口）；美林时钟是框架、不是水晶球。

## 相关
`portfolio-review`/`portfolio-optimizer`(落到仓位) · `sector-rotation`(行业暴露) · `sell-discipline`(久期/现金) · `master-lens`(达利欧·经济机器)
