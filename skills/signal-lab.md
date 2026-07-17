# 信号研究防过拟合工具箱

信号/策略研究的防过拟合护栏：$ARGUMENTS。信号与策略路线图 P0/P1 一等公民。

## 解决什么

诊断实证：全库 walk-forward/OOS/holdout/bootstrap/deflated-Sharpe/FDR 命中 **= 0**——过拟合"完全无防守"。`signal_lab.py`（零依赖）把"防过拟合"从事后诚实声明升级为**可复用、可测的原语**，**必须先于任何信号规模化测试落地**（护栏先行是路线图的核心纪律）。

| 原语 | 作用 |
|---|---|
| `effective_independent_obs` | 功效体检：重叠前瞻窗把 N 次触发压成几个独立观测（诚实预期锚） |
| `holdout_split` / `assert_no_holdout_leak` | 密封时间轴样本外，发现阶段永不触碰（**唯二无法回填之一**） |
| `record_trial` / `trial_count` | append-only 试验台账 = 多重比较的分母（**唯二无法回填之二**） |
| `walk_forward_splits` | 滚动训练/测试 + purge（防重叠标签泄漏）+ embargo |
| `block_bootstrap_pvalue` | 分块自助显著性，尊重重叠窗自相关（替换朴素 edge>0） |
| `benjamini_hochberg` | BH-FDR 多重检验校正（测 N 个信号必有假阳性） |
| `deflated_sharpe_pvalue` | 按试验次数 Šidák 惩罚 Sharpe（防"试到显著为止"） |
| `coverage_verdict` | 反转覆盖率门禁：修正数据缺失时拒绝声称"无偏差"，强制标 coverage-absent |

## 执行流程
```bash
python3 tools/signal_lab.py power --triggers 21 --horizon 20   # 功效:21触发/前瞻20 → 有效独立观测
python3 tools/signal_lab.py demo                               # 各原语自检
```
**已接入 `signal_calibration`**：每次校准（`--no-record` 可关）自动 ① 算有效独立观测 ② 跑 block-bootstrap 显著性 ③ 写试验台账。实测 AAPL RSI 超卖：朴素判定"有效"(+2.01%)，但 signal_lab 揭示**有效观测仅 15、自助 p=0.077 不显著**——把假阳性当场降级为"证据弱"。

## 原则与诚实边界
- **护栏先行**：holdout + 试验台账无法事后回填（分母不从第 1 次记就重建不出、holdout 被挖过就洗不干净），必须第一步立起。
- **样本薄时结论多为 null**：38 标的×6 年、重叠窗下 21 触发≈几个独立观测——**"证伪也是成果"，不为交白卷放松门禁**。
- zero-dep 下显著性数学手写：block-bootstrap（非 iid）、`math.erf` 算正态 CDF；deflated 用 Šidák 近似（非完整 DSR，无 skew/kurt）。
- 覆盖率门禁只**诚实标注**、不真去偏（现有退市库仅 4 条）。

## 相关
`signal-calibration`(已接入,信号 edge 校准) · `backtest-rigorous`(三偏差引擎,待接 walk-forward) · `factor-library`(因子信号) · `quant-metrics`(Sharpe) · `docs/信号与策略路线图-20260717.md`
