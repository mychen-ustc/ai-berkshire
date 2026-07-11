# 持仓监控告警：把手动红线变成主动巡检

对 $ARGUMENTS 巡检持仓、评估触发器、展示催化剂日历。

## 这个 skill 解决什么
`thesis-tracker` 的红线要手动重跑。`/watch` 用 `tools/watch.py`（零依赖）**主动巡检**：从账本取成本、数据层取实时价，按每标的触发器（止损/止盈/价位/单日异动）产出告警；配合 `/loop` 或 cron 可定时运行。

## 执行流程
### 1. 巡检持仓
```bash
python3 tools/watch.py check --ledger data/portfolio/transactions.csv --config config/watch.json
```
配置格式（`config/watch.json`，见 `config/watch.example.json`）：
```json
{"_default": {"stop_loss_pct": 25, "day_move_pct": 8},
 "0700.HK": {"take_profit_pct": 60, "price_below": 400}}
```
输出每只：🟢正常 / 🟡关注 / 🔴告警 + 触发原因。

### 2. 催化剂/财报日历
```bash
python3 tools/watch.py calendar --file data/portfolio/catalysts.csv --within 30
```

### 3. 定时运行（可选）
用 `/loop`（会话内周期）或 `/schedule`（cron 云端）包裹第 1 步，实现每日盘后自动巡检。

## 触发后动作（纪律）
- 🔴 止损/跌破 → 立即用 `/sell-discipline` 评估是否离场（论点是否证伪）。
- 🟡 单日异动 → 用 `/news-pulse` 归因"发生了什么"。
- 🟡 止盈 → 用 `tools/dcf.py` 重估内在价值，判断减仓。

## 相关
`thesis-tracker`（红线定义）· `sell-discipline`（触发后决策）· `news-pulse`（异动归因）· `tools/ledger.py`/`datalayer.py`（事实源）
