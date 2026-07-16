# 估值交叉校验（DCF↔comps↔市价）

多估值法三角对账：$ARGUMENTS。L3 交叉验证支柱（估值侧）。

## 解决什么

诊断指出估值域**无 DCF↔comps 跨模型交叉验证**（L3 明列要件）——dcf 的 reverse round-trip 只是单引擎自洽。`valuation_cross_check.py`（零依赖）把**相互独立**的估值法放一起对账：

- **DCF**（绝对法：贴现现金流）· **comps**（相对法：同业中位倍数 × 本公司每股指标）· **morningstar 公允价值**（第三方，可选）
- 算两两**背离度** → 收敛（≤15%）/ 部分收敛 / 分歧（≥35%）判定 + 三角中枢区间 + 市价定位 + 置信度

**为什么是 L3 支柱**：单一方法可能系统性偏差（DCF 对 WACC/g 极敏感、comps 受同业错杀影响）。两法**独立收敛**才增信；**显著分歧**说明至少一法假设有误——正是该深挖处。把"一个数"变成"被印证或被质疑的结论"。

## 执行流程
```bash
# 直接对账两个已算每股价 + 市价
python3 tools/valuation_cross_check.py check --dcf 165 --comps 158 --price 140
# 用 comps 中位 PE × 本公司 EPS 现算相对法隐含价
python3 tools/valuation_cross_check.py check --dcf 165 --median-pe 22 --eps 6.1 --price 140
# 三法(加 morningstar)+ JSON
python3 tools/valuation_cross_check.py check --dcf 165 --comps 128 --mos 150 --price 140 --json
```
DCF 每股价取自 `tools/dcf.py`；中位 PE 取自 `tools/comps.py`；morningstar FV 取自 `tools/morningstar_fair_value.py`。

## 原则与诚实边界
- **收敛非"正确"，分歧才是信号**：交叉验证只校验方法间一致性，不保证任一方法对。
- **分歧时勿取中枢**：先查哪个方法假设有误（工具会提示方向：哪法显著高/低），解决分歧再谈安全边际。
- comps 隐含价 = 同业中位倍数 × 本公司每股指标，受同业选取与每股口径影响。

## 相关
`dcf`(绝对法) · `comps`(相对法) · `morningstar-fair-value`(第三方) · `signal-calibration`(L3 支柱·信号侧) · `scenario`(三情景)
