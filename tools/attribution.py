#!/usr/bin/env python3
"""业绩归因（P1，零外部依赖）。

回答"收益到底从哪来"：
  1) 贡献分解：每只持仓对组合收益的贡献 = 权重 × 收益（可经数据层实时算区间收益）。
  2) Brinson 归因：相对基准的超额，拆成【配置效应】(选对了行业/市场)
     + 【选股效应】(在行业内选对了股) + 【交互效应】。

配置效应/选股效应是机构区分"运气(踩对赛道) vs 能力(选对个股)"的标准方法。

用法：
  # 贡献分解（经数据层取区间收益）
  python3 tools/attribution.py contribution --from-datalayer "600519=0.4,0700.HK=0.4,AAPL=0.2" --period 1y
  # Brinson 归因（CSV: group,wp,rp,wb,rb）
  python3 tools/attribution.py brinson --file groups.csv
"""
import argparse
import csv


# --------------------------------------------------------------------------
# 纯函数（可测）
# --------------------------------------------------------------------------
def contributions(weights, returns):
    """contribution_i = w_i × r_i；组合收益 = Σ。返回 (dict, total)。"""
    contrib = {s: weights[s] * returns[s] for s in weights}
    return contrib, sum(contrib.values())


def brinson(groups):
    """groups: [{group, wp, rp, wb, rb}] → 每组配置/选股/交互效应 + 汇总。
    BHB 分解：alloc=(wp-wb)(rb-rb_tot); sel=wb(rp-rb); inter=(wp-wb)(rp-rb)。"""
    rb_tot = sum(g["wb"] * g["rb"] for g in groups)
    rp_tot = sum(g["wp"] * g["rp"] for g in groups)
    rows = []
    for g in groups:
        alloc = (g["wp"] - g["wb"]) * (g["rb"] - rb_tot)
        sel = g["wb"] * (g["rp"] - g["rb"])
        inter = (g["wp"] - g["wb"]) * (g["rp"] - g["rb"])
        rows.append({"group": g["group"], "allocation": alloc, "selection": sel,
                     "interaction": inter, "total": alloc + sel + inter})
    return {
        "rows": rows, "rp_total": rp_tot, "rb_total": rb_tot, "excess": rp_tot - rb_tot,
        "allocation": sum(r["allocation"] for r in rows),
        "selection": sum(r["selection"] for r in rows),
        "interaction": sum(r["interaction"] for r in rows),
    }


def _parse_weighted(spec):
    w = {}
    for part in spec.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            w[k.strip()] = float(v)
    tot = sum(w.values())
    return {k: v / tot for k, v in w.items()} if tot else w


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def cmd_contribution(args):
    import datalayer as dl
    weights = _parse_weighted(args.from_datalayer)
    returns = {}
    for s in weights:
        pts = dl.fetch_history(s, freq="weekly", period=args.period)["points"]
        returns[s] = (pts[-1][1] / pts[0][1] - 1) if len(pts) >= 2 else 0.0
    contrib, total = contributions(weights, returns)
    print("=" * 60)
    print(f"贡献分解 · {args.period} · 组合收益 {total:+.2%}")
    print("=" * 60)
    print(f"  {'标的':<10}{'权重':>8}{'区间收益':>10}{'贡献':>10}{'占比':>8}")
    for s in sorted(contrib, key=lambda x: -contrib[x]):
        share = contrib[s] / total if total else 0
        print(f"  {s:<10}{weights[s]:>7.1%}{returns[s]:>10.1%}{contrib[s]:>+10.2%}{share:>7.0%}")
    print(f"  {'合计':<10}{'':>8}{'':>10}{total:>+10.2%}")


def cmd_brinson(args):
    groups = []
    with open(args.file, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            groups.append({"group": r["group"], "wp": float(r["wp"]), "rp": float(r["rp"]),
                           "wb": float(r["wb"]), "rb": float(r["rb"])})
    res = brinson(groups)
    print("=" * 66)
    print(f"Brinson 归因 · 组合 {res['rp_total']:+.2%} vs 基准 {res['rb_total']:+.2%} "
          f"· 超额 {res['excess']:+.2%}")
    print("=" * 66)
    print(f"  {'分组':<12}{'配置效应':>10}{'选股效应':>10}{'交互':>8}{'合计':>10}")
    for r in res["rows"]:
        print(f"  {r['group']:<12}{r['allocation']:>+10.2%}{r['selection']:>+10.2%}"
              f"{r['interaction']:>+8.2%}{r['total']:>+10.2%}")
    print("  " + "-" * 56)
    print(f"  {'汇总':<12}{res['allocation']:>+10.2%}{res['selection']:>+10.2%}"
          f"{res['interaction']:>+8.2%}{res['excess']:>+10.2%}")
    print(f"\n  解读：配置效应={'正' if res['allocation'] >= 0 else '负'}(选赛道)，"
          f"选股效应={'正' if res['selection'] >= 0 else '负'}(选个股)")


def main():
    ap = argparse.ArgumentParser(description="业绩归因：贡献分解 + Brinson（P1，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("contribution", help="个股对组合收益的贡献分解")
    c.add_argument("--from-datalayer", required=True, help='"600519=0.4,0700.HK=0.4,AAPL=0.2"')
    c.add_argument("--period", default="1y", choices=["1y", "2y", "5y", "10y", "max"])
    b = sub.add_parser("brinson", help="Brinson 配置/选股归因（相对基准）")
    b.add_argument("--file", required=True, help="CSV: group,wp,rp,wb,rb")
    args = ap.parse_args()
    if args.cmd == "contribution":
        cmd_contribution(args)
    elif args.cmd == "brinson":
        cmd_brinson(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
