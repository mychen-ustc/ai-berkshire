# 因子策略回测脊柱（OOS-first）

把因子变成可验证策略：$ARGUMENTS。信号与策略路线图 ⑤（产收益脊柱）。

## 解决什么

诊断：`backtest_rigorous` 只是审计器、无产收益引擎；因子→可验证策略闭环不存在。`strategy_backtest.py`（零依赖）补脊柱，**评审纪律全焊入**：

- **只用 PIT_SAFE 因子**（`factor_pit_status()`；ROE 质量走 `pit_financials.as_of`，`available_at<=d` 无前视）
- **OOS-first**：样本内 IS / 样本外 OOS **分开报告**，OOS 才算数，全样本标"有偏、勿作头条"
- **扣 TCA 净额**为唯一头条（很多样本内 alpha 扣成本后消失）
- **coverage_from_master** 诚实标覆盖率（无成分分母 → coverage-unknown，不称"无幸存者偏差"）
- 每次回测写**哈希链试验台账**（`signal_lab`，多重比较分母 + 防篡改）

## 执行流程（预注册 → 回测 → 自动晋级判定，闭环）
```bash
# ① 跑之前先冻结晋级阈值(哈希链,防事后改参);param_hash 与 run 一致
python3 tools/strategy_backtest.py prereg --factor quality --universe px-2y \
    --min-material-edge 0.05 --max-p 0.05 --min-net-excess 0.0
# ② 同参回测 → 自动匹配预注册,按**预注册**阈值判 promote(未注册→仅探索性、拒晋级)
python3 tools/strategy_backtest.py run --prices data/build_universe_prices_2y.csv \
    --factor quality --universe px-2y --top-frac 0.5 --cost-bps 10 --oos-frac 0.4 --benchmark SPY
python3 tools/signal_lab.py verify     # 校验台账/预注册册哈希链完整性
```
示例产出（ROE 质量、5 名 universe、24 次月度再平衡）：**OOS CAGR +14.77% / Sharpe 0.89**，但 **OOS bootstrap p=0.083（弱证据/不显著）**、**相对 SPY 净超额 −1.16%（实则跑输基准=负 alpha）**、**coverage-unknown**（无幸存者分母）——晋级门禁在"要求净超额≥0"时正确🔴拒绝。诚实、不吹。

## 原则与诚实边界
- **OOS 才算数**：全样本 Sharpe 是有偏的、永不作头条；报告同时给 IS/OOS/全样本三档。
- **净额口径**：扣换手 × cost_bps；毛收益为正的策略可能扣成本后为负。
- **最小实现**：纯多头 / 月度 / 单因子；universe 受价格矩阵限（薄）；ROE 仅美股点时库。
- **预期多为 null**：样本薄（评审：38 标的×6 年、重叠窗）；"证伪也是成果"，不为交白卷放松门禁。
- 非交易建议；`coverage-unknown` 表示无法证明无幸存者偏差，须补交易所历史成分分母。
- **晋级须先预注册**：阈值来自 `prereg`（哈希链冻结），非事后所定；未预注册的策略只能是探索性、不得晋级。**相对基准净超额**才是真 alpha（本例 −1.16% 揭示"看着赚钱、实则跑输 SPY"）。

## 相关
`factor-library`(PIT_SAFE 因子源) · `signal-lab`(OOS切分/覆盖率/哈希链台账) · `pit-financials`(ROE) · `tca`(成本) · `delisting`(当时在市池) · `docs/信号与策略路线图-20260717.md`
