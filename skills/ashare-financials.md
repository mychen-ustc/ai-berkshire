# A股财务摄取（点时）

从东方财富业绩报表拉真实 A 股年报入点时库：$ARGUMENTS。补齐 `pit_financials` 的 A 股半边、喂 factor-library 质量维度。

## 解决什么

点时财务库此前**仅美股**(EDGAR)，A 股质量(ROE)因子缺数据。`ashare_financials.py`(零依赖)从**东财业绩报表 RPT_LICO_FN_CPD**(官方、免费、无 key)拉**真实**年报财务(归母净利/营收/加权ROE/EPS)及其**公告日(NOTICE_DATE)**，按公告日录入点时库——公告日天然是 available_at，故录入即**无前视**、**不编数据**。

与 `edgar-financials`(美股)对称，共同让 `factor-library` 的**质量(ROE)维度对 A 股也生效**、A 股历史基本面可用于 comps 分位。

## 执行流程
```bash
python3 tools/ashare_financials.py ingest --symbol 002185          # 拉华天科技→点时库
python3 tools/ashare_financials.py ingest-universe                 # 真实工作 universe 的 A 股批量(13只)
# 摄取后，质量因子即对 A 股可算：
python3 -c "import sys;sys.path.insert(0,'tools');import factor_library as fl;print(fl._quality_factor('002185.SZ'))"
```
- 每期录 net_income / revenue / roe / eps，`fiscal_period=FY{年}`，`available_at=公告日`。
- **ROE 口径统一**：东财 `WEIGHTAVG_ROE` 是百分数(4.14=4.14%)，工具 **÷100 转比率**，与 EDGAR roe(净利/权益,比率)一致，供质量因子横截面 z-score。
- shares(总股本)取当前快照(总市值/价)，喂规模因子。
- 实测无前视：查询 2026-03-01(FY2025 公告 03-31 前)只见 FY2024；03-31 后才见 FY2025。

## 原则与诚实边界
- **只录真实东财公告数据**，不编；同年多条(年报+修订)取**最早公告**(PIT 关键)。
- **成长因子仍限美股**：A 股无免费前瞻一致预期源，若用 A 股历史 EPS CAGR 会与美股的前瞻口径**混用、污染同一横截面因子**——故**不做**(诚实优先于覆盖)。
- shares 是当前快照非期末口径；仅 A 股(美股用 `edgar-financials`)。

## 相关
`edgar-financials`(美股对称件) · `data-foundation`(点时库引擎) · `factor-library`(质量/规模维度) · `ingest-universe`(数据底座总摄取)
