#!/usr/bin/env python3
"""估值交叉校验（DCF↔comps↔市价 三角验证，零外部依赖）——L3 交叉验证支柱。

诊断(全链路能力诊断评级)指出：估值域**无 DCF↔comps 跨模型交叉验证**（L3 明列要件），
dcf 的 reverse round-trip 只是单引擎自洽、非跨模型。本工具补这根支柱：

  把**相互独立**的估值方法放到一起对账——
    · DCF(绝对法：贴现未来现金流)
    · comps(相对法：同业中位倍数 × 本公司每股指标)
    · morningstar 公允价值(第三方,可选)
  计算两两**背离度**,给**收敛/分歧**判定 + 三角中枢区间 + 市价定位 + 置信度。

为什么是 L3 支柱：单一方法可能系统性偏差(DCF 对 WACC/g 极敏感、comps 受同业错杀影响)。
两法**独立收敛**才增信;**显著分歧**说明至少一法假设有误——正是该深挖之处。交叉验证把
"一个数"变成"一个被印证或被质疑的结论"。

用法：
  # 直接对账两个已算出的每股价值 + 市价
  python3 tools/valuation_cross_check.py check --dcf 165 --comps 128 --price 140
  # 用 comps 中位 PE × 本公司 EPS 现算相对法隐含价,再与 DCF 对账
  python3 tools/valuation_cross_check.py check --dcf 165 --median-pe 22 --eps 6.1 --price 140
  python3 tools/valuation_cross_check.py check --dcf 165 --comps 128 --mos 150 --price 140 --json
"""
import argparse
import json
import statistics


def implied_from_multiple(multiple, per_share_metric):
    """相对法隐含每股价 = 同业中位倍数 × 本公司每股指标(EPS 或 BPS)。纯函数。"""
    if multiple is None or per_share_metric is None:
        return None
    return multiple * per_share_metric


def divergence(a, b):
    """两估值的相对背离度 = |a−b| / 均值。均值<=0 或异号 → None(不可比)。纯函数。"""
    if a is None or b is None:
        return None
    m = (a + b) / 2.0
    if m <= 0:
        return None
    return abs(a - b) / m


def triangulate(methods):
    """methods: {名称: 每股价值}(去 None)。→ 中枢/区间/离散度/两两背离。纯函数。"""
    vals = {k: v for k, v in methods.items() if v is not None}
    if not vals:
        return {"n": 0, "values": {}, "median": None, "low": None, "high": None,
                "spread_pct": None, "pairwise": {}}
    xs = list(vals.values())
    med = statistics.median(xs)
    lo, hi = min(xs), max(xs)
    spread = (hi - lo) / med if med > 0 else None
    pair = {}
    names = list(vals)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            pair[f"{names[i]}~{names[j]}"] = divergence(vals[names[i]], vals[names[j]])
    return {"n": len(vals), "values": vals, "median": med, "low": lo, "high": hi,
            "spread_pct": spread, "pairwise": pair}


def cross_verdict(methods, price=None, converge_tol=0.15, diverge_tol=0.35):
    """交叉校验判定。→ status(收敛/部分收敛/分歧)、中枢、市价定位、置信度、提示。纯函数。
    converge_tol: 最大两两背离 ≤ 此值 → 收敛;≥ diverge_tol → 分歧;之间 → 部分收敛。"""
    tri = triangulate(methods)
    flags = []
    if tri["n"] < 2:
        return {"status": "数据不足", "triangulation": tri, "confidence": "低",
                "note": "需 ≥2 个独立估值方法才能交叉校验", "flags": ["方法不足"]}

    divs = [d for d in tri["pairwise"].values() if d is not None]
    max_div = max(divs) if divs else None
    if max_div is None:
        status, conf = "不可比", "低"
    elif max_div <= converge_tol:
        status, conf = "收敛", "高"
    elif max_div >= diverge_tol:
        status, conf = "分歧", "低"
    else:
        status, conf = "部分收敛", "中"

    # 哪对分歧最大 + 方向提示
    if status in ("分歧", "部分收敛") and tri["pairwise"]:
        worst = max((p for p in tri["pairwise"].items() if p[1] is not None),
                    key=lambda x: x[1], default=None)
        if worst:
            a, b = worst[0].split("~")
            va, vb = tri["values"][a], tri["values"][b]
            hi_name, lo_name = (a, b) if va > vb else (b, a)
            flags.append(f"{hi_name} 显著高于 {lo_name}（背离 {worst[1]:.0%}）——"
                         f"需查 {hi_name} 假设是否过乐观 / {lo_name} 是否被低估")

    # 市价定位
    price_position = None
    mos = None
    if price is not None and tri["median"]:
        mos = (tri["median"] - price) / tri["median"]      # 相对三角中枢的安全边际
        if price < tri["low"]:
            price_position = "低于所有方法（潜在低估）"
        elif price > tri["high"]:
            price_position = "高于所有方法（潜在高估）"
        else:
            price_position = "落在估值区间内"
        if status == "分歧":
            flags.append("方法分歧时市价定位仅供参考——先解决分歧再谈安全边际")

    return {"status": status, "confidence": conf, "triangulation": tri,
            "price": price, "price_position": price_position, "margin_of_safety": mos,
            "flags": flags}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _collect_methods(args):
    methods = {}
    if args.dcf is not None:
        methods["DCF"] = args.dcf
    if args.comps is not None:
        methods["comps"] = args.comps
    elif args.median_pe is not None and args.eps is not None:
        methods["comps"] = implied_from_multiple(args.median_pe, args.eps)
    if args.mos is not None:
        methods["morningstar"] = args.mos
    return methods


def render(res):
    tri = res["triangulation"]
    L = ["=" * 62, f"估值交叉校验 · {tri['n']} 法三角 · 判定【{res['status']}】(置信 {res['confidence']})", "=" * 62]
    for k, v in tri["values"].items():
        L.append(f"  {k:<12} {v:>10.2f} /股")
    if tri["median"]:
        L.append("  " + "-" * 40)
        L.append(f"  {'三角中枢(中位)':<12} {tri['median']:>10.2f} /股   区间 [{tri['low']:.2f}, {tri['high']:.2f}]"
                 + (f"  离散 {tri['spread_pct']:.0%}" if tri["spread_pct"] is not None else ""))
    if tri["pairwise"]:
        L.append(f"  两两背离: " + " · ".join(
            f"{k} {v:.0%}" if v is not None else f"{k} 不可比" for k, v in tri["pairwise"].items()))
    if res.get("price") is not None:
        L.append("")
        L.append(f"  市价 {res['price']:.2f} → {res['price_position']}"
                 + (f"  安全边际(vs中枢) {res['margin_of_safety']:+.0%}" if res.get("margin_of_safety") is not None else ""))
    for f in res.get("flags", []):
        L.append(f"  ⚠️ {f}")
    L.append("")
    if res["status"] == "收敛":
        L.append("  ✅ 两法独立收敛,估值结论互相印证,置信度高。")
    elif res["status"] == "分歧":
        L.append("  🔴 两法显著分歧——至少一法假设有误,勿直接取中枢,先深挖分歧来源。")
    else:
        L.append("  🟡 部分收敛——结论方向一致但幅度存差,谨慎取区间而非单点。")
    L.append("\n  ⚠️ 交叉验证只校验方法间一致性,不保证任一方法对;comps 隐含价=同业中位倍数×本公司每股指标(受同业与指标口径影响)。")
    return "\n".join(L)


def cmd_check(args):
    methods = _collect_methods(args)
    res = cross_verdict(methods, price=args.price,
                        converge_tol=args.converge_tol, diverge_tol=args.diverge_tol)
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else render(res))


def main():
    ap = argparse.ArgumentParser(description="估值交叉校验(DCF↔comps↔市价三角,L3支柱,零依赖)")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check", help="对账多个独立估值方法")
    c.add_argument("--dcf", type=float, help="DCF 每股内在价值(tools/dcf.py 输出)")
    c.add_argument("--comps", type=float, help="相对法隐含每股价(或用 --median-pe+--eps 现算)")
    c.add_argument("--median-pe", dest="median_pe", type=float, help="同业中位 PE(tools/comps.py)")
    c.add_argument("--eps", type=float, help="本公司每股收益(配 --median-pe 算相对法隐含价)")
    c.add_argument("--mos", type=float, help="morningstar 公允价值(第三方,可选)")
    c.add_argument("--price", type=float, help="当前市价(用于定位/安全边际)")
    c.add_argument("--converge-tol", dest="converge_tol", type=float, default=0.15)
    c.add_argument("--diverge-tol", dest="diverge_tol", type=float, default=0.35)
    c.add_argument("--json", action="store_true")
    args = ap.parse_args()
    {"check": cmd_check}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
