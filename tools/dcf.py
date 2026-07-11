#!/usr/bin/env python3
"""估值建模：DCF / 反向DCF / SOTP（P1，零外部依赖，货币全程 Decimal）。

补齐 investment-research 第七步"内在价值"环节——此前只有粗三情景。
  - dcf：多阶段自由现金流折现（显式期 + Gordon 永续），得每股内在价值。
  - reverse：给定当前股价，反解"市场隐含的增长率"（当前价把多高增长 price 已进去）。
  - sotp：分部加总（各业务估值 + 净现金/投资组合）→ 每股。

用法：
  python3 tools/dcf.py dcf --fcf0 1826 --growth "0.14,0.12,0.10,0.09,0.08" \
      --wacc 0.10 --terminal-growth 0.03 --shares 91.3 --net-debt -1071 --currency 亿元
  python3 tools/dcf.py reverse --price 470 --fcf0 20 --wacc 0.10 \
      --terminal-growth 0.03 --shares 91.3 --years 10
  python3 tools/dcf.py sotp --parts "游戏=20000,广告=8000,金科企服=9000" \
      --net-cash 1071 --investments 10358 --shares 91.3 --currency 亿元
"""
import argparse
from decimal import Decimal, getcontext

getcontext().prec = 28
D = lambda x: Decimal(str(x))  # noqa: E731


# --------------------------------------------------------------------------
# 纯函数（可测）
# --------------------------------------------------------------------------
def dcf_value(fcf0, growths, wacc, terminal_growth, shares, net_debt=0):
    """多阶段 DCF。growths: 显式期各年增速列表；末年后按 terminal_growth 永续。
    返回 dict：EV / 权益价值 / 每股 / 各期现值 / 终值现值。net_debt>0=净负债，<0=净现金。"""
    fcf0, wacc, tg = D(fcf0), D(wacc), D(terminal_growth)
    shares, net_debt = D(shares), D(net_debt)
    if wacc <= tg:
        raise ValueError("WACC 必须 > 永续增长率（否则永续值发散）")
    pv_explicit, fcf, pvs = Decimal(0), fcf0, []
    for t, g in enumerate(growths, start=1):
        fcf = fcf * (Decimal(1) + D(g))
        pv = fcf / (Decimal(1) + wacc) ** t
        pvs.append((t, fcf, pv))
        pv_explicit += pv
    n = len(growths)
    tv = fcf * (Decimal(1) + tg) / (wacc - tg)          # Gordon 永续
    pv_tv = tv / (Decimal(1) + wacc) ** n
    ev = pv_explicit + pv_tv
    equity = ev - net_debt
    return {"ev": ev, "equity": equity, "per_share": equity / shares,
            "pv_explicit": pv_explicit, "terminal_value": tv, "pv_terminal": pv_tv,
            "pvs": pvs, "terminal_pct": (pv_tv / ev if ev else Decimal(0))}


def reverse_dcf(price, fcf0, wacc, terminal_growth, shares, years, net_debt=0,
                lo="-0.5", hi="1.0", tol="1e-9", max_iter=200):
    """反解：使 DCF 每股价值 == price 的（显式期恒定）增长率。二分法。"""
    price = D(price)
    lo, hi = D(lo), D(hi)

    def val(g):
        return dcf_value(fcf0, [g] * years, wacc, terminal_growth, shares, net_debt)["per_share"]

    f_lo, f_hi = val(lo) - price, val(hi) - price
    if (f_lo > 0) == (f_hi > 0):
        return None  # 区间内无解
    tol = D(tol)
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        fm = val(mid) - price
        if abs(fm) < tol:
            return mid
        if (fm > 0) == (f_lo > 0):
            lo, f_lo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


def sotp(parts, shares, net_cash=0, investments=0, holdco_discount=0):
    """分部加总。parts: {名称: 业务价值}；+净现金+投资组合(可打折)→权益→每股。"""
    shares = D(shares)
    core = sum((D(v) for v in parts.values()), Decimal(0))
    inv = D(investments) * (Decimal(1) - D(holdco_discount))
    equity = core + D(net_cash) + inv
    return {"core": core, "investments_adj": inv, "net_cash": D(net_cash),
            "equity": equity, "per_share": equity / shares}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _q2(d):
    return d.quantize(Decimal("0.01"))


def cmd_dcf(args):
    growths = [g.strip() for g in args.growth.split(",") if g.strip()]
    r = dcf_value(args.fcf0, growths, args.wacc, args.terminal_growth, args.shares, args.net_debt)
    cur = args.currency
    print("=" * 60)
    print(f"多阶段 DCF · WACC {args.wacc} · 永续 {args.terminal_growth} · {len(growths)} 年显式期")
    print("=" * 60)
    for t, fcf, pv in r["pvs"]:
        print(f"  第{t}年  FCF {_q2(fcf)}  现值 {_q2(pv)} {cur}")
    print(f"  显式期现值合计: {_q2(r['pv_explicit'])} {cur}")
    print(f"  终值现值:       {_q2(r['pv_terminal'])} {cur}  (占EV {r['terminal_pct']:.0%})")
    print(f"  企业价值 EV:    {_q2(r['ev'])} {cur}")
    print(f"  权益价值:       {_q2(r['equity'])} {cur}  (净{'负债' if D(args.net_debt) > 0 else '现金'} {abs(D(args.net_debt))})")
    print(f"  ★ 每股内在价值: {_q2(r['per_share'])} {cur}/股")
    if args.price:
        mos = (r["per_share"] - D(args.price)) / r["per_share"]
        print(f"  当前价 {args.price} → 安全边际 {mos:.0%}  ({'低估' if mos > 0 else '高估'})")


def cmd_reverse(args):
    g = reverse_dcf(args.price, args.fcf0, args.wacc, args.terminal_growth,
                    args.shares, args.years, args.net_debt)
    print("=" * 60)
    print(f"反向 DCF · 当前价 {args.price} · WACC {args.wacc} · {args.years} 年显式期")
    print("=" * 60)
    if g is None:
        print("  在 [-50%, 100%] 内无解（价格过高/过低或参数异常）")
        return
    print(f"  ★ 市场隐含的显式期年增长率: {g:.2%}")
    print(f"  解读：当前股价已把'未来{args.years}年 FCF 年增 {g:.1%}'price 进去；")
    print("        你若判断实际增速高于此→低估，低于此→高估。")


def cmd_sotp(args):
    parts = {}
    for p in args.parts.split(","):
        if "=" in p:
            k, v = p.split("=", 1)
            parts[k.strip()] = v.strip()
    r = sotp(parts, args.shares, args.net_cash, args.investments, args.holdco_discount)
    cur = args.currency
    print("=" * 60)
    print("分部加总 SOTP")
    print("=" * 60)
    for k, v in parts.items():
        print(f"  {k:<12}{_q2(D(v)):>14} {cur}")
    print(f"  核心业务合计:  {_q2(r['core'])} {cur}")
    print(f"  + 投资组合(打折{args.holdco_discount}): {_q2(r['investments_adj'])} {cur}")
    print(f"  + 净现金:      {_q2(r['net_cash'])} {cur}")
    print(f"  权益价值:      {_q2(r['equity'])} {cur}")
    print(f"  ★ 每股价值:    {_q2(r['per_share'])} {cur}/股")
    if args.price:
        mos = (r["per_share"] - D(args.price)) / r["per_share"]
        print(f"  当前价 {args.price} → 安全边际 {mos:.0%}")


def main():
    ap = argparse.ArgumentParser(description="估值建模：DCF/反向DCF/SOTP（P1，零依赖）")
    sub = ap.add_subparsers(dest="cmd")

    d = sub.add_parser("dcf", help="多阶段 DCF")
    d.add_argument("--fcf0", required=True, help="基年自由现金流")
    d.add_argument("--growth", required=True, help='显式期各年增速 "0.14,0.12,0.10"')
    d.add_argument("--wacc", required=True)
    d.add_argument("--terminal-growth", required=True)
    d.add_argument("--shares", required=True, help="总股本(与FCF同单位口径)")
    d.add_argument("--net-debt", default="0", help="净负债(>0)/净现金(<0)")
    d.add_argument("--price", help="当前股价(算安全边际)")
    d.add_argument("--currency", default="")

    r = sub.add_parser("reverse", help="反向 DCF：解市场隐含增长率")
    r.add_argument("--price", required=True)
    r.add_argument("--fcf0", required=True, help="每股FCF")
    r.add_argument("--wacc", required=True)
    r.add_argument("--terminal-growth", required=True)
    r.add_argument("--shares", default="1", help="每股口径时填1")
    r.add_argument("--years", type=int, default=10)
    r.add_argument("--net-debt", default="0")

    s = sub.add_parser("sotp", help="分部加总")
    s.add_argument("--parts", required=True, help='"游戏=20000,广告=8000"')
    s.add_argument("--shares", required=True)
    s.add_argument("--net-cash", default="0")
    s.add_argument("--investments", default="0")
    s.add_argument("--holdco-discount", default="0", help="投资组合折价率 0-1")
    s.add_argument("--price")
    s.add_argument("--currency", default="")

    args = ap.parse_args()
    {"dcf": cmd_dcf, "reverse": cmd_reverse, "sotp": cmd_sotp}.get(
        args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
