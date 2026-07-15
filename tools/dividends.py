#!/usr/bin/env python3
"""分红入账（零外部依赖）。

回放账本，对每只持仓、每个除息日，按**当时实际持股数 × 真实每股分红**(Yahoo events=div)
计算收到的分红，记为账本 DIV 交易(现金入账 + 计入该 symbol 累计分红)。

为什么需要：分析层(adjclose/前复权)已假设分红再投资，但**真实账本只记买卖、没记分红现金**。
本工具用**真实分红数据**(非估算)把这块补上，让账本现金/累计收益反映实际收到的股息。

诚实边界：
  · 仅美股(Yahoo 分红事件)；A股/港股(兆易)分红需东财数据，本版本未接，另行处理。
  · 记的是**除息日 × 当时持股**的应得分红；实际到账有派息日延迟、且外国投资者美股股息
    有预扣税(~30%/协定~10%)——本工具记**税前毛股息**(可 --tax 扣预扣税)。
  · 默认记为现金 DIV(不自动再投资)；DRIP 再投资需另行下买单。

用法：
  python3 tools/dividends.py preview --from-ledger data/portfolio/transactions.csv   # 预览应记分红
  python3 tools/dividends.py apply --from-ledger data/portfolio/transactions.csv [--tax 0.1]  # 追加DIV(先备份)
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402
import ledger as L  # noqa: E402


# --------------------------------------------------------------------------
# 纯函数（可测）
# --------------------------------------------------------------------------
def filter_calendar(divs, start, end):
    """[(ex_date, dps)] 过滤到 [start,end] 闭区间并排序。纯函数。"""
    return sorted((d, a) for d, a in divs if start <= d <= end)


def div_cash(shares, dps, tax=0.0):
    """应收分红现金 = 持股 × 每股 × (1−预扣税)。纯函数。"""
    return shares * dps * (1 - tax)


# --------------------------------------------------------------------------
# 取数
# --------------------------------------------------------------------------
def fetch_dividends(symbol):
    """Yahoo events=div → [(ex_date 'YYYY-MM-DD', dps)]。仅美股。"""
    info = dl.detect(symbol)
    if info["market"] != "US":
        return []
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{info['yahoo']}"
           f"?interval=1d&range=2y&events=div")   # 1d 才有准确除息日(1mo 会吸附到月初)
    try:
        d = json.loads(dl._curl(url))
        divs = d["chart"]["result"][0].get("events", {}).get("dividends", {})
    except Exception:  # noqa: BLE001
        return []
    out = []
    for k, v in divs.items():
        dt = datetime.fromtimestamp(int(k), tz=timezone.utc).strftime("%Y-%m-%d")
        out.append((dt, float(v["amount"])))
    return out


# --------------------------------------------------------------------------
# 编排：回放账本 → 每除息日应得分红
# --------------------------------------------------------------------------
def compute(rows, tax=0.0):
    """→ (records[list], per_symbol[dict], total_by_ccy[dict])。
    records: 每笔 {date, symbol, market, currency, shares, dps, cash}。"""
    # 账本日期范围 + 持仓标的
    dates = [r["date"] for r in rows if r.get("date")]
    start = min(dates) if dates else "2000-01-01"
    today = datetime.now().strftime("%Y-%m-%d")
    pos_now, _, _, _ = L.rebuild(rows)
    held_syms = {s for s, p in pos_now.items()}
    # 也纳入历史持有过但已清仓的(整段持有期都可能有分红)
    all_syms = {r["symbol"] for r in rows if r.get("action") in ("BUY", "SELL")}

    records = []
    for sym in sorted(all_syms):
        info = dl.detect(sym)
        if info["market"] != "US":
            continue
        cal = filter_calendar(fetch_dividends(sym), start, today)
        for ex, dps in cal:
            pos, _, _, _ = L.rebuild(rows, as_of=ex)
            p = pos.get(sym)
            sh = float(p.qty) if p and p.qty > 0 else 0.0
            if sh <= 0:
                continue
            cash = div_cash(sh, dps, tax)
            records.append({"date": ex, "symbol": sym, "market": info["market"],
                            "currency": info["currency"], "shares": sh, "dps": dps,
                            "cash": round(cash, 2)})
    per_sym, by_ccy = {}, {}
    for r in records:
        per_sym[r["symbol"]] = per_sym.get(r["symbol"], 0.0) + r["cash"]
        by_ccy[r["currency"]] = by_ccy.get(r["currency"], 0.0) + r["cash"]
    return records, per_sym, by_ccy


MKT_CN = {"US": "美股", "A": "A股", "HK": "港股"}


def cmd_preview(args):
    rows = L.load_ledger(args.from_ledger)
    records, per_sym, by_ccy = compute(rows, args.tax)
    print("=" * 66)
    print(f"分红入账预览 · {os.path.basename(args.from_ledger)} · "
          f"{'税前毛股息' if args.tax == 0 else f'扣预扣税{args.tax:.0%}后'}")
    print("=" * 66)
    print(f"  共 {len(records)} 笔除息(仅美股;A/港股分红未接)")
    print(f"\n  按标的汇总:")
    for s in sorted(per_sym, key=lambda x: -per_sym[x]):
        n = sum(1 for r in records if r["symbol"] == s)
        print(f"    {s:<8} {n:>2}笔 · 累计分红 ${per_sym[s]:>9,.2f}")
    print(f"\n  合计: " + " · ".join(f"{c} ${v:,.2f}" for c, v in by_ccy.items()))
    print(f"\n  最近 8 笔:")
    for r in sorted(records, key=lambda x: x["date"])[-8:]:
        print(f"    {r['date']} {r['symbol']:<7} {r['shares']:>5.0f}股 × ${r['dps']} = ${r['cash']:,.2f}")
    print(f"\n  → apply 将追加 {len(records)} 条 DIV 交易到账本(先自动备份)。")
    if args.tax == 0:
        print(f"  ⚠️ 当前记税前毛股息;外国投资者美股股息有预扣税,可加 --tax 0.1(协定)或 0.3。")


def cmd_apply(args):
    rows = L.load_ledger(args.from_ledger)
    records, per_sym, by_ccy = compute(rows, args.tax)
    if not records:
        print("无可入账分红。")
        return
    # 备份到 reports/private/(gitignore，含真实持仓)
    priv = os.path.join(L.ROOT if hasattr(L, "ROOT") else
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "private")
    os.makedirs(priv, exist_ok=True)
    bak = os.path.join(priv, f"transactions.pre-div-backup-{datetime.now().strftime('%Y%m%d')}.csv")
    shutil.copyfile(args.from_ledger, bak)
    # 追加 DIV 行
    with open(args.from_ledger, "a", encoding="utf-8") as f:
        for r in sorted(records, key=lambda x: x["date"]):
            note = "分红入账" + (f"(扣税{args.tax:.0%})" if args.tax else "(税前)")
            f.write(f"{r['date']},DIV,{r['symbol']},{MKT_CN.get(r['market'], '')},{r['currency']},"
                    f"{r['shares']:.0f},{r['dps']},0,{r['cash']},{note}\n")
    print(f"✅ 已追加 {len(records)} 条 DIV 到账本(备份 → {os.path.basename(bak)})")
    print(f"   累计分红: " + " · ".join(f"{c} ${v:,.2f}" for c, v in by_ccy.items()))
    print(f"   用 `ledger.py positions` 重建可见现金已含分红。")


def main():
    ap = argparse.ArgumentParser(description="分红入账:真实分红×时点持股→账本DIV交易(零依赖)")
    ap.add_argument("--tax", type=float, default=0.0, help="股息预扣税率(如0.1协定/0.3)")
    sub = ap.add_subparsers(dest="cmd")
    for c in ("preview", "apply"):
        p = sub.add_parser(c)
        p.add_argument("--from-ledger", required=True)
        p.add_argument("--tax", type=float, default=0.0)
    args = ap.parse_args()
    {"preview": cmd_preview, "apply": cmd_apply}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
