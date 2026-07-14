# 资产配置 SAA/TAA

跨资产战略中枢 + 宏观战术倾斜 + 再平衡带：$ARGUMENTS。T3-2。

## 解决什么

当前组合是纯股票长仓。`asset_allocation.py`(零依赖)补**跨资产配置**——组合的最上层旋钮：
- **SAA 战略配置**：按风险承受度定长期中枢(股/债/商品/现金)，是组合的"锚"。
- **TAA 战术倾斜**：按宏观 regime(美林时钟)在中枢附近做**有限**倾斜——不择时、只调旋钮。
- **再平衡带**：偏离中枢超容忍带才动手，减少无谓换手。

## 执行流程
```bash
python3 tools/asset_allocation.py saa --risk balanced              # 战略中枢
python3 tools/asset_allocation.py taa --risk balanced --regime 复苏  # 叠加战术倾斜(对接 macro_regime)
python3 tools/asset_allocation.py rebalance --target "stock=55,bond=30,commodity=5,cash=10" \
    --current "stock=64,bond=22,commodity=4,cash=10" --band 5
```
- **regime 倾斜逻辑**(对接 `macro_regime`)：复苏→超配股票;过热→超配商品;滞胀→现金/商品避险、低配股;衰退→超配债券。
- 单类倾斜设上限(默认±10pp)，截断后归一——宏观只调旋钮、**绝不清空**某类资产。

## 与其它工具的关系
`macro_regime`(判象限) → `asset_allocation taa`(定跨资产权重) → `portfolio_optimizer`(股票内部权重) → `rebalance`(落订单)。资产配置是最上层，个股优化是其下的一层。

## 原则与诚实边界
- **SAA 是锚、长期不动；TAA 幅度须克制**——regime 是事后描述非预测,过度择时是负和游戏。
- 风险档(conservative/balanced/growth/aggressive)与倾斜幅度是**框架默认值**,须按个人目标/久期/流动性需求校准。
- 当前系统主要是股票研究;债/商品/现金的择券未深入,SAA/TAA 给的是资产**类别**权重。

## 相关
`macro-regime`(regime判别) · `portfolio-optimizer`(类内权重) · `portfolio-review`(总体) · `master-lens`(达利欧·全天候/分散)
