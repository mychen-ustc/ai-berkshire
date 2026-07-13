# 市场机会雷达：持仓之外的新线索

扫描 $ARGUMENTS（默认全市场）挖掘持仓/watchlist 之外值得研究的新标的与动向。P2 机会发现。

## 解决什么

回答"除了我的持仓和 watchlist，还有什么值得关注、是否有新标的该纳入观察"。`tools/radar.py`（零依赖）扫描全市场动向、自动去重你已持有/已观察的标的，只呈现**新线索**：
- **龙虎榜机构买入**（"聪明钱"一手席位）——最强线索。
- **涨停/连板池**（题材/情绪异动 + 所属板块）——较弱线索（动量，须警惕）。
- **热门板块**（涨停家数聚合）——资金/情绪关注方向。
- **政策/宏观要闻**（新浪7×24，政策关键词标记）。

## 执行流程
```bash
python3 tools/radar.py scan --exclude "603986,600519,..."   # 全市场雷达(去重持仓/watchlist)
python3 tools/radar.py candidates --exclude "..."           # 只看新标的候选线索
python3 tools/radar.py sectors                              # 热门板块
```
（已集成进 `/review` 的第六节「市场机会雷达」，周/季复盘自动去重当前持仓+watchlist 后呈现。）

## ⚠️ 价值投资定位（最重要）
- **雷达是"值得研究的线索池"、不是买入信号。** 龙虎榜/涨停是资金异动；**直接追涨是投机、与本体系相悖**。
- 任何线索须先过 `/investment-research` 八模块基本面 + `dcf`/`comps` 估值 + `forensic` 验伤，**通过后才用 `/watchlist add` 纳入观察**（状态从"发现/初筛"起步），而非直接买入。
- 龙虎榜"机构买入"含游资误标可能；"成功率"是次日概率、非质量。仅 A 股（东财数据）。

## 与机会发现闭环
1. `/radar scan` 出线索 → 2. 感兴趣者 `/investment-research` 深研 + `forensic` 验伤 → 3. 通过则 `/watchlist add <code> --state screening` 纳入观察流水线 → 4. `/review` 后续定期跟踪。

## 相关
`review`(集成雷达) · `investment-research`(线索→深研) · `watchlist-pipeline`(纳入观察) · `sector-rotation`(板块) · `news-engine`(政策要闻) · `stock_screener`(量化初筛)
