# 每日市场全景盘点

对上一交易日**整个市场**做全面综述（市场级，区别于组合级 `/review`）。P3 运营节奏。

## 解决什么

`/review` 看"我的组合/watchlist 该怎么办"；`/market-review` 看"**整个市场**昨天发生了什么、有什么该关注"——不局限于持仓。`tools/market_review.py`（零依赖、纯 Python、可挂 cron）一键聚合：

- **① 大盘概览**：A股(上证/深证/创业板/沪深300) · 港股(恒生) · 美股(标普/纳指) 涨跌。
- **② 广度与情绪**：A股涨跌停家数 · 三市场恐惧贪婪 + VIX。
- **③ 资金与异动**：龙虎榜机构买入 · 高连板题材。
- **④ 热门板块**：涨停家数聚合。
- **⑤ 宏观与政策要闻**：美林 regime + 新浪7×24 政策头条 + Finnhub 美股要闻。
- **⑥ 市场综述**：普涨/普跌/分化 + 广度 + 情绪 + 主线 + 关注点。

## 执行流程
```bash
python3 tools/market_review.py               # 文本
python3 tools/market_review.py --md --html    # 导出到 reports/private/market/
bash scripts/install-review-cron.sh          # 已含每日(工作日 07:30)市场盘点 cron
```

## 与运营节奏闭环
1. **每日**（工作日盘前）`/market-review` 看全市场动向、异动、政策 → 2. 若有值得研究的新标的/板块，`/radar` 或 `/investment-research` 深挖 → 3. **每周** `/review` 回到组合层做持仓决策。

## 原则
- **市场综述非预测**：普涨/普跌/情绪/主线是对昨日的客观描述，不预测今日。
- 龙虎榜/涨停/词典情感是**粗筛线索**（含游资误标、题材投机），须人工研判；追涨与本体系相悖。
- 板块用"涨停家数聚合"作热度代理（clist 板块行情受限时的稳健替代）。仅覆盖免费源。

## 相关
`review`(组合级复盘) · `radar`(新标的线索) · `sentiment`/`macro-regime`/`news-engine`(复用) · `sector-rotation`(板块深研)
