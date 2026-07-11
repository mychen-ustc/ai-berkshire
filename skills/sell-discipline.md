# 卖出纪律：何时该走，按规则不按情绪

对 $ARGUMENTS 评估一只持仓是否该卖/减/持。

## 这个 skill 解决什么
研究界普遍**重买入、轻卖出**——最怕"再等等看"。`tools/sell_discipline.py`（零依赖）把"何时该走"规则化，按优先级评估五类信号，联动 `thesis-tracker`（红线）、`tools/dcf.py`（内在价值）、`tools/performance.py`（预期回报）。

## 执行流程
```bash
python3 tools/sell_discipline.py eval \
  --entry {成本} --current {现价} --fair-value {DCF内在价值} \
  --stop-loss {止损%} --expected-return {当前预期年化} --risk-free 0.04 \
  --better-opp {更优机会预期年化} [--thesis-broken]
```

## 五类卖出信号（按优先级）
1. **论点证伪**（`--thesis-broken`）→ 卖：核心假设被推翻，无论盈亏都离场（最高优先）。
2. **止损触发**：较成本跌破止损线 → 卖/复审。
3. **显著超内在价值/目标**：现价 ≥ 内在价值×1.2 → 卖；≥ 内在价值 → 减（MOAT 式"涨过公允价值就卖"）。
4. **机会成本**：预期回报 < 无风险利率 → 卖，不如持币（卡拉曼：现金是仓位）。
5. **换仓**：出现明显更优机会 → 减仓腾挪。

## 原则
- **论点证伪与止损优先于一切侥幸**——这是防止"亏损翻倍"的第一纪律。
- 卖出决策要与 `decision-journal` 联动：了结时记录结果，事后校准。
- 区分"过程对/错"与"结果对/错"，避免因运气好而强化坏卖出习惯。

## 相关
`thesis-tracker`（论点红线）· `watch`（触发巡检）· `decision-journal`（了结记录与校准）· `master-lens`（卡拉曼下行优先 / 马克斯周期镜片）
