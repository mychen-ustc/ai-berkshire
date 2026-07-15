# 三级机会流水线

从线索到持仓的三级漏斗 + 降级级联：$ARGUMENTS。

## 解决什么

把机会管理做成有纪律的三级漏斗，避免"雷达线索一闪而过没人跟进"：

| 层 | 文件 | 含义 |
|---|---|---|
| **T1 候选观察名单** | `data/candidate_pool.jsonl`(新) | 原始线索(雷达/选股器/手工)，低承诺、无需论点 |
| **T2 观察名单** | `watchlist.pipeline.json` | 已承诺研究，有论点/红线/复审日 |
| **T3 持仓组合** | 账本 `transactions.csv` | 实际持有 |

**流转**：T1 →(承诺研究)→ T2 →(买入)→ T3；**降级级联**：T3 剔除→回 T2；T2 剔除→回 T1(用户指定规则)。

## 执行流程
```bash
python3 tools/pipeline.py capture-radar          # 雷达线索(A股龙虎榜 + 美股13F新建仓)自动落入 T1
python3 tools/pipeline.py capture --symbol NVDA --market US --source 手工 --reason "AI算力"
python3 tools/pipeline.py promote --symbol 002463  # T1→T2(晋级观察名单)
python3 tools/pipeline.py demote  --symbol COST    # T3→T2 或 T2→T1(级联降级)
python3 tools/pipeline.py status                   # 三层总览 + 一致性检查
```
复盘(`review.py --weekly/--quarterly`)第九节自动回顾三层清单,并把雷达线索落入 T1。

## 多市场覆盖(补齐美股/港股缺口)
- **A股**：雷达龙虎榜机构买入 + 涨停池(东财)。
- **美股**：`us_leads` 用超级投资者(伯克希尔/Pershing/Scion/Baupost/Appaloosa)最新 13F **新建仓**(SEC EDGAR)——A股龙虎榜"聪明钱"的对等物。
- **港股**：免费的机构买入/异动数据源受限，暂未接(诚实标注)。

## 原则与诚实边界
- **降级不删除线索**：T2→T1 保留原因,避免重复研究已否决的标的。
- 一致性检查:持仓(T3)应在 watchlist 标 holding;不符会提示。
- `demote` 只更新流水线**状态**;实际买卖仍须 `rebalance` 下单 + 人工确认。
- 13F 季度滞后、用 issuer 名(非ticker,研究时定位);雷达线索非买入信号,须基本面研究。

## 相关
`radar`(A股线索源) · `edgar-13f`(美股线索源) · `watchlist`(T2状态机) · `ledger`(T3事实源) · `review`(第九节回顾)
