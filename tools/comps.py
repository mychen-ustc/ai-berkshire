#!/usr/bin/env python3
"""可比公司相对估值（零外部依赖，仅 stdlib）。

绝对法（DCF）之外的另一条腿：把一只股票放到**可比同业**里看贵贱——
PE / PB / 市值横截面，各自相对同业中位的溢价/折价，(可选)结合一致预期增速的 PEG。
与 dcf 互为交叉验证（"绝对 vs 相对"）。它是叠加层——**给相对位置，不给买卖结论**。

数据（均为已验证的免费源）：
  · 估值：腾讯行情 gtimg（PE 动态 / PB / 总市值，A 股）。
  · PEG（--peg）：复用 consensus（东财一致预期 EPS CAGR）。

诚实边界：
  · 仅 PE/PB/市值（+PEG）；**PS / EV-EBITDA 需营收/EV，本版本未接**（不同业务不可比时 PE 会误导）。
  · **同业需人工给定**（未做行业自动成员）；可比性由你判断——把银行和白酒放一起没意义。
  · **仅 A 股**（gtimg 字段位）；港美股字段位不同，未接入。PE 为负（亏损）不可比、已剔除。

用法：
  python3 tools/comps.py analyze "600519,000858,000568,600809" --peg     # 白酒可比
  python3 tools/comps.py analyze "603986,688981,002049" --anchor 603986   # 半导体，锚定兆易
"""
import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402


def fetch_valuation(symbol):
    """腾讯 gtimg → PE(动)/PB/总市值(亿)/换手（A 股字段位）。"""
    info = dl.detect(symbol)
    if info["market"] != "A":
        raise ValueError(f"可比估值当前仅 A 股（gtimg 字段位），{info['symbol']} 为 {info['market']} 股")
    raw = dl._curl(f"https://qt.gtimg.cn/q={info['tencent']}")
    body = raw.split('"', 2)[1] if '"' in raw else raw
    f = body.split("~")

    def g(i):
        try:
            return float(f[i])
        except (ValueError, IndexError):
            return None
    return {"symbol": info["symbol"], "name": f[1] if len(f) > 1 else symbol,
            "price": g(3), "pe": g(39), "mktcap_yi": g(44), "pb": g(46), "turnover": g(38)}


def analyze(symbols, with_peg=False, anchor=None):
    rows = []
    for s in symbols:
        try:
            v = fetch_valuation(s)
            if with_peg:
                try:
                    import consensus as cs
                    c = cs.fetch_consensus(s)
                    v["eps_cagr"] = c.get("eps_cagr_pct")
                    v["fwd_pe"] = c.get("fwd_pe")
                    v["peg"] = (v["fwd_pe"] / v["eps_cagr"]) if (v.get("fwd_pe") and v.get("eps_cagr") and v["eps_cagr"] > 0) else None
                except Exception as e:  # noqa: BLE001
                    v["peg_err"] = str(e)
            rows.append(v)
        except Exception as e:  # noqa: BLE001
            rows.append({"symbol": s, "error": str(e)})

    med_pe, med_pb = cross_section(rows)
    return {"symbols": symbols, "median_pe": med_pe, "median_pb": med_pb,
            "anchor": anchor, "rows": rows, "with_peg": with_peg}


def cross_section(rows):
    """纯函数：给估值行加"相对同业中位溢价/折价"，返回 (中位PE, 中位PB)。仅正 PE 计入中位。"""
    valid = [r for r in rows if r.get("pe") and r["pe"] > 0]
    pb_vals = [r["pb"] for r in valid if r.get("pb")]
    med_pe = statistics.median([r["pe"] for r in valid]) if valid else None
    med_pb = statistics.median(pb_vals) if pb_vals else None
    for r in rows:
        if r.get("pe") and r["pe"] > 0 and med_pe:            # 负 PE(亏损)不可比、不标注
            r["pe_vs_median_pct"] = round((r["pe"] / med_pe - 1) * 100, 1)   # >0 贵于同业
        if r.get("pb") and r["pb"] > 0 and med_pb:
            r["pb_vs_median_pct"] = round((r["pb"] / med_pb - 1) * 100, 1)
    return med_pe, med_pb


def render(res):
    L = ["=" * 74]
    L.append(f"可比公司相对估值 · {len(res['rows'])} 只 · 同业中位 PE {res['median_pe']:.1f} / PB {res['median_pb']:.2f}"
             if res["median_pe"] else "可比公司相对估值")
    L.append("=" * 74)
    hdr = f"  {'标的':<10}{'PE':>7}{'PB':>7}{'市值(亿)':>10}{'PE vs中位':>10}"
    if res["with_peg"]:
        hdr += f"{'EPS增速':>9}{'PEG':>7}"
    L.append(hdr)
    L.append("  " + "-" * (len(hdr)))
    for r in sorted(res["rows"], key=lambda x: (x.get("pe") is None, x.get("pe") or 0)):
        if r.get("error"):
            L.append(f"  {r['symbol']:<10} 取数失败: {r['error'][:40]}")
            continue
        mark = " ★" if res.get("anchor") and r["symbol"].startswith(res["anchor"]) else ""
        line = (f"  {(r['name'] or r['symbol'])[:8]:<10}{r['pe'] or 0:>7.1f}{r.get('pb') or 0:>7.2f}"
                f"{r.get('mktcap_yi') or 0:>10.0f}{(str(r.get('pe_vs_median_pct')) + '%') if r.get('pe_vs_median_pct') is not None else '—':>10}")
        if res["with_peg"]:
            eps = f"{r['eps_cagr']:+.0f}%" if r.get("eps_cagr") is not None else "—"
            peg = f"{r['peg']:.2f}" if r.get("peg") else "—"
            line += f"{eps:>9}{peg:>7}"
        L.append(line + mark)
    # 解读
    valid = [r for r in res["rows"] if r.get("pe_vs_median_pct") is not None]
    if valid:
        cheap = min(valid, key=lambda x: x["pe_vs_median_pct"])
        rich = max(valid, key=lambda x: x["pe_vs_median_pct"])
        L.append(f"\n  同业最低估: {cheap['name']}（PE 低于中位 {abs(cheap['pe_vs_median_pct']):.0f}%）"
                 f" · 最高估: {rich['name']}（高于中位 {rich['pe_vs_median_pct']:.0f}%）")
    L.append("\n  ⚠️ 仅 PE/PB/市值(+PEG)、需同业可比才有意义；PE 低≠便宜(可能盈利要跌)；与 DCF 交叉验证，不单独下结论。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="可比公司相对估值（PE/PB/市值横截面 + PEG，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("analyze", help="对可比同业做相对估值")
    a.add_argument("symbols", help='逗号分隔的可比同业，如 "600519,000858,000568"')
    a.add_argument("--peg", action="store_true", help="加算 PEG（需一致预期，较慢）")
    a.add_argument("--anchor", help="标注锚定标的（★）")
    a.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd != "analyze":
        ap.print_help()
        return
    syms = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if len(syms) < 2:
        raise SystemExit("可比估值至少需 2 只同业")
    res = analyze(syms, with_peg=args.peg, anchor=args.anchor)
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else render(res))


if __name__ == "__main__":
    main()
