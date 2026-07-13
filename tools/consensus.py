#!/usr/bin/env python3
"""一致预期跟踪（零外部依赖，仅 stdlib）。

价格常由「预期修正方向」驱动。本工具拉卖方一致预期，回答：
  · 机构覆盖多少、评级偏乐观还是谨慎？
  · 未来几年 EPS 预期增速多快？
  · 结合现价的前瞻 PE / PEG——市场是否已把成长充分定价？
它是叠加层——帮你看清「你的判断 vs 市场共识」的差距，**永不替代自己的估值**。

数据：A 股用东财一致预期（RPT_WEB_RESPREDICT：机构评级分布 + 当年实际/未来 3 年预测 EPS）。

诚实边界：
  · 卖方一致预期**系统性偏乐观**（卖出评级极少）；EPS 是预测、非事实。
  · 本版本取**最新快照**，尚无"盈利修正动量"时间序列（修正方向趋势待补，见路线图 P4-4）。
  · **仅 A 股**（东财）；美股一致预期需 Finnhub/FMP 等带 key 的源（Yahoo quoteSummary 已 crumb 锁），本版本未接入。

用法：
  python3 tools/consensus.py analyze 600519
  python3 tools/consensus.py analyze 300750 --json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402


def fetch_consensus(symbol):
    info = dl.detect(symbol)
    if info["market"] != "A":
        raise ValueError(f"一致预期当前仅 A 股（东财），{info['symbol']} 为 {info['market']} 股；"
                         "美股需 Finnhub/FMP 等带 key 的源（本版本未接入）")
    import re
    code = re.sub(r"\D", "", info["tencent"])[-6:]
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_WEB_RESPREDICT"
           f"&columns=ALL&filter=(SECURITY_CODE%3D%22{code}%22)&pageSize=1"
           "&sortColumns=RATING_ORG_NUM&sortTypes=-1")
    raw = dl._curl(url, headers=["Referer: https://data.eastmoney.com/"])
    d = json.loads(raw)
    rows = ((d.get("result") or {}).get("data")) or []
    if not rows:
        raise SystemExit(f"{info['symbol']} 无一致预期数据（可能覆盖机构过少或非A股主板标的）")
    r = rows[0]
    # 现价（算前瞻 PE）
    price = None
    try:
        price = dl.fetch_quote(symbol, cross=False).get("price")
    except Exception:  # noqa: BLE001
        pass
    return _build(r, price, info["symbol"])


def _build(r, price, symbol):
    def num(k):
        v = r.get(k)
        return v if isinstance(v, (int, float)) else None

    org = num("RATING_ORG_NUM") or 0
    buy, add = num("RATING_BUY_NUM") or 0, num("RATING_ADD_NUM") or 0
    neu, red, sale = num("RATING_NEUTRAL_NUM") or 0, num("RATING_REDUCE_NUM") or 0, num("RATING_SALE_NUM") or 0
    bullish = buy + add
    total_r = buy + add + neu + red + sale
    bull_pct = (bullish / total_r * 100) if total_r else None

    # 前瞻 EPS 序列（YEAR1..4 + MARK A/E）
    eps_series = []
    for i in range(1, 5):
        y, mk, e = r.get(f"YEAR{i}"), r.get(f"YEAR_MARK{i}"), num(f"EPS{i}")
        if y and e is not None:
            eps_series.append({"year": y, "mark": mk, "eps": e})
    # 增速
    growth = []
    for i in range(1, len(eps_series)):
        p, c = eps_series[i - 1]["eps"], eps_series[i]["eps"]
        growth.append((c / p - 1) * 100 if p else None)
    # EPS CAGR（首→末）
    eps_cagr = None
    if len(eps_series) >= 2:
        first, last = eps_series[0]["eps"], eps_series[-1]["eps"]
        yrs = len(eps_series) - 1
        if first and first > 0 and last > 0:
            eps_cagr = ((last / first) ** (1 / yrs) - 1) * 100
    # 前瞻 PE：现价 / 下一预测年 EPS
    fwd = next((x for x in eps_series if x["mark"] == "E"), None)
    fwd_pe = (price / fwd["eps"]) if (price and fwd and fwd["eps"]) else None
    peg = (fwd_pe / eps_cagr) if (fwd_pe and eps_cagr and eps_cagr > 0) else None

    stance = ("乐观" if (bull_pct or 0) >= 80 else ("谨慎" if (bull_pct or 0) < 50 else "中性"))
    return {"symbol": symbol, "name": r.get("SECURITY_NAME_ABBR"), "industry": r.get("INDUSTRY_BOARD"),
            "org_num": org, "buy": buy, "add": add, "neutral": neu, "reduce": red, "sale": sale,
            "bullish_pct": round(bull_pct, 1) if bull_pct is not None else None, "stance": stance,
            "price": price, "eps_series": eps_series,
            "eps_growth_pct": [round(g, 1) if g is not None else None for g in growth],
            "eps_cagr_pct": round(eps_cagr, 1) if eps_cagr is not None else None,
            "fwd_pe": round(fwd_pe, 1) if fwd_pe else None,
            "peg": round(peg, 2) if peg else None}


def render(c):
    L = ["=" * 60, f"一致预期 · {c['name']} [{c['symbol']}] · {c['industry'] or ''}", "=" * 60]
    L.append(f"  机构覆盖: {c['org_num']} 家  ·  评级倾向: {c['stance']}"
             + (f"（看多占比 {c['bullish_pct']}%）" if c['bullish_pct'] is not None else ""))
    L.append(f"    买入 {c['buy']} · 增持 {c['add']} · 中性 {c['neutral']} · 减持 {c['reduce']} · 卖出 {c['sale']}")
    L.append("  前瞻 EPS（A=实际 / E=预测）:")
    line = "    " + "  ".join(f"{x['year']}{x['mark']}:{x['eps']:.2f}" for x in c["eps_series"])
    L.append(line)
    if c["eps_growth_pct"]:
        L.append(f"    同比增速: {'  '.join(f'{g:+.1f}%' if g is not None else '—' for g in c['eps_growth_pct'])}")
    if c["eps_cagr_pct"] is not None:
        L.append(f"    预期 EPS CAGR: {c['eps_cagr_pct']:+.1f}%")
    if c["price"]:
        L.append(f"  现价 {c['price']}  ·  前瞻 PE {c['fwd_pe'] if c['fwd_pe'] else '—'}"
                 + (f"  ·  PEG {c['peg']}" if c['peg'] else ""))
    # 反向解读
    hint = []
    if (c["bullish_pct"] or 0) >= 90:
        hint.append("评级高度一致乐观 → 预期可能已充分定价，警惕不及预期")
    if c["peg"] and c["peg"] > 1.5:
        hint.append(f"PEG {c['peg']} 偏高 → 成长已被市场买单")
    if c["peg"] and 0 < c["peg"] < 1:
        hint.append(f"PEG {c['peg']} < 1 → 若预期兑现，估值不算贵")
    if hint:
        L.append("  解读: " + "；".join(hint))
    L.append("\n  ⚠️ 卖方一致预期系统性偏乐观、为预测非事实；此为最新快照(无修正动量序列)；仅辅助看认知差，不替代自己估值。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="一致预期跟踪（A股机构评级 + 前瞻EPS + 前瞻PE，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("analyze", help="拉取并分析个股一致预期")
    a.add_argument("symbol")
    a.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd != "analyze":
        ap.print_help()
        return
    c = fetch_consensus(args.symbol)
    print(json.dumps(c, ensure_ascii=False, indent=2) if args.json else render(c))


if __name__ == "__main__":
    main()
