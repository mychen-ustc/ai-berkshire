#!/usr/bin/env python3
"""SEC EDGAR 13F 机构持仓跟踪（零外部依赖，仅 stdlib）。

看一手披露的"聪明钱在买什么、加减了什么"——机构 13F 季报持仓 + 环比增减仓。
官方数据、完全免费、无需 key（仅需 UA 声明 + ≤10 req/s）。它是叠加层——**验证/启发，不替代基本面**。

用法：
  python3 tools/edgar_13f.py holdings --cik 1067983 --top 15      # 伯克希尔最新 13F Top 持仓
  python3 tools/edgar_13f.py holdings --fund berkshire            # 用内置别名
  python3 tools/edgar_13f.py changes --fund berkshire             # 最近两期环比：新建/加/减/清仓
  python3 tools/edgar_13f.py funds                                # 列出内置机构别名

诚实边界：
  · 13F **滞后**：季度末后最多 45 天才披露；只含美股多头（不含做空/期权多为名义/不含现金与海外）。
  · **只知道"上季末持有什么"**，非实时；大师也会错、也会调仓。
  · value 为 13F 口径美元金额（2023 起为整数美元）；同一 issuer 多条已合并。
"""
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402

UA = "ai-berkshire research contact@ai-berkshire.local"
FUNDS = {                    # 常见机构别名 → CIK（可扩充）
    "berkshire": ("1067983", "Berkshire Hathaway (巴菲特)"),
    "bridgewater": ("1350694", "Bridgewater (达利欧)"),
    "scion": ("1649339", "Scion Asset Mgmt (Michael Burry)"),
    "pershing": ("1336528", "Pershing Square (Ackman)"),
    "renaissance": ("1037389", "Renaissance Technologies"),
    "tigerglobal": ("1167483", "Tiger Global"),
    "baupost": ("1061768", "Baupost (Klarman)"),
    "appaloosa": ("1006438", "Appaloosa (Tepper)"),
}


def _get(url):
    return dl._curl(url, ua=UA)


def _local(tag):
    return tag.split("}")[-1]


def _resolve(cik, fund):
    if fund:
        if fund.lower() not in FUNDS:
            raise SystemExit(f"未知别名 {fund}；用 `funds` 看内置列表，或用 --cik 直接指定")
        return FUNDS[fund.lower()][0]
    if not cik:
        raise SystemExit("需 --cik 或 --fund")
    return str(int(cik))


def recent_13f(cik):
    """→ [(accession, filingDate)]，最近在前。"""
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    d = json.loads(_get(url))
    name = d.get("name")
    f = d["filings"]["recent"]
    out = []
    for form, date, acc in zip(f["form"], f["filingDate"], f["accessionNumber"]):
        if form.startswith("13F-HR"):
            out.append((acc, date))
    return name, out


def fetch_infotable(cik, accession):
    """拉某次 13F 的信息表 XML → 持仓 [dict]。"""
    acc_nodash = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}"
    idx = json.loads(_get(f"{base}/index.json"))
    xml_name = None
    for it in idx["directory"]["item"]:
        n = it["name"]
        if n.endswith(".xml") and n != "primary_doc.xml":
            xml_name = n
            break
    if not xml_name:
        return []
    root = ET.fromstring(_get(f"{base}/{xml_name}"))
    holds = []
    for it in root:
        if _local(it.tag) != "infoTable":
            continue
        rec = {"issuer": None, "cusip": None, "value": 0.0, "shares": 0.0}
        for e in it.iter():
            t, txt = _local(e.tag), (e.text or "").strip()
            if t == "nameOfIssuer":
                rec["issuer"] = txt
            elif t == "cusip":
                rec["cusip"] = txt
            elif t == "value":
                rec["value"] = float(txt or 0)
            elif t == "sshPrnamt":
                rec["shares"] = float(txt or 0)
        if rec["cusip"]:
            holds.append(rec)
    return holds


def aggregate(holds):
    """按 cusip 合并（一个 issuer 可能多条），返回 {cusip: {issuer, value, shares}} + 总值。"""
    agg = {}
    for h in holds:
        a = agg.setdefault(h["cusip"], {"issuer": h["issuer"], "value": 0.0, "shares": 0.0})
        a["value"] += h["value"]
        a["shares"] += h["shares"]
    total = sum(a["value"] for a in agg.values())
    return agg, total


def holdings(cik, fund, top=15):
    cik = _resolve(cik, fund)
    name, filings = recent_13f(cik)
    if not filings:
        raise SystemExit(f"CIK {cik} 无 13F-HR 记录")
    acc, date = filings[0]
    agg, total = aggregate(fetch_infotable(cik, acc))
    ranked = sorted(agg.items(), key=lambda kv: -kv[1]["value"])[:top]
    return {"name": name, "cik": cik, "as_of_filing": date, "total_value": total,
            "n_positions": len(agg),
            "top": [{"issuer": v["issuer"], "cusip": k, "value": v["value"],
                     "weight_pct": round(v["value"] / total * 100, 2) if total else None} for k, v in ranked]}


def classify_move(nv, ov):
    """纯函数：新旧市值 → 调仓动作（可离线测试）。"""
    if ov == 0 and nv > 0:
        return "🟢新建"
    if nv == 0 and ov > 0:
        return "🔴清仓"
    if nv > ov * 1.05:
        return "➕加仓"
    if nv < ov * 0.95:
        return "➖减仓"
    return "持平"


def changes(cik, fund, top=12):
    cik = _resolve(cik, fund)
    name, filings = recent_13f(cik)
    if len(filings) < 2:
        raise SystemExit(f"CIK {cik} 少于两期 13F，无法环比")
    (acc_new, d_new), (acc_old, d_old) = filings[0], filings[1]
    new_agg, _ = aggregate(fetch_infotable(cik, acc_new))
    old_agg, _ = aggregate(fetch_infotable(cik, acc_old))
    rows = []
    for cusip in set(new_agg) | set(old_agg):
        nv = new_agg.get(cusip, {}).get("value", 0.0)
        ov = old_agg.get(cusip, {}).get("value", 0.0)
        issuer = (new_agg.get(cusip) or old_agg.get(cusip))["issuer"]
        act = classify_move(nv, ov)
        rows.append({"issuer": issuer, "cusip": cusip, "action": act,
                     "new_value": nv, "old_value": ov, "delta": nv - ov})
    moves = [r for r in rows if r["action"] not in ("持平",)]
    moves.sort(key=lambda r: -abs(r["delta"]))
    return {"name": name, "cik": cik, "period": f"{d_old} → {d_new}", "moves": moves[:top]}


def _yi_usd(v):
    return f"${v / 1e8:.2f}亿" if v >= 1e8 else f"${v / 1e6:.1f}M"


def render_holdings(d):
    L = [f"SEC 13F · {d['name']} · 披露 {d['as_of_filing']} · 组合 {_yi_usd(d['total_value'])} · {d['n_positions']} 只",
         f"  Top {len(d['top'])} 持仓:"]
    for i, h in enumerate(d["top"], 1):
        L.append(f"    {i:>2}. {h['issuer'][:28]:<28} {_yi_usd(h['value']):>10}  {h['weight_pct']}%")
    L.append("\n  ⚠️ 13F 季度滞后(≤45天披露)、只含美股多头；是「上季末持有」、非实时；不替代基本面。")
    return "\n".join(L)


def render_changes(d):
    L = [f"SEC 13F 环比 · {d['name']} · {d['period']}", "  主要调仓(按变动额):"]
    for r in d["moves"]:
        L.append(f"    {r['action']} {r['issuer'][:26]:<26} {_yi_usd(r['new_value']):>10} (上期 {_yi_usd(r['old_value'])})")
    L.append("\n  ⚠️ 13F 滞后、只含美股多头；调仓反映上季末、非实时。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="SEC EDGAR 13F 机构持仓（官方免费无 key，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    h = sub.add_parser("holdings", help="最新 13F Top 持仓")
    h.add_argument("--cik"); h.add_argument("--fund"); h.add_argument("--top", type=int, default=15)
    h.add_argument("--json", action="store_true")
    c = sub.add_parser("changes", help="最近两期环比增减仓")
    c.add_argument("--cik"); c.add_argument("--fund"); c.add_argument("--top", type=int, default=12)
    c.add_argument("--json", action="store_true")
    sub.add_parser("funds", help="列出内置机构别名")
    args = ap.parse_args()

    if args.cmd == "holdings":
        d = holdings(args.cik, args.fund, args.top)
        print(json.dumps(d, ensure_ascii=False, indent=2) if args.json else render_holdings(d))
    elif args.cmd == "changes":
        d = changes(args.cik, args.fund, args.top)
        print(json.dumps(d, ensure_ascii=False, indent=2) if args.json else render_changes(d))
    elif args.cmd == "funds":
        for k, (cik, name) in FUNDS.items():
            print(f"  {k:<14} CIK {cik:<10} {name}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
