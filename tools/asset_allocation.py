#!/usr/bin/env python3
"""资产配置 SAA/TAA（T3-2，零外部依赖）。

当前组合是纯股票长仓。本工具补**跨资产的战略(SAA)与战术(TAA)配置**：
  · SAA 战略配置 —— 按风险承受度定长期中枢(股/债/商品/现金)，是组合的"锚"。
  · TAA 战术倾斜 —— 按宏观 regime(美林时钟)在中枢附近做有限倾斜(不择时、只调旋钮)。
  · 再平衡带 —— 各资产偏离中枢超容忍带才动手，减少无谓换手。

对接 macro_regime：复苏→超配股票/顺周期;过热→超配商品;滞胀→超配现金/商品、低配股债;
衰退→超配债券。倾斜幅度设上限(默认±10pp)，宏观只调旋钮、绝不清空某类资产。

用法：
  python3 tools/asset_allocation.py saa --risk balanced           # 战略中枢
  python3 tools/asset_allocation.py taa --risk balanced --regime 复苏   # 叠加战术倾斜
  python3 tools/asset_allocation.py rebalance --target "stock=55,bond=30,commodity=5,cash=10" \
      --current "stock=64,bond=22,commodity=4,cash=10" --band 5
"""
import argparse

ASSETS = ["stock", "bond", "commodity", "cash"]
ASSET_CN = {"stock": "股票", "bond": "债券", "commodity": "商品", "cash": "现金"}

# 战略中枢(SAA)：风险档 → 各资产% 长期锚
SAA = {
    "conservative": {"stock": 30, "bond": 50, "commodity": 5, "cash": 15},
    "balanced": {"stock": 55, "bond": 30, "commodity": 5, "cash": 10},
    "growth": {"stock": 75, "bond": 15, "commodity": 5, "cash": 5},
    "aggressive": {"stock": 90, "bond": 5, "commodity": 3, "cash": 2},
}

# 战术倾斜(TAA)：美林时钟象限 → 各资产倾斜(pp，正=超配)
REGIME_TILT = {
    "复苏": {"stock": +10, "bond": -5, "commodity": 0, "cash": -5},     # 增长↑通胀↓:股票最优
    "过热": {"stock": 0, "bond": -10, "commodity": +10, "cash": 0},    # 增长↑通胀↑:商品最优
    "滞胀": {"stock": -10, "bond": -5, "commodity": +10, "cash": +5},  # 增长↓通胀↑:现金/商品避险
    "衰退": {"stock": -5, "bond": +10, "commodity": -5, "cash": 0},    # 增长↓通胀↓:债券最优
}


# --------------------------------------------------------------------------
# 纯函数（可测）
# --------------------------------------------------------------------------
def strategic(risk):
    """战略中枢(SAA)。纯函数。"""
    if risk not in SAA:
        raise ValueError(f"未知风险档: {risk}(可选 {list(SAA)})")
    return dict(SAA[risk])


def tactical(saa, regime, max_tilt=10):
    """在 SAA 上叠加 regime 战术倾斜(单类上限 max_tilt pp)，截断后归一到100。纯函数。"""
    tilt = REGIME_TILT.get(regime, {a: 0 for a in ASSETS})
    raw = {a: saa[a] + max(-max_tilt, min(max_tilt, tilt.get(a, 0))) for a in saa}
    raw = {a: max(0, v) for a, v in raw.items()}       # 不为负
    s = sum(raw.values()) or 1
    return {a: round(v / s * 100, 1) for a, v in raw.items()}


def rebalance_triggers(target, current, band):
    """各资产偏离中枢超 band(pp) 才触发。→ [{asset, target, current, drift, action}]。纯函数。"""
    out = []
    for a in target:
        cur = current.get(a, 0)
        drift = cur - target[a]
        if abs(drift) > band:
            out.append({"asset": a, "target": target[a], "current": cur, "drift": drift,
                        "action": "减" if drift > 0 else "加"})
    return out


def drift_summary(target, current):
    """总偏离度(各资产|偏离|之和的一半=需换手比例)。纯函数。"""
    return sum(abs(current.get(a, 0) - target[a]) for a in target) / 2.0


def _parse(spec):
    out = {}
    for part in (spec or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = float(v)
    return out


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
def _print_alloc(title, alloc):
    print(f"  {title}")
    for a in ASSETS:
        if a in alloc:
            bar = "█" * int(alloc[a] / 2)
            print(f"    {ASSET_CN[a]:<4} {alloc[a]:>5.1f}%  {bar}")


def cmd_saa(args):
    print("=" * 50)
    print(f"战略资产配置 SAA · 风险档【{args.risk}】")
    print("=" * 50)
    _print_alloc("长期中枢:", strategic(args.risk))
    print(f"\n  → SAA 是组合的锚,长期不动;短期只在其附近做有限战术倾斜(见 taa)。")


def cmd_taa(args):
    saa = strategic(args.risk)
    taa = tactical(saa, args.regime, args.max_tilt)
    print("=" * 50)
    print(f"战术资产配置 TAA · 风险档【{args.risk}】· regime【{args.regime}】")
    print("=" * 50)
    _print_alloc("战略中枢(SAA):", saa)
    print()
    _print_alloc(f"叠加战术倾斜后(TAA, 单类上限±{args.max_tilt}pp):", taa)
    tilt = REGIME_TILT.get(args.regime, {})
    print(f"\n  倾斜逻辑({args.regime}): " +
          " · ".join(f"{ASSET_CN[a]}{tilt[a]:+d}pp" for a in ASSETS if tilt.get(a)))
    print(f"  ⚠️ 宏观只调旋钮、绝不清空某类;regime 是事后描述非预测,倾斜幅度须克制。")


def cmd_rebalance(args):
    tgt = _parse(args.target)
    cur = _parse(args.current)
    trig = rebalance_triggers(tgt, cur, args.band)
    print("=" * 56)
    print(f"资产配置再平衡 · 容忍带 ±{args.band}pp")
    print("=" * 56)
    print(f"  {'资产':<6}{'中枢':>7}{'当前':>7}{'偏离':>8}{'动作':>6}")
    for a in ASSETS:
        if a in tgt:
            drift = cur.get(a, 0) - tgt[a]
            act = next((t["action"] for t in trig if t["asset"] == a), "—")
            flag = "⚠️" if abs(drift) > args.band else ""
            print(f"  {ASSET_CN[a]:<6}{tgt[a]:>7.1f}{cur.get(a,0):>7.1f}{drift:>+8.1f}{act:>6} {flag}")
    print(f"\n  总偏离度: {drift_summary(tgt, cur):.1f}pp")
    if trig:
        print(f"  🔴 {len(trig)} 类超容忍带需再平衡: " +
              " · ".join(f"{ASSET_CN[t['asset']]}{t['action']}{abs(t['drift']):.0f}pp" for t in trig))
    else:
        print(f"  🟢 各类均在容忍带内,无需再平衡(减少无谓换手)。")


def main():
    ap = argparse.ArgumentParser(description="资产配置 SAA/TAA(T3-2，跨资产战略战术，零依赖)")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("saa", help="战略中枢")
    s.add_argument("--risk", default="balanced", choices=list(SAA))
    t = sub.add_parser("taa", help="战术倾斜(叠加 regime)")
    t.add_argument("--risk", default="balanced", choices=list(SAA))
    t.add_argument("--regime", required=True, choices=list(REGIME_TILT))
    t.add_argument("--max-tilt", dest="max_tilt", type=float, default=10)
    rb = sub.add_parser("rebalance", help="再平衡带触发")
    rb.add_argument("--target", required=True, help='"stock=55,bond=30,commodity=5,cash=10"')
    rb.add_argument("--current", required=True)
    rb.add_argument("--band", type=float, default=5, help="容忍带 pp")
    args = ap.parse_args()
    {"saa": cmd_saa, "taa": cmd_taa, "rebalance": cmd_rebalance}.get(
        args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
