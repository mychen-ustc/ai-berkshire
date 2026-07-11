# data/portfolio —— 交易账本（事实源）

本目录是 P0-2「统一交易账本」的落地：整个投资系统的**单一事实源**。风险、业绩、归因、告警都应从这里重建的持仓出发，而不是各自维护一份持仓。

## 隐私原则（重要）

遵循实盘记录的既有做法——**公开决策，不公开规模**：

- **真实账本只存本地，不进仓库**：`transactions.csv`、`prices.csv`、`*.local.*` 已在 `.gitignore` 中。
- 仓库内只提供**合成示例** `transactions.example.csv` / `prices.example.csv`（数据均为虚构，用于演示和测试工具）。
- 要用真实数据：把自己的账本存为 `data/portfolio/transactions.csv`（不会被提交），命令里 `--ledger` 指向它即可。

## 账本 CSV schema

表头必须为：`date,action,symbol,market,currency,quantity,price,fee,amount,note`

| action | 语义 |
|---|---|
| DEPOSIT / WITHDRAW | 现金流入/流出（`currency` + `amount`） |
| BUY | 买入：`cost = quantity*price + fee`，扣对应币种现金 |
| SELL | 卖出：`proceeds = quantity*price - fee`，加现金，累计已实现盈亏 |
| DIV | 股息：加现金，并计入该 `symbol` 的累计分红 |
| FEE | 费用：扣现金（`amount` 或 `fee`） |
| SPLIT | 拆股：`price` 列填拆股比（如 2 = 1拆2），股数×比、均价÷比 |
| FX | 换汇：`symbol`=来源币种, `quantity`=来源金额, `currency`=目标币种, `amount`=目标金额 |

## 用法

```bash
# 重建持仓/现金/成本（无需价格）
python3 tools/ledger.py positions --ledger data/portfolio/transactions.example.csv

# 任意历史日重放
python3 tools/ledger.py positions --ledger data/portfolio/transactions.example.csv --as-of 2026-02-01

# 给价格 + 汇率 → 市值/未实现/权重，并按 config/investment-policy.json 查集中度是否越限
python3 tools/ledger.py positions \
  --ledger data/portfolio/transactions.example.csv \
  --prices data/portfolio/prices.example.csv \
  --base HKD --fx "USD=7.80"
```

## 已知限制（后续里程碑补）

- 成本用**移动平均**（非 FIFO 分批）——报税级别的税表批次留待 P1。
- 市值/NAV 的跨币种换算依赖手动 `--fx`；自动汇率、point-in-time 价格属 P0-3 数据层。
- 尚无自动回归测试（golden case）——属 P0-4 测试基建。
