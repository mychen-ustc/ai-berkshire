# 行业专用估值模型

对 $ARGUMENTS 用行业专用锚估值。P4 深度建模。

## 解决什么

通用 DCF 套所有行业会失真。`tools/industry_valuation.py`（零依赖）给强特征行业专用锚：
- **银行**：合理 P/B = (ROE−g)/(COE−g)（剩余收益）。
- **保险**：内含价值法 评估价值 ≈ EV + NBV×倍数、P/EV。
- **地产**：NAV/RNAV 折溢价。
- **SaaS**：Rule of 40（增速+FCF利润率）+ 反推可承受 EV/S。

## 执行流程
```bash
python3 tools/industry_valuation.py bank --roe 0.15 --coe 0.10 --g 0.03 --bvps 20
python3 tools/industry_valuation.py saas --growth 0.30 --fcf-margin 0.15 --ev-s 12
python3 tools/industry_valuation.py property --nav 100 --price 70
python3 tools/industry_valuation.py insurance --ev 50 --nbv 6 --price 45
```

## 与其它工具的闭环
`dcf`/`comps`(交叉验证：绝对/相对/行业三锚) · `forensic-accounting`(银行看拨备/不良、地产看减值) · `investment-research`(行业尽调)

## 原则
- 行业模型是**锚、非真值**：银行务必看资本充足/拨备/不良；地产折价未必便宜(杠杆/去化);保险 EV 假设(投资回报/贴现率)是关键。
- SaaS 的 EV/S 启发式是经验锚、非精确——结合净留存(NRR)与现金流看。
- 与 DCF/comps 三锚交叉，不单用一个模型下结论。
