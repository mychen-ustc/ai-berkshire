# 信号有效性校准（前瞻收益 vs 基线）

用数据检验信号有没有 edge：$ARGUMENTS。L3 交叉验证支柱（信号侧）。

## 解决什么

诊断指出五面研究的信号**从未被证明有效**——全仓零 forward-return/backtest 校准，"我觉得这信号有用"从未被数据验证。`signal_calibration.py`（零依赖）补这根支柱：

- 信号每次**触发日 i** → 前瞻收益 = P[i+h]/P[i]−1
- 把所有触发的前瞻收益 与 **无条件基线**（每个可算日持有 h）对比 → 均值/胜率 **edge**
- 判定：**有效**（均值 edge>0 且胜率 edge>0，同向占优）/ **无效**（无 edge）/ **存疑**（方向不一致）/ **样本不足**

## 执行流程
```bash
python3 tools/signal_calibration.py calibrate --symbol AAPL --signal rsi_oversold --horizon 20
python3 tools/signal_calibration.py calibrate --symbol 600519 --signal golden_cross --horizon 60 --freq daily
```
内置信号：`rsi_oversold`（RSI 跌破 30）、`golden_cross`（SMA50 上穿 SMA200）。RSI 用逐 bar Wilder 序列（末值与 `technicals.rsi` 一致）。

示例产出（AAPL·RSI超卖·前瞻20日·10y）：触发 21 次，信号后均值 +4.38% 胜率 67% vs 基线均值 +2.37% 胜率 65% → **edge +2.01% / +1.3%，判定「有效」**。

## 原则与诚实边界
- **描述性校准非严格显著性检验**：无 t 检验/无多重比较校正；样本少、regime 变化、前瞻窗口重叠都会失真。
- 是"信号有没有被数据支持"的**证据**，不是交易建议；免费日线前复权。
- 判定要求均值与胜率**同向占优**，避免单一指标造成的偶然。

## 相关
`technicals`(信号源) · `valuation-cross-check`(L3 支柱·估值侧) · `backtest-rigorous`(严谨回测) · `factor-library`(因子有效性)
