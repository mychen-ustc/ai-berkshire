# 因子策略回测脊柱（OOS-first）

把因子变成可验证策略：$ARGUMENTS。信号与策略路线图 ⑤（产收益脊柱）。

## 解决什么

诊断：`backtest_rigorous` 只是审计器、无产收益引擎；因子→可验证策略闭环不存在。`strategy_backtest.py`（零依赖）补脊柱，**评审纪律全焊入**：

- **只用 PIT_SAFE 因子**（`factor_pit_status()`；ROE 质量走 `pit_financials.as_of`，`available_at<=d` 无前视）
- **OOS-first**：样本内 IS / 样本外 OOS **分开报告**，OOS 才算数，全样本标"有偏、勿作头条"
- **扣 TCA 净额**为唯一头条（很多样本内 alpha 扣成本后消失）
- **coverage_from_master** 诚实标覆盖率（无成分分母 → coverage-unknown，不称"无幸存者偏差"）
- 每次回测写**哈希链试验台账**（`signal_lab`，多重比较分母 + 防篡改）

## 执行流程
```bash
python3 tools/strategy_backtest.py run --prices data/build_universe_prices_2y.csv \
    --factor quality --top-frac 0.5 --cost-bps 10 --oos-frac 0.4
python3 tools/signal_lab.py verify     # 校验台账哈希链完整性
```
示例产出（ROE 质量、5 名 universe、24 次月度再平衡）：**OOS CAGR +14.77% / Sharpe 0.89**，但 **OOS bootstrap p=0.083（弱证据/不显著）**、**coverage-unknown**（无幸存者分母）——诚实、不吹。

## 原则与诚实边界
- **OOS 才算数**：全样本 Sharpe 是有偏的、永不作头条；报告同时给 IS/OOS/全样本三档。
- **净额口径**：扣换手 × cost_bps；毛收益为正的策略可能扣成本后为负。
- **最小实现**：纯多头 / 月度 / 单因子；universe 受价格矩阵限（薄）；ROE 仅美股点时库。
- **预期多为 null**：样本薄（评审：38 标的×6 年、重叠窗）；"证伪也是成果"，不为交白卷放松门禁。
- 非交易建议；`coverage-unknown` 表示无法证明无幸存者偏差，须补交易所历史成分分母。

## 相关
`factor-library`(PIT_SAFE 因子源) · `signal-lab`(OOS切分/覆盖率/哈希链台账) · `pit-financials`(ROE) · `tca`(成本) · `delisting`(当时在市池) · `docs/信号与策略路线图-20260717.md`
