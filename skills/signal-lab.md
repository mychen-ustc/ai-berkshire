# 信号研究防过拟合工具箱

信号/策略研究的防过拟合护栏：$ARGUMENTS。信号与策略路线图 P0/P1 一等公民。

## 解决什么

诊断实证：全库 walk-forward/OOS/holdout/bootstrap/deflated-Sharpe/FDR 命中 **= 0**——过拟合"完全无防守"。`signal_lab.py`（零依赖）把"防过拟合"从事后诚实声明升级为**可复用、可测的原语**，**必须先于任何信号规模化测试落地**（护栏先行是路线图的核心纪律）。

| 原语 | 作用 |
|---|---|
| `effective_independent_obs` | 功效体检：重叠前瞻窗把 N 次触发压成几个独立观测（诚实预期锚） |
| `holdout_split` / `assert_no_holdout_leak` | 密封时间轴样本外，发现阶段永不触碰（**唯二无法回填之一**） |
| `record_trial` / `verify_ledger` | 试验台账 = 多重比较分母；**哈希链(seq+prev_hash+chain_hash)防篡改可审计**，`verify` 检出删改（`signal_lab.py verify`） |
| `load_expected_delisted` / `coverage_from_master` | 从交易所历史成分主表载**真覆盖率分母**（数据待摄取，缺则 coverage-unknown） |
| `walk_forward_splits` | 滚动训练/测试 + purge（防重叠标签泄漏）+ embargo |
| `block_bootstrap_pvalue` | 圆形分块自助**启发式**证据（尊重重叠窗自相关）。⚠️ 非严格经验零分布 p（重采样已观测收益 vs 固定基线，未处理基线误差/选择效应），仅证据强弱；严格版需时间块置换 + scipy oracle |
| `benjamini_hochberg` | BH-FDR 多重检验（控 **FDR**，与 Šidák 控 FWER 不同） |
| `sidak_adjusted_sharpe_pvalue` | 正态近似 Sharpe p + Šidák 试验惩罚（控 **FWER**）。⚠️ **非完整 DSR**（未处理 skew/kurt）；旧名 `deflated_sharpe_pvalue` 留兼容别名 |
| `coverage_verdict` | 覆盖率门禁（**需分母**：交易所历史证券主表/指数成分）。⚠️ **无分母→coverage-unknown（不通过）**；加一个退市样本≠覆盖完整 |
| `param_hash` / `trial_uid` | 试验指纹与唯一 ID（台账去重/审计） |

## 执行流程
```bash
python3 tools/signal_lab.py power --triggers 21 --horizon 20   # 功效:21触发/前瞻20 → 有效独立观测
python3 tools/signal_lab.py demo                               # 各原语自检
```
**已接入 `signal_calibration`**：每次校准（`--no-record` 可关）自动 ① 算有效独立观测 ② 跑 block-bootstrap 启发式证据 ③ 写试验台账（trial_id/param_hash/记失败）。支持 `--as-of DATE`（真数据截断，PIT 验证；`--split holdout/validation` 须配 `--as-of`）。实测 AAPL RSI 超卖：朴素判定"有效"(+2.01%)，但 signal_lab 揭示**有效观测仅 15、自助 p=0.077 弱证据**——把假阳性当场降级。

## ⚠️ 诚实边界（经评审纠正，避免"防过拟合工具"自身失真）
- **是原语、尚非不可绕过的生产门禁**：`--no-record` 可绕过、台账可手删、无哈希链/强制入口——"条数==校准次数"仅单机经 CLI 无删改时成立。
- **bootstrap/Sharpe 是近似**：bootstrap 非严格零分布；Šidák-Sharpe 非完整 DSR。严格显著性需 scipy/statsmodels oracle 校 size/power。
- **覆盖率门禁需真分母**（证券主表/指数成分），否则只能 coverage-unknown。
- **历史 holdout 已被观察=污染**：`--as-of` 是 validation 截断；真 final holdout 须用未来/未观察数据。
- **factor PIT**：回测只用 `factor_pit_status()` 的 PIT_SAFE 子集{quality,momentum,lowvol,size}；value/growth 前瞻不可历史重建、已排除。

## 原则与诚实边界
- **护栏先行**：holdout + 试验台账无法事后回填（分母不从第 1 次记就重建不出、holdout 被挖过就洗不干净），必须第一步立起。
- **样本薄时结论多为 null**：38 标的×6 年、重叠窗下 21 触发≈几个独立观测——**"证伪也是成果"，不为交白卷放松门禁**。
- zero-dep 下显著性数学手写：block-bootstrap（非 iid）、`math.erf` 算正态 CDF；deflated 用 Šidák 近似（非完整 DSR，无 skew/kurt）。
- 覆盖率门禁只**诚实标注**、不真去偏（现有退市库仅 4 条）。

## 相关
`signal-calibration`(已接入,信号 edge 校准) · `backtest-rigorous`(三偏差引擎,待接 walk-forward) · `factor-library`(因子信号) · `quant-metrics`(Sharpe) · `docs/信号与策略路线图-20260717.md`
