#!/usr/bin/env python3
"""事件/催化剂日历（零外部依赖，仅 stdlib）。P3 运营骨架。

把"未来会发生什么"排成一条时间线,驱动监控与复盘节奏:
  · 美股财报日(Finnhub calendar/earnings,含 EPS/营收预期)——前瞻。
  · 手动催化剂(从 watchlist 各标的 next_catalyst 汇总,或命令行传入)。
  · A股近期公告事件(可选,复用 news_engine)。
合并排序 → 未来 N 天时间线,临近(≤14天)高亮。

诚实边界:美股财报日来自 Finnhub(需 key);A股前瞻财报日暂无稳定免费源
(用 news_engine 补近期已发生事件);手动催化剂靠人工维护。

用法:
  python3 tools/calendar.py earnings AAPL,GOOGL,NVDA
  python3 tools/calendar.py upcoming --symbols "AAPL,GOOGL" --days 60     # 财报日 + watchlist 催化剂
  python3 tools/calendar.py upcoming --from-watchlist --days 90
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402
import keys  # noqa: E402


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _days_between(d1, d2):
    try:
        a = datetime.strptime(d1[:10], "%Y-%m-%d")
        b = datetime.strptime(d2[:10], "%Y-%m-%d")
        return (b - a).days
    except ValueError:
        return None


def fetch_earnings(symbol, days=120):
    """Finnhub 财报日历 → 该标的未来财报事件。需 key;仅美股。"""
    key = keys.get_key("FINNHUB_API_KEY")
    if not key:
        return []
    today = _today()
    end = datetime.strptime(today, "%Y-%m-%d")
    to = f"{end.year + (1 if end.month + 4 > 12 else 0)}-{(end.month + 4 - 1) % 12 + 1:02d}-{end.day:02d}"
    url = f"https://finnhub.io/api/v1/calendar/earnings?from={today}&to={to}&symbol={symbol.upper()}&token={key}"
    try:
        arr = (json.loads(dl._curl(url)).get("earningsCalendar")) or []
    except Exception:  # noqa: BLE001
        return []
    out = []
    for e in arr:
        out.append({"date": e.get("date"), "symbol": symbol.upper(), "type": "财报",
                    "detail": f"Q{e.get('quarter')} {e.get('hour', '')}（EPS预期 {e.get('epsEstimate')}）"})
    return out


def build_timeline(events, days, as_of=None):
    """合并 + 过滤未来 days 天 + 排序 + 标临近。"""
    as_of = as_of or _today()
    fut = []
    for e in events:
        dd = _days_between(as_of, e.get("date", ""))
        if dd is not None and 0 <= dd <= days:
            e["in_days"] = dd
            e["imminent"] = dd <= 14
            fut.append(e)
    return sorted(fut, key=lambda x: x["date"])


def from_watchlist_catalysts():
    """从 watchlist 状态机汇总 next_catalyst(格式建议 'YYYY-MM-DD 描述')。"""
    import watchlist as wl
    out = []
    for e in wl.load()["entries"]:
        c = e.get("next_catalyst")
        if c and len(c) >= 10 and c[:4].isdigit():
            out.append({"date": c[:10], "symbol": e["symbol"], "type": "催化剂", "detail": c[10:].strip() or "—"})
    return out


def render(timeline, as_of):
    if not timeline:
        return f"  (未来窗口内无已知事件；截至 {as_of})"
    L = []
    for e in timeline:
        flag = "🔴临近" if e.get("imminent") else "     "
        L.append(f"  {e['date']} {flag} [{e['type']}] {e['symbol']}  {e.get('detail', '')}  (+{e['in_days']}天)")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="事件/催化剂日历（美股财报 Finnhub + 手动催化剂，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    e = sub.add_parser("earnings", help="美股财报日(Finnhub)")
    e.add_argument("symbols"); e.add_argument("--json", action="store_true")
    u = sub.add_parser("upcoming", help="未来催化剂时间线（财报 + watchlist 催化剂）")
    u.add_argument("--symbols"); u.add_argument("--from-watchlist", action="store_true")
    u.add_argument("--days", type=int, default=90); u.add_argument("--as-of"); u.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.cmd == "earnings":
        syms = [s.strip() for s in args.symbols.split(",") if s.strip()]
        ev = []
        for s in syms:
            ev += fetch_earnings(s)
        tl = build_timeline(ev, 400, args.as_of if hasattr(args, "as_of") else None)
        print(json.dumps(tl, ensure_ascii=False, indent=2) if args.json else render(tl, _today()))
    elif args.cmd == "upcoming":
        ev = []
        if args.from_watchlist:
            ev += from_watchlist_catalysts()
            syms = [e["symbol"] for e in ev]
        else:
            syms = [s.strip() for s in (args.symbols or "").split(",") if s.strip()]
        for s in syms:
            if dl.detect(s)["market"] == "US":
                ev += fetch_earnings(s)
        as_of = args.as_of or _today()
        tl = build_timeline(ev, args.days, as_of)
        if args.json:
            print(json.dumps(tl, ensure_ascii=False, indent=2))
        else:
            print(f"未来 {args.days} 天催化剂时间线（截至 {as_of}，🔴=≤14天临近）:")
            print(render(tl, as_of))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
