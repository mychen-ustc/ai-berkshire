#!/usr/bin/env python3
"""板块轮动：动量 / 相对强弱排名（P1，零外部依赖）。

给一组板块代理（板块 ETF 或指数），经数据层取前复权历史，计算多周期动量、
相对强弱（对全市场均值），排名找领涨/领跌板块，辅助顺周期↔防御的轮动判断。
补 industry-research 偏静态的短板——加"时机/轮动"维度。统计量用 float。

用法：
  python3 tools/sector_rotation.py rank --from-datalayer "科技=XLK,金融=XLF,能源=XLE,医疗=XLV,必需消费=XLP" --period 2y
"""
import argparse


def trailing_return(prices, lb):
    """过去 lb 期的收益率。prices 升序。"""
    if len(prices) <= lb:
        return None
    return prices[-1] / prices[-1 - lb] - 1


def momentum_score(prices, lookbacks):
    """多周期动量 = 各回看期收益的均值（忽略数据不足的周期）。"""
    rs = [trailing_return(prices, lb) for lb in lookbacks]
    rs = [r for r in rs if r is not None]
    return sum(rs) / len(rs) if rs else None


def rank_sectors(hist_map, lookbacks=(13, 26, 52)):
    """hist_map: {sector: [close...]} → 排名列表 + 市场均值 + 相对强弱(RS)。"""
    scored = {}
    for s, prices in hist_map.items():
        m = momentum_score(prices, lookbacks)
        if m is not None:
            scored[s] = m
    if not scored:
        return [], None
    market = sum(scored.values()) / len(scored)
    rows = [{"sector": s, "momentum": m, "rs": m - market} for s, m in scored.items()]
    rows.sort(key=lambda r: -r["momentum"])
    return rows, market


def _parse_map(spec):
    out = {}
    for part in spec.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def cmd_rank(args):
    import datalayer as dl
    proxies = _parse_map(args.from_datalayer)
    hist = {}
    for name, sym in proxies.items():
        pts = dl.fetch_history(sym, freq="weekly", period=args.period)["points"]
        hist[name] = [c for _, c in pts]
    rows, market = rank_sectors(hist, lookbacks=(13, 26, 52))
    print("=" * 60)
    print(f"板块轮动排名 · {args.period} · 市场动量均值 {market:+.1%}")
    print("=" * 60)
    print(f"  {'板块':<12}{'动量':>10}{'相对强弱':>12}  强弱")
    for r in rows:
        bar = "领涨▲" if r["rs"] > 0.03 else ("领跌▼" if r["rs"] < -0.03 else "中性")
        print(f"  {r['sector']:<12}{r['momentum']:>+10.1%}{r['rs']:>+12.1%}  {bar}")
    if rows:
        print(f"\n  领涨：{rows[0]['sector']}（{rows[0]['momentum']:+.1%}）"
              f" · 领跌：{rows[-1]['sector']}（{rows[-1]['momentum']:+.1%}）")
        print("  提示：动量领先≠低估；结合估值与景气度，避免在轮动尾部追高（马克斯：周期定位）。")


def main():
    ap = argparse.ArgumentParser(description="板块轮动：动量/相对强弱（P1，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("rank", help="板块动量排名")
    r.add_argument("--from-datalayer", required=True, help='"科技=XLK,金融=XLF,能源=XLE"')
    r.add_argument("--period", default="2y", choices=["1y", "2y", "5y", "10y", "max"])
    args = ap.parse_args()
    if args.cmd == "rank":
        cmd_rank(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
