# 标的主数据 + 点时快照库（事实源）

登记/查询 $ARGUMENTS 的标的主数据与点时数据。P3-1 事实源持久化。

## 解决什么

给整套系统一个**单一事实源**，用 `tools/security_master.py`（零依赖，持久化到 `data/`）：
- **Security Master**：内部ID ↔ 各市场代码/交易所/币种/名称/行业/上市退市状态。解决"同一标的多处硬编码"、跨市场对齐、退市标记。
- **点时(PIT)快照库**：把每次取到的关键指标按 `as_of` 存档；查询只返回"该日期前已知"的数据——**防回测/归因的前视偏差(look-ahead)**。

## 执行流程
```bash
python3 tools/security_master.py resolve 600519            # 解析并登记
python3 tools/security_master.py set 06082.HK --status delisted --industry 国产GPU
python3 tools/security_master.py list --status active
python3 tools/security_master.py snapshot 600519           # 记今日点时快照(价/PE/PB)
python3 tools/security_master.py asof 600519 --date 2026-06-30   # 只看该日期前已知
```

## 与事实源闭环
1. 各工具解析标的 → `security_master resolve`（统一 ID/币种/交易所）→ 2. 定期 `snapshot` 积累点时数据 → 3. 回测/归因用 `asof(date)` 取数、**杜绝前视** → 4. 退市标的 `set --status delisted` 纳入，供 backtest 补幸存者偏差。

## 原则（诚实边界）
- market/exchange/currency 由 `datalayer.detect` 路由(可靠)、name 由行情取；**行业/上市日/退市状态**受免费数据访问限制，支持**手动设定**或后续接入。
- **自动退市列表本环境不稳**——故 backtest 的幸存者偏差仍需人工补退市样本(用 `set --status delisted` 登记)。
- **PIT 库只在快照积累后才对回测有意义**：它是"从今天起不再前视"的基建，历史回补需另接点时财务源。

## 相关
`datalayer`(路由/取数) · `backtest`(用退市样本消除幸存者偏差) · `ledger`(持仓事实源) · `attribution`(点时归因)
