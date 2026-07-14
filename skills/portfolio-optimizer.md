# 组合优化器：约束下的纪律化权重

对 $ARGUMENTS 给出价值投资约束下的建议权重。

## 这个 skill 解决什么

`portfolio-review` 是定性体检；`/portfolio-optimizer` 用 `tools/portfolio_optimizer.py`（零依赖）给**透明、可解释 + 硬约束**的权重建议——不是黑箱均值方差，而是逆波动(风险平价近似) + IPS 单一上限硬约束。

## 执行流程
```bash
python3 tools/portfolio_optimizer.py optimize --from-datalayer "600519,0700.HK,AAPL,VOO" \
    --method risk-parity --period 5y   # 上限默认读 config/investment-policy.json
```
四种方法（均含 IPS 单一上限硬约束）：
- **逆波动 `inverse-vol`**：波动越低权重越高（忽略相关性的风险平价近似）。
- **风险平价 `risk-parity`**：等风险贡献(ERC)——用协方差矩阵 + 平方根阻尼迭代，让每只对组合风险的贡献相等（考虑相关性，比逆波动更严谨）。
- **最小方差 `min-variance`**：w ∝ Σ⁻¹·1（纯 stdlib Gauss-Jordan 求逆），长仓截零归一——集中于低波/低相关，理论组合波动最小。
- **等权 `equal`**：朴素基准。
- **IPS 上限**：超限者封顶，超出部分按比例再分配（迭代收敛）；`--cap` 可覆盖。
- 输出各标的年化波动、原始权重、上限后权重、HHI/有效持仓数。

## 与其它工具的闭环
1. `/portfolio-optimizer` 给建议权重 →
2. `tools/portfolio_risk.py` 对结果体检(波动/回撤/相关性/集中度) →
3. `tools/position_sizing.py` 对单只用凯利/赔率校验仓位 →
4. `/portfolio-review` 综合决策与再平衡。

## 原则
- 这是**纪律化配置**，非收益最大化；逆波动降低单点风险，但不预测收益。
- 优化只在**已通过质量与估值筛选**的候选内进行——别优化一篮子烂公司的权重。
- 相关性高的资产即使各自波动低，也不能靠"分散"错觉重仓（结合 portfolio_risk 的相关性矩阵看）。

## 相关
`portfolio-review` · `portfolio_risk.py`(诊断) · `position_sizing.py`(单只定仓) · `master-lens`(达利欧·分散)
