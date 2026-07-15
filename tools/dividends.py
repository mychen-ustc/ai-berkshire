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
import math
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


def allocate(cash, weights, prices, whole=False):
    """按权重(在有价标的间重新归一)把 cash 分配为(碎)股。
    → {sym:{weight,alloc,price,shares}}。whole=True 则向下取整为整股。纯函数。"""
    avail = {s: weights[s] for s in weights if prices.get(s)}
    tot = sum(avail.values()) or 1.0
    out = {}
    for s, w in avail.items():
        alloc = cash * w / tot
        raw = alloc / prices[s] if prices[s] else 0
        # 向下截断(整股或4位碎股)，确保不超额→现金不为负
        sh = float(int(raw)) if whole else math.floor(raw * 10000) / 10000
        out[s] = {"weight": w, "alloc": round(alloc, 2), "price": prices[s], "shares": sh}
    return out


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


def cmd_reinvest(args):
    """把可用现金(默认USD分红)按目标权重碎股再投资(DRIP)。"""
    rows = L.load_ledger(args.from_ledger)
    _, cash, _, _ = L.rebuild(rows)
    ccy = args.ccy
    avail = float(cash.get(ccy, 0))
    if avail <= 0:
        print(f"无可再投资 {ccy} 现金(={avail})。")
        return
    tgt = {}
    for part in args.target.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            tgt[dl.detect(k.strip())["symbol"]] = float(v)
    # 仅在与现金同币种的标的间部署(异币种需FX，且A股100股起板，故排除)
    usd_tgt, prices, dropped = {}, {}, []
    for s, w in tgt.items():
        info = dl.detect(s)
        if info["currency"] != ccy:
            dropped.append(s)
            continue
        try:
            prices[s] = dl.fetch_quote(s, cross=False).get("price")
            usd_tgt[s] = w
        except Exception:  # noqa: BLE001
            dropped.append(s)
    alloc = allocate(avail, usd_tgt, prices, whole=args.whole)
    print("=" * 62)
    print(f"分红再投资(DRIP) · 可用 {ccy} ${avail:.2f} · 按 v10 权重{'(整股)' if args.whole else '(碎股)'}")
    print("=" * 62)
    print(f"  {'标的':<7}{'目标%':>6}{'分配$':>9}{'现价':>10}{'买入股数':>11}")
    deployed = 0.0
    for s in sorted(alloc, key=lambda x: -alloc[x]["weight"]):
        a = alloc[s]
        deployed += a["shares"] * a["price"]
        print(f"  {s:<7}{a['weight']:>5.0f}%{a['alloc']:>9.2f}{a['price']:>10.2f}{a['shares']:>11.4f}")
    print(f"  部署 ${deployed:.2f} · 残留现金 ${avail - deployed:.2f}")
    if dropped:
        print(f"  ⓘ 排除(异币种/A股100股起板，需FX单独处理): {', '.join(dropped)}")
    if not args.apply:
        print(f"\n  → 加 --apply 追加 {len(alloc)} 条 BUY 到账本(先备份)。")
        return
    priv = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "private")
    os.makedirs(priv, exist_ok=True)
    bak = os.path.join(priv, f"transactions.pre-drip-backup-{datetime.now().strftime('%Y%m%d')}.csv")
    shutil.copyfile(args.from_ledger, bak)
    today = datetime.now().strftime("%Y-%m-%d")
    with open(args.from_ledger, "a", encoding="utf-8") as f:
        for s, a in alloc.items():
            if a["shares"] <= 0:
                continue
            f.write(f"{today},BUY,{s},美股,{ccy},{a['shares']},{a['price']},0,,分红再投资DRIP-v10权重\n")
    print(f"\n✅ 已追加 {sum(1 for a in alloc.values() if a['shares'] > 0)} 条 BUY(备份 → {os.path.basename(bak)})")


def main():
    ap = argparse.ArgumentParser(description="分红入账+再投资:真实分红→账本DIV,可按权重DRIP(零依赖)")
    ap.add_argument("--tax", type=float, default=0.0, help="股息预扣税率(如0.1协定/0.3)")
    sub = ap.add_subparsers(dest="cmd")
    for c in ("preview", "apply"):
        p = sub.add_parser(c)
        p.add_argument("--from-ledger", required=True)
        p.add_argument("--tax", type=float, default=0.0)
    ri = sub.add_parser("reinvest", help="按目标权重把分红现金DRIP再投资")
    ri.add_argument("--from-ledger", required=True)
    ri.add_argument("--target", required=True, help='v10目标权重 "GOOGL=16,MTUM=14,..."')
    ri.add_argument("--ccy", default="USD", help="再投资币种(默认USD)")
    ri.add_argument("--whole", action="store_true", help="整股(默认碎股)")
    ri.add_argument("--apply", action="store_true", help="写入账本(默认仅预览)")
    args = ap.parse_args()
    {"preview": cmd_preview, "apply": cmd_apply, "reinvest": cmd_reinvest}.get(
        args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
