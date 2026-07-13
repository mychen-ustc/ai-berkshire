# 持股与内部人跟踪：谁真的在买卖

对 $ARGUMENTS 拉取龙虎榜与股东户数，看一手披露的资金/筹码变动。

## 这个 skill 解决什么

`money-flow` 的主力资金流是逐笔单量的**估算**；`/holdings-tracker` 用 `tools/holdings_tracker.py`（零依赖）看**一手披露**——补上"真实席位/筹码"的诚实缺口：

- **龙虎榜**（东财）：机构/游资席位异动、成交额占比、当日涨跌——"聪明钱异动"的一手记录。
- **股东户数**（东财）：户数环比变化——下降=筹码集中（常伴主力吸筹）、上升=筹码分散。

## 执行流程
```bash
python3 tools/holdings_tracker.py track 300750       # 龙虎榜 + 户数 + 综合姿态
python3 tools/holdings_tracker.py dragon 300750 --limit 8
python3 tools/holdings_tracker.py holders 300750
```

## 与其它工具的闭环
1. `/money-flow` 给主力资金流（估算）→ 2. **`/holdings-tracker` 用龙虎榜/户数做一手验证** → 3. 若"主力吸筹估算 + 户数下降 + 机构龙虎榜净买"三者同向，资金面信号更可信 → 4. 结合 `technical-analysis` 的趋势与 `sentiment` 的情绪交叉印证。

## 原则
- **龙虎榜是"异动才上榜"的样本**、非全量资金：大盘蓝筹长期不上榜是常态（不代表没资金）；游资上榜 ≠ 长期资金；只反映当日。
- **股东户数季度披露、滞后**：集中度是概率性信号、非因果——户数降常伴吸筹，但也可能是缩量。
- **仅 A 股**（东财）；美股机构持仓需 SEC EDGAR 13F、内部人交易需 Form 4（本版本未接入，见路线图 P4-8）。
- 一手披露**验证**资金面论点，**永不替代基本面**。

## 相关
`money-flow`(主力资金流估算) · `technical-analysis`(趋势印证) · `sentiment`(情绪印证) · `forensic-accounting`(减持是否伴随质量恶化)
