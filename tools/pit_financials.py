#!/usr/bin/env python3
"""点时财务库（T1-1，point-in-time，零外部依赖）。

机构级研究的地基：存每期财报**及其可获得日期(available_at/披露日)**，任何历史
查询只返回"当时已知"的数据——**杜绝前视偏差(look-ahead bias)**。

为什么重要：财报有滞后。2025Q4 财报的会计期是 2025-12-31，但可能 2026-02-04 才
披露。一个在 2026-01-15 跑的回测/因子/估值，绝不能"看到"这份还没发布的财报——
否则回测虚高、因子暴露失真、历史估值不可信。这是 backtest/factor_library/comps
做**可信历史研究**的前提(见路线图 T2-3/T2-1)。

与 security_master 的 PIT 快照互补：那个管"标的属性"(行业/上市状态)，这个管
"财务数值"(营收/EPS/净利/净资产/ROE/股本)。

隐私：真实数据存 data/pit_financials.jsonl(gitignore)；结构见 .example。

用法：
  # 录入一期财报(关键是 available_at=披露日,不是会计期末)
  python3 tools/pit_financials.py record --symbol GOOGL --metric revenue \
      --period 2025Q4 --value 96469 --available-at 2026-02-04 --source 10-K --unit 百万美元
  # 点时查询:2026-01-15 时点只能看到那时已披露的(2025Q4未发→被正确排除)
  python3 tools/pit_financials.py asof --symbol GOOGL --metric revenue --date 2026-01-15
  # 某指标的点时序列
  python3 tools/pit_financials.py series --symbol GOOGL --metric eps --date 2026-06-30
  python3 tools/pit_financials.py list --symbol GOOGL
"""
import argparse
import json
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "data", "pit_financials.jsonl")


# --------------------------------------------------------------------------
# 纯函数（可测）——无前视查询语义
# --------------------------------------------------------------------------
def _d(s):
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def _period_key(p):
    """会计期排序键：2025Q4 → (2025,4)；FY2025 → (2025,5 视为年末最后)。"""
    p = p.strip().upper()
    if p.startswith("FY"):
        return (int(p[2:6]), 5)
    if "Q" in p:
        y, q = p.split("Q")
        return (int(y[:4]), int(q))
    return (int(p[:4]), 0)


def visible(records, symbol, metric, as_of_date):
    """→ 截至 as_of_date **已披露**(available_at<=date) 的该(symbol,metric)全部记录。
    这是无前视的核心过滤：available_at 晚于查询日的记录被排除。纯函数。"""
    d = _d(as_of_date) if isinstance(as_of_date, str) else as_of_date
    out = [r for r in records
           if r["symbol"] == symbol and r["metric"] == metric and _d(r["available_at"]) <= d]
    return sorted(out, key=lambda r: (_period_key(r["fiscal_period"]), r["available_at"]))


def as_of(records, symbol, metric, as_of_date):
    """点时最新值：截至 as_of_date 已披露记录里，会计期最新的那条。无则 None。纯函数。"""
    vis = visible(records, symbol, metric, as_of_date)
    return vis[-1] if vis else None


def series_as_of(records, symbol, metric, as_of_date):
    """点时序列：截至 as_of_date 已披露、按会计期去重(取每期最后披露的修订)。纯函数。"""
    vis = visible(records, symbol, metric, as_of_date)
    by_period = {}
    for r in vis:                       # 已按 (period, available_at) 排序 → 后者覆盖(取最新修订)
        by_period[r["fiscal_period"]] = r
    return sorted(by_period.values(), key=lambda r: _period_key(r["fiscal_period"]))


def has_lookahead(records, symbol, metric, as_of_date):
    """诊断：是否存在会计期已过但当时尚未披露的记录(会造成前视的陷阱)。纯函数。"""
    d = _d(as_of_date) if isinstance(as_of_date, str) else as_of_date
    trap = [r for r in records if r["symbol"] == symbol and r["metric"] == metric
            and _d(r["available_at"]) > d]
    return trap


# --------------------------------------------------------------------------
# 存取
# --------------------------------------------------------------------------
def load(path=STORE):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def append(rec, path=STORE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
def cmd_record(args):
    # 校验：available_at 不应早于会计期末太多(常见录入错误：把期末当披露日)
    rec = {"symbol": args.symbol, "metric": args.metric, "fiscal_period": args.period,
           "value": args.value, "available_at": args.available_at,
           "unit": args.unit or "", "source": args.source or ""}
    append(rec, args.path)
    print(f"✅ 已录入 {args.symbol} {args.metric} {args.period} = {args.value}{args.unit or ''} "
          f"(披露日 {args.available_at}, 源 {args.source or '—'})")
    pk = _period_key(args.period)
    # 提醒：披露日通常晚于会计期末
    try:
        pend = datetime(pk[0], min(pk[1], 4) * 3 or 12, 28).date() if pk[1] <= 4 else datetime(pk[0], 12, 31).date()
        if _d(args.available_at) < pend:
            print(f"  ⚠️ 披露日 {args.available_at} 早于会计期末({pend})？请确认 available_at 是"
                  f"'财报发布日'而非'会计期末'——这是点时库防前视的关键。")
    except Exception:  # noqa: BLE001
        pass


def cmd_asof(args):
    recs = load(args.path)
    hit = as_of(recs, args.symbol, args.metric, args.date)
    trap = has_lookahead(recs, args.symbol, args.metric, args.date)
    print("=" * 60)
    print(f"点时查询 · {args.symbol} · {args.metric} · 截至 {args.date}")
    print("=" * 60)
    if hit:
        print(f"  ✅ 当时可见最新值：{hit['value']}{hit.get('unit','')} "
              f"(会计期 {hit['fiscal_period']}, 披露 {hit['available_at']}, 源 {hit.get('source','—')})")
    else:
        print(f"  ⬜ 截至 {args.date} 无任何已披露记录")
    if trap:
        print(f"\n  🛡️ 无前视保护生效：以下 {len(trap)} 条会计期已过但当时未披露，已被正确排除：")
        for r in trap:
            print(f"     · {r['fiscal_period']} = {r['value']}{r.get('unit','')} "
                  f"(实际披露 {r['available_at']} > 查询日 {args.date})")


def cmd_series(args):
    recs = load(args.path)
    s = series_as_of(recs, args.symbol, args.metric, args.date)
    print(f"点时序列 · {args.symbol} · {args.metric} · 截至 {args.date}（{len(s)} 期）")
    for r in s:
        print(f"  {r['fiscal_period']:<8} {r['value']:>14}{r.get('unit','')}  (披露 {r['available_at']})")


def cmd_list(args):
    recs = [r for r in load(args.path) if not args.symbol or r["symbol"] == args.symbol]
    print(f"点时财务库（{len(recs)} 条{'· '+args.symbol if args.symbol else ''}）")
    for r in sorted(recs, key=lambda x: (x["symbol"], x["metric"], _period_key(x["fiscal_period"]))):
        print(f"  {r['symbol']:<8} {r['metric']:<12} {r['fiscal_period']:<8} "
              f"{r['value']:>14}{r.get('unit','')}  披露 {r['available_at']}")


def main():
    ap = argparse.ArgumentParser(description="点时财务库(T1-1，无前视，零依赖)")
    ap.add_argument("--path", default=STORE)
    sub = ap.add_subparsers(dest="cmd")

    rc = sub.add_parser("record", help="录入一期财报(关键:available_at=披露日)")
    rc.add_argument("--symbol", required=True)
    rc.add_argument("--metric", required=True, help="revenue/net_income/eps/book_value/roe/shares...")
    rc.add_argument("--period", required=True, help="2025Q4 / FY2025")
    rc.add_argument("--value", type=float, required=True)
    rc.add_argument("--available-at", dest="available_at", required=True, help="披露日 YYYY-MM-DD")
    rc.add_argument("--unit", default="")
    rc.add_argument("--source", default="")

    ao = sub.add_parser("asof", help="点时查询(无前视)")
    ao.add_argument("--symbol", required=True)
    ao.add_argument("--metric", required=True)
    ao.add_argument("--date", required=True)

    se = sub.add_parser("series", help="点时序列")
    se.add_argument("--symbol", required=True)
    se.add_argument("--metric", required=True)
    se.add_argument("--date", required=True)

    li = sub.add_parser("list", help="列出")
    li.add_argument("--symbol")

    args = ap.parse_args()
    {"record": cmd_record, "asof": cmd_asof, "series": cmd_series,
     "list": cmd_list}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
