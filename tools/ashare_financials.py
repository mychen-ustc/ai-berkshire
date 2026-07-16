#!/usr/bin/env python3
"""A 股财务数据摄取（点时，零外部依赖）——补齐 pit_financials 的 A 股半边。

诊断(全链路能力诊断评级)指出：pit_financials 仅美股 25 只(EDGAR)，**A 股质量(ROE)因子
缺数据**。本工具从东方财富**业绩报表**拉 A 股**真实**年报财务(归母净利/营收/加权ROE/EPS)
及其**公告日(NOTICE_DATE)**，按公告日录入点时财务库——公告日天然是 available_at，录入即无前视。

解锁 factor_library 的**质量(ROE)维度**对 A 股生效(此前只有美股),并让 A 股历史基本面
可用于 comps 分位/statement_model。

数据源：datacenter-web.eastmoney.com RPT_LICO_FN_CPD(业绩报表,官方、免费、无 key)。仅 A 股。
ROE 口径：东财 WEIGHTAVG_ROE 是**百分数**(如 4.14 表示 4.14%)，本工具 ÷100 转**比率**，
与 EDGAR roe(净利/权益,比率)统一，供质量因子横截面 z-score。

诚实边界：录**真实公告数据**，不编。成长因子仍用 us_consensus(仅美股,前瞻一致预期)——A 股
无免费前瞻一致预期源，若用 A 股历史 EPS CAGR 会与美股的前瞻口径混用、污染同一横截面因子，
故不做(诚实优先于覆盖)；shares(总股本)取当前快照(总市值/价),供规模因子。

用法：
  python3 tools/ashare_financials.py ingest --symbol 002185          # 拉华天科技财务→点时库
  python3 tools/ashare_financials.py ingest-universe                 # 真实工作 universe 的 A 股批量
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl       # noqa: E402
import pit_financials as pf  # noqa: E402


def _num(v):
    """东财字段 → float，空/None → None。纯函数。"""
    if v in (None, "", "-", "--"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_report(row):
    """一条业绩报表 → 标准化 dict(仅年报关心的字段)。缺关键字段返回 None。纯函数。
    ROE 由百分数 ÷100 转比率(对齐 EDGAR)。"""
    rd = str(row.get("REPORTDATE", ""))[:10]
    notice = str(row.get("NOTICE_DATE", ""))[:10]
    year = row.get("DATAYEAR")
    if not rd or not notice or not year:
        return None
    ni = _num(row.get("PARENT_NETPROFIT"))
    rev = _num(row.get("TOTAL_OPERATE_INCOME"))
    roe_pct = _num(row.get("WEIGHTAVG_ROE"))
    eps = _num(row.get("BASIC_EPS"))
    bps = _num(row.get("BPS"))
    return {
        "year": int(year), "report_date": rd, "notice_date": notice,
        "is_annual": rd.endswith("12-31"),
        "net_income": ni, "revenue": rev,
        "roe": (roe_pct / 100.0) if roe_pct is not None else None,   # 百分数→比率
        "eps": eps, "bps": bps,
    }


def annual_points(rows, limit=6):
    """业绩报表 rows → 年报点(按会计期末 12-31 过滤)，按年去重取**最早公告**(PIT),取最近 limit 年。纯函数。"""
    by_year = {}
    for r in rows:
        p = parse_report(r)
        if not p or not p["is_annual"]:
            continue
        y = p["year"]
        if y not in by_year or p["notice_date"] < by_year[y]["notice_date"]:
            by_year[y] = p
    return sorted(by_year.values(), key=lambda x: x["year"])[-limit:]


# --------------------------------------------------------------------------
# 抓取（IO）
# --------------------------------------------------------------------------
def fetch_reports(code, page_size=40):
    """东财业绩报表 RPT_LICO_FN_CPD → rows。code 为纯数字(如 002185)。IO。"""
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?"
           "reportName=RPT_LICO_FN_CPD&columns=ALL"
           f"&filter=(SECURITY_CODE=%22{code}%22)"
           f"&sortColumns=REPORTDATE&sortTypes=-1&pageNumber=1&pageSize={page_size}")
    try:
        d = json.loads(dl._curl(url))
        return (d.get("result") or {}).get("data") or []
    except Exception:  # noqa: BLE001
        return []


def fetch_total_shares(symbol):
    """当前总股本 = 总市值/现价(腾讯 gtimg)。供规模因子。IO。返回 (shares, price) 或 (None, None)。"""
    info = dl.detect(symbol)
    if info["market"] != "A" or not info.get("tencent"):
        return None, None
    try:
        raw = dl._curl(f"https://qt.gtimg.cn/q={info['tencent']}")
        f = raw.split('"', 2)[1].split("~")
        price = float(f[3])
        mktcap_yi = float(f[44])          # 总市值(亿元)
        if price > 0 and mktcap_yi > 0:
            return mktcap_yi * 1e8 / price, price
    except Exception:  # noqa: BLE001
        pass
    return None, None


def _bare_code(symbol):
    """→ 纯数字代码(东财要 002185 而非 002185.SZ)。"""
    return dl.detect(symbol)["symbol"].split(".")[0]


# --------------------------------------------------------------------------
# 摄取
# --------------------------------------------------------------------------
def _present_keys(path):
    """已在点时库中的 (symbol, metric, fiscal_period, available_at) 集合，用于幂等去重。"""
    keys = set()
    for r in pf.load(path):
        keys.add((r.get("symbol"), r.get("metric"), r.get("fiscal_period"), r.get("available_at")))
    return keys


def ingest_symbol(symbol, path=pf.STORE, limit=6):
    """拉 symbol 的年报财务 → 点时库(available_at=公告日,无前视)。幂等(去重已存在的期)。
    返回 (新录入条数, points)。"""
    if dl.detect(symbol)["market"] != "A":
        raise SystemExit(f"{symbol} 非 A 股(本工具仅 A 股;美股用 edgar_financials)")
    code = _bare_code(symbol)
    key = dl.detect(symbol)["symbol"]              # 规范化键 002185.SZ
    pts = annual_points(fetch_reports(code), limit)
    present = _present_keys(path)
    n = 0
    for p in pts:
        fy = f"FY{p['year']}"
        for metric, val, unit in (("net_income", p["net_income"], "CNY"),
                                   ("revenue", p["revenue"], "CNY"),
                                   ("roe", p["roe"], "ratio"),
                                   ("eps", p["eps"], "CNY/share")):
            if val is None or (key, metric, fy, p["notice_date"]) in present:
                continue
            pf.append({"symbol": key, "metric": metric, "fiscal_period": fy,
                       "value": round(val, 6), "available_at": p["notice_date"],
                       "unit": unit, "source": "东财业绩报表"}, path)
            present.add((key, metric, fy, p["notice_date"]))
            n += 1
    # 当前总股本(供规模因子;available_at=今日,是当前快照;同日不重复录)
    shares, _px = fetch_total_shares(symbol)
    if shares:
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        if (key, "shares", today, today) not in present:
            pf.append({"symbol": key, "metric": "shares", "fiscal_period": today,
                       "value": round(shares), "available_at": today,
                       "unit": "shares", "source": "腾讯(算:总市值/价)"}, path)
            n += 1
    return n, pts


def cmd_ingest(args):
    n, pts = ingest_symbol(args.symbol, args.path, args.limit)
    key = dl.detect(args.symbol)["symbol"]
    print(f"✅ {key}: 录入 {n} 条点时财务(东财,公告日=available_at,无前视)")
    for p in pts:
        roe = f"{p['roe']*100:.2f}%" if p["roe"] is not None else "—"
        ni = f"{p['net_income']/1e8:.2f}亿" if p["net_income"] is not None else "—"
        print(f"   FY{p['year']}  归母净利 {ni:>9}  加权ROE {roe:>7}  公告 {p['notice_date']}")
    if pts:
        print(f"   → factor_library 质量(ROE)维度现对 {key} 生效(此前仅美股)。")


def cmd_ingest_universe(args):
    import ingest_universe as iu
    universe, _ = iu.load_universe()
    a_syms = [u["symbol"] for u in universe if iu._market(u["symbol"]) == "A"]
    print(f"A 股 universe {len(a_syms)} 只：{', '.join(a_syms)}\n")
    total, ok = 0, 0
    for s in a_syms:
        try:
            n, pts = ingest_symbol(s, args.path, args.limit)
            total += n
            ok += 1 if pts else 0
            latest = pts[-1] if pts else None
            tag = f"最新 FY{latest['year']}(公告 {latest['notice_date']})" if latest else "无年报"
            print(f"  ✅ {dl.detect(s)['symbol']:<11} {n:>2} 条  {tag}")
        except Exception as e:  # noqa: BLE001
            print(f"  ❌ {s}: {str(e)[:50]}")
    print(f"\n共录入 {total} 条点时财务({ok}/{len(a_syms)} 只有年报)。"
          f"A 股质量(ROE)/规模(股本)因子现有数据;成长因子仍限美股(见诚实边界)。")


def main():
    ap = argparse.ArgumentParser(description="A 股财务摄取(点时,东财业绩报表,真实数据,零依赖)")
    ap.add_argument("--path", default=pf.STORE)
    sub = ap.add_subparsers(dest="cmd")
    ig = sub.add_parser("ingest", help="拉单只 A 股年报财务→点时库")
    ig.add_argument("--symbol", required=True)
    ig.add_argument("--limit", type=int, default=6, help="录最近 N 个财年")
    iu = sub.add_parser("ingest-universe", help="真实工作 universe 的 A 股批量")
    iu.add_argument("--limit", type=int, default=6)
    args = ap.parse_args()
    {"ingest": cmd_ingest, "ingest-universe": cmd_ingest_universe}.get(
        args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
