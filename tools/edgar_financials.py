#!/usr/bin/env python3
"""EDGAR 财务数据摄取（点时，零外部依赖）。

从 SEC EDGAR companyconcept API 拉**真实**财务数据(净利/股东权益/营收/股本)及其
**filing date(披露日)**，按披露日录入点时财务库(pit_financials)——喂出真数据、
不编。filing date 天然是 available_at，故录入即无前视。

解锁 factor_library 的**质量(ROE)与规模(市值)维度**：ROE=净利/股东权益、
市值=股本×现价——这两块此前因缺点时基本面而无法计算。

数据源：data.sec.gov XBRL companyconcept（官方、免费、无 key）。仅美股 10-K 申报人。

用法：
  python3 tools/edgar_financials.py ingest --symbol AAPL          # 拉 AAPL 财务→点时库
  python3 tools/edgar_financials.py ingest --symbol GOOGL --cik 1652044
  python3 tools/edgar_financials.py ingest-core                   # 核心美股持仓批量
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402
import pit_financials as pf  # noqa: E402

UA = "ai-berkshire research contact@example.com"

# 核心美股持仓 ticker → CIK（SEC 官方编号）
CIK_MAP = {
    "AAPL": 320193, "GOOGL": 1652044, "GOOG": 1652044, "AXP": 4962,
    "KO": 21344, "COST": 909832, "NDAQ": 1120193, "BRK.B": 1067983,
    "MSFT": 789019, "NVDA": 1045810, "META": 1326801, "AMZN": 1018724,
}

# 概念标签(不同公司可能用不同 tag，逐个尝试)
CONCEPTS = {
    "net_income": ["NetIncomeLoss"],
    "stockholders_equity": ["StockholdersEquity",
                            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                "RevenueFromContractWithCustomerIncludingAssessedTax"],
}


def annual_points(units):
    """从 XBRL units 提取年度(10-K/FY)点，按会计期末去重取**首次披露**(PIT关键)。纯函数。"""
    ann = [u for u in units if u.get("form") == "10-K" and u.get("fp") == "FY" and u.get("end")]
    by_end = {}
    for u in ann:
        e = u["end"]
        if e not in by_end or u["filed"] < by_end[e]["filed"]:   # 取最早披露
            by_end[e] = u
    return sorted(by_end.values(), key=lambda x: x["end"])


def _fetch_concept(cik, tags):
    """拉某概念的年度(FY)点，返回 [{end, filed, val, fy}]。"""
    for tag in tags:
        url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{int(cik):010d}/us-gaap/{tag}.json"
        try:
            d = json.loads(dl._curl(url, ua=UA))
        except Exception:  # noqa: BLE001
            continue
        pts = annual_points(d.get("units", {}).get("USD", []))
        if pts:
            return pts
    return []


def ingest_symbol(symbol, cik, path=pf.STORE, limit=6):
    """拉 symbol 的净利/权益/营收 → 录点时库 + 计算 ROE。返回录入条数。"""
    if not cik:
        cik = CIK_MAP.get(symbol.upper())
    if not cik:
        raise SystemExit(f"未知 CIK：{symbol}（用 --cik 指定，或非美股10-K申报人）")

    data = {m: _fetch_concept(cik, tags) for m, tags in CONCEPTS.items()}
    # 以净利的会计期为主轴，对齐权益/营收
    equity_by_end = {u["end"]: u for u in data["stockholders_equity"]}
    rev_by_end = {u["end"]: u for u in data["revenue"]}

    n = 0
    ni_points = data["net_income"][-limit:]
    for u in ni_points:
        end, filed, ni = u["end"], u["filed"], u["val"]
        fy = f"FY{u.get('fy')}"
        pf.append({"symbol": symbol, "metric": "net_income", "fiscal_period": fy,
                   "value": ni, "available_at": filed, "unit": "USD", "source": "EDGAR 10-K"}, path)
        n += 1
        eq = equity_by_end.get(end)
        if eq:
            pf.append({"symbol": symbol, "metric": "stockholders_equity", "fiscal_period": fy,
                       "value": eq["val"], "available_at": eq["filed"], "unit": "USD",
                       "source": "EDGAR 10-K"}, path)
            n += 1
            # ROE = 净利 / 股东权益(同期)；披露日取两者较晚(都可得才算得出)
            roe = ni / eq["val"] if eq["val"] else None
            if roe is not None:
                pf.append({"symbol": symbol, "metric": "roe", "fiscal_period": fy,
                           "value": round(roe, 4), "available_at": max(filed, eq["filed"]),
                           "unit": "ratio", "source": "EDGAR 10-K(算)"}, path)
                n += 1
        rv = rev_by_end.get(end)
        if rv:
            pf.append({"symbol": symbol, "metric": "revenue", "fiscal_period": fy,
                       "value": rv["val"], "available_at": rv["filed"], "unit": "USD",
                       "source": "EDGAR 10-K"}, path)
            n += 1
    return n, ni_points


def cmd_ingest(args):
    n, pts = ingest_symbol(args.symbol, args.cik, args.path, args.limit)
    print(f"✅ {args.symbol}: 录入 {n} 条点时财务(EDGAR，披露日=available_at，无前视)")
    for u in pts:
        print(f"   FY{u.get('fy')} 净利 {u['val']/1e9:>7.1f}B  期末 {u['end']}  披露 {u['filed']}")
    if pts:
        latest = pts[-1]
        print(f"   → 最新已披露 FY{latest.get('fy')}(披露 {latest['filed']})。"
              f"factor_library 的质量(ROE)维度现可算。")


def cmd_ingest_core(args):
    core = ["AAPL", "GOOGL", "AXP", "KO", "COST", "NDAQ"]
    total = 0
    for s in core:
        try:
            n, _ = ingest_symbol(s, None, args.path, args.limit)
            total += n
            print(f"  ✅ {s}: {n} 条")
        except Exception as e:  # noqa: BLE001
            print(f"  ❌ {s}: {str(e)[:60]}")
    print(f"\n共录入 {total} 条点时财务。BRK.B(控股公司)/兆易(A股)/ETF 不在此(EDGAR美股10-K限)。")


def main():
    ap = argparse.ArgumentParser(description="EDGAR 财务摄取(点时，真实数据，零依赖)")
    ap.add_argument("--path", default=pf.STORE)
    sub = ap.add_subparsers(dest="cmd")
    ig = sub.add_parser("ingest", help="拉单只财务→点时库")
    ig.add_argument("--symbol", required=True)
    ig.add_argument("--cik", type=int)
    ig.add_argument("--limit", type=int, default=6, help="录最近N个财年")
    ic = sub.add_parser("ingest-core", help="核心美股持仓批量")
    ic.add_argument("--limit", type=int, default=6)
    args = ap.parse_args()
    {"ingest": cmd_ingest, "ingest-core": cmd_ingest_core}.get(
        args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
