# 定期复盘：投资组合与 watchlist 的心跳

对 $ARGUMENTS（默认当前账本）跑一轮定期复盘。P3 运营节奏。

## 解决什么

把"研究—持有—复盘"从一次性动作变成**固定节奏**。`tools/review.py`（零依赖）一键：刷新每只持仓五面信号 → **红线/异动告警** → 汇总 watchlist 到期复审 + 临近催化剂 → 产出**行动清单**。纯 Python、可挂 cron 定期跑（无需 LLM）。

## 执行流程
```bash
python3 tools/review.py --from-ledger data/portfolio/transactions.csv --weekly [--html]
python3 tools/review.py --daily        # 盘前轻量：告警 + 今日到期 + ≤7天催化剂
python3 tools/review.py --quarterly     # 季度：+ 深度扫描/归因/IPS 复审提醒
bash scripts/install-review-cron.sh     # 装 cron：每周一 + 每季首日自动跑
```

输出（行动清单置顶）：
- **🎯 行动清单**：到期复审 / 临近催化剂 / 触发红线的持仓——一眼看该做什么。
- **组合层**：有效独立因子 + PC1 + 宏观 regime + 三市场情绪。
- **持仓信号 + 红线检查**：每只五面告警(🔴技术转弱/主力派发/盈利下修 · 🟡极度贪婪 · 🟢极度恐惧)，并对照 watchlist 里存的红线文本。
- **到期复审 / 临近催化剂**。

## 与运营节奏的闭环
1. `watchlist` 录入持仓(论点/红线/复审日) → 2. **`/review` 定期跑**(cron 每周) → 3. 行动清单驱动:红线触发→深研/减仓、复审到期→更新论点、催化剂临近→财报精读 → 4. 决策写回 `watchlist set/catalyst` 与 `decision-journal`。

## 原则
- **红线是提示、须人工判断**：review 只做机械信号刷新(技术/资金/情绪/预期)，是否行动由人定。
- **复盘非预测**：信号聚合帮你不漏事、按节奏走;五面皆叠加层、不替代基本面。
- **含真实持仓**：报告存 reports/private/reviews/(gitignore)、不入库。

## 相关
`portfolio-scan`(复用其采集) · `watchlist-pipeline`(到期/红线来源) · `catalysts`(催化剂) · `decision-journal`(决策留痕) · `sell-discipline`(红线触发后的卖出纪律)
