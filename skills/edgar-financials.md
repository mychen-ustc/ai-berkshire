# EDGAR 财务摄取（点时）

从 SEC EDGAR 拉真实财报入点时库：$ARGUMENTS。喂 factor-library 的质量维度。

## 解决什么

点时财务库(`pit_financials`)是**引擎**，但要有真数据才有用。`edgar_financials.py`(零依赖)从 **SEC EDGAR companyconcept API**(官方、免费、无 key)拉**真实**财务数据(净利/股东权益/营收)及其 **filing date(披露日)**，按披露日录入点时库——filing date 天然是 available_at，故录入即**无前视**、且**不编数据**。

直接解锁 `factor-library` 的**质量(ROE)维度**：ROE = 净利/股东权益，此前因缺点时基本面无法计算。

## 执行流程
```bash
python3 tools/edgar_financials.py ingest --symbol AAPL          # 拉单只→点时库
python3 tools/edgar_financials.py ingest-core                   # 核心美股持仓批量(AAPL/GOOGL/AXP/KO/COST/NDAQ)
# 摄取后，质量维度即可用：
python3 tools/factor_library.py analyze --symbols "GOOGL,AXP,COST,NDAQ,KO,AAPL" --weights "..."
```
- 每期录入 net_income / stockholders_equity / revenue / roe(算)，available_at = 首次披露日。
- 实测 ROE(真实)：AAPL 152%(回购型)、KO 41%、GOOGL/AXP 32%、COST 28%、NDAQ 15%。

## 原则与诚实边界
- **只录真实 EDGAR 数据**：不用估计值填充；filing date = 首次披露(同一期在后续财报重复出现时取最早)。
- **仅美股 10-K 申报人**：BRK.B(控股公司结构)/兆易(A股)/ETF 不在覆盖内。
- 概念标签因公司而异(营收有多个 tag)，工具逐个尝试；仍可能有个别公司取不全，需 --cik 指定或人工补。
- 这是"给点时库喂真数据"的一环，与 `data-foundation`(引擎)配套。

## 相关
`pit-financials`/`data-foundation`(点时引擎) · `factor-library`(质量维度消费者) · `edgar-13f`(同源EDGAR,机构持仓) · `backtest-rigorous`(点时信号检验)
