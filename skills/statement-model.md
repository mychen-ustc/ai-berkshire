# 三表联动财务预测模型

对 $ARGUMENTS 做 driver-based 三表投影 → FCF。P4 深度建模。

## 解决什么

DCF 常只吃"假设"、无前端建模，假设难自洽。`tools/statement_model.py`（零依赖）由收入驱动 → 利润表 → 自由现金流(勾稽营运资本/资本开支/折旧)，让假设**内部自洽**(高增长必然消耗 WC、需 capex 支撑)，输出 FCF 喂 `dcf.py`。

## 执行流程
```bash
python3 tools/statement_model.py project --rev 1000 --years 5 \
  --growth 0.15 --gross 0.60 --opex 0.35 --tax 0.25 --dep 0.04 --capex 0.06 --wc 0.10
```
输出：逐年 营收/EBIT/NOPAT/折旧/资本开支/ΔWC/FCF + FCF CAGR。

## 与其它工具的闭环
`dcf`(接 FCF 做贴现) · `scenario`(牛/基/熊 各一组驱动→各情景估值) · `consensus`/`us-consensus`(增速假设对齐市场) · `comps`(交叉验证)

## 原则
- **driver 模型放大假设敏感性**：毛利/增速/capex 任一偏差都显著改 FCF——做三情景、勿单点。
- 是"让假设自洽"的工具，不是预测机；增长与再投资必须匹配(高增长不可能零 capex)。
