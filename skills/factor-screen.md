# 五面因子 IS-FDR 双门筛（OOS-first）

一次把 factor_library 的因子跑一遍 OOS 回测 + 多重检验双门：$ARGUMENTS。信号与策略路线图 P2。

## 解决什么

单独跑一个因子看着"能赚"极易自欺——**没扣多重检验、没比基准、没做功效**。`factor_screen.py`（零依赖）把全部**可离线 PIT 重建**的因子一次跑完，并施加四道门，把假阳性当场拦下。**它的价值是拦截、不是选赢家**——"证伪也是成果"。

| 门 | 判据 | 拦什么 |
|---|---|---|
| ①物质性 | OOS CAGR ≥ 门槛(默认 3%) | 微不足道的"边际" |
| ②相对基准净超额 | OOS 净超额 vs SPY > 0 | **搭大盘便车的假 alpha**(本例三因子全跑输 SPY) |
| ③BH-FDR 家族校正 | p 在"本次因子家族"内 BH-FDR(α)后仍显著 | 多测几个因子必有的假阳性(分母=跑了几个因子) |
| ④功效 | `power_at`(OOS期数,效应,波动) ≥ 0.5 | **样本太薄、结论不可信**(本例功效仅 0.07–0.11) |

## PIT 边界（诚实,不静默跳过）

只筛能由**本地源无前视重建**的因子：`quality`(ROE, pit_financials.as_of)、`momentum`(12−1 价格动量, CSV as_of 截断)、`lowvol`(负波动, CSV)。**显式列为"不可离线测"**：`size`(需历史流通股本, security_master 空/ETF 无股本)、`value`/`growth`(用前瞻一致预期, 历史不可无前视重建)。

## 执行流程
```bash
python3 tools/factor_screen.py run --prices data/build_universe_prices_2y.csv --benchmark SPY --alpha 0.10
```
实测（14 标的 ETF+大盘股混合篮、25 个月末再平衡、10 个 OOS 观测）：**quality/momentum/lowvol 三面全部 🔴 拒**——① 净超额全为负(−1.16%/−1.87%/−5.27%,全跑输 SPY=无真 alpha) ② 功效 0.07–0.11 远低于 0.5(样本撑不起结论)。**没有一个因子过关**,与"样本薄→多为 null"的诚实预期一致。

## 原则与诚实边界
- **净超额才是真 alpha**：因子选出的组合"赚了 14.77%"看着漂亮,但同期持有 SPY 赚 15.93%——净超额 −1.16% = 负 alpha。没有基准对比会把 beta 误当本事。
- **样本决定能不能得结论**：10 个 OOS 观测,`power_at`≈0.08,意味着即便真有 3%/年的 edge 也几乎测不出——**拒绝≠因子无效,而是"这个样本无权下结论"**。
- **本矩阵是 ETF+债+金混合篮、非干净股票池**：factor 语义弱,本工具是**机制演示**,非可交易的因子研究。真因子研究需干净的历史成分股 + 历史股本 + 更长样本。
- bootstrap 是启发式非严格零分布；FDR 家族仅本次因子(非全历史试验分母)；覆盖率无成分分母=coverage-unknown。**非交易建议。**

## 相关
`strategy-backtest`(OOS 回测脊柱,被复用) · `signal-lab`(FDR/功效/覆盖率原语) · `factor-library`(因子集/PIT 状态) · `pit-financials`(ROE) · `docs/信号与策略路线图-20260717.md`
