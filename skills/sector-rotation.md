# 板块轮动：动量与相对强弱

对 $ARGUMENTS 做板块动量排名，判断顺周期↔防御的轮动位置。

## 这个 skill 解决什么
`industry-research` 偏**静态**产业链全景，缺"时机/轮动"。`/sector-rotation` 用 `tools/sector_rotation.py`（零依赖）经数据层取板块代理的前复权历史，算多周期动量与相对强弱，排出领涨/领跌板块。

## 执行流程
```bash
# 用板块 ETF/指数作代理（名称=代码，经数据层取历史）
python3 tools/sector_rotation.py rank \
  --from-datalayer "科技=XLK,金融=XLF,能源=XLE,医疗=XLV,必需消费=XLP,工业=XLI" --period 2y
```
输出各板块 多周期动量 + 相对强弱(对市场均值) + 领涨/领跌标记。

A股可用行业指数或行业 ETF 代码；港股同理。

## 判读原则（客观 + 反追高）
- 动量领先 ≠ 低估：轮动尾部追高风险大（马克斯：周期定位）。
- 结合**景气度**（订单/产能/价格/库存）与**估值分位**，动量只是时机线索之一。
- 防御板块(必需消费/医疗/公用)领先，常预示市场转谨慎；顺周期(科技/工业/能源)领先预示风险偏好上升。
- 呈现正反两面，不预设看多看空。

## 相关
`industry-research`（产业链全景）· `industry-funnel`（漏斗筛选）· `master-lens`（马克斯周期镜片）· `tools/datalayer.py`（历史行情）
