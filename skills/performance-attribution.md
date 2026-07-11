# 业绩归因：收益到底从哪来

对 $ARGUMENTS 做业绩归因——把组合收益拆解到每只持仓，并相对基准分出"选赛道"还是"选个股"的功劳。

## 这个 skill 解决什么

多数人只看"赚了多少"，不看"**为什么赚/赔**"。机构靠归因区分**运气（踩对赛道）vs 能力（选对个股）**，并与决策日志联动做自我进化。

工具：`tools/attribution.py`、`tools/performance.py`、`tools/decision_journal.py`（均零依赖）。

## 执行流程

### 1. 贡献分解（每只持仓贡献了多少收益）
```bash
python3 tools/attribution.py contribution --from-datalayer "{代码1}={权重},{代码2}={权重}" --period {1y|5y}
```
经数据层取前复权区间收益，输出每只的 权重×收益=贡献 及占比。**找出真正的收益来源与拖累项。**

### 2. Brinson 归因（相对基准的超额从哪来）
准备 CSV（`group,wp,rp,wb,rb`：分组、组合权重/收益、基准权重/收益），然后：
```bash
python3 tools/attribution.py brinson --file {groups.csv}
```
超额 = **配置效应**（选对行业/市场）+ **选股效应**（行业内选对股）+ 交互。
- 配置正、选股负 → 你会踩赛道但选股拖后腿
- 配置负、选股正 → 你选股强但赛道押错

### 3. 收益率口径（TWR vs MWR）
```bash
python3 tools/performance.py twr --nav {nav.csv}         # 时间加权(衡量能力，对比基准用它)
python3 tools/performance.py mwr --ledger {账本} --currency {币} --terminal-value {期末市值}
python3 tools/performance.py value --ledger {账本} --fx "USD=7.8,HKD=1"   # 期末市值可由此得
```

### 4. 决策校准联动
```bash
python3 tools/decision_journal.py calibrate
```
把"归因结果"与"当初决策的概率估计"对照：**赚钱是因为判断对了，还是运气？** 这是复盘的灵魂。

## 输出要求
1. 明确区分：收益来自**配置**还是**选股**？是**能力**还是**运气**？
2. 归因要诚实——**最大拖累项**和最大贡献项同样重要（错题）。
3. 结合决策校准：结果好但当初理由错，仍要记为"过程错、结果对"（避免强化坏习惯）。

## 相关
- `decision-journal`：决策记录与校准（归因的对照）
- `portfolio-review`：组合层健康度与再平衡
- `tools/ledger.py` / `tools/datalayer.py`：事实源与行情
