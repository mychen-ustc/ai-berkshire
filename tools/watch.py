#!/usr/bin/env python3
"""持仓监控与告警（P1，零外部依赖）。

巡检持仓：从账本取成本、数据层取实时价，按每标的触发器规则产出告警
（止损/止盈/价位突破/单日异动），并可展示未来 N 天的催化剂/财报日历。
可配合 /loop 或 cron 定时运行——把 thesis-tracker 的"手动红线"变成主动巡检。

用法：
  python3 tools/watch.py check --ledger data/portfolio/transactions.example.csv \
      --config config/watch.example.json
  python3 tools/watch.py calendar --file data/portfolio/catalysts.example.csv --within 30
"""
import argparse
import csv
import json
import os
from datetime import datetime


def evaluate_triggers(entry, current, triggers, change_pct=None):
    """纯函数：给成本价/现价/触发器 → 告警列表 [(level, msg)]。level: info/warn/alert。"""
    alerts = []
    if entry and current and triggers.get("stop_loss_pct") is not None:
        dd = (current / entry - 1) * 100
        if dd <= -abs(triggers["stop_loss_pct"]):
            alerts.append(("alert", f"止损触发：较成本 {dd:+.1f}% ≤ -{abs(triggers['stop_loss_pct'])}%"))
    if entry and current and triggers.get("take_profit_pct") is not None:
        up = (current / entry - 1) * 100
        if up >= triggers["take_profit_pct"]:
            alerts.append(("warn", f"止盈触发：较成本 {up:+.1f}% ≥ {triggers['take_profit_pct']}%（考虑减仓/重估）"))
    if triggers.get("price_below") is not None and current is not None and current < triggers["price_below"]:
        alerts.append(("alert", f"跌破价位 {triggers['price_below']}（现价 {current}）"))
    if triggers.get("price_above") is not None and current is not None and current > triggers["price_above"]:
        alerts.append(("warn", f"突破价位 {triggers['price_above']}（现价 {current}）"))
    if triggers.get("day_move_pct") is not None and change_pct is not None and abs(change_pct) >= triggers["day_move_pct"]:
        alerts.append(("warn", f"单日异动 {change_pct:+.1f}%（阈值 ±{triggers['day_move_pct']}%）→ 建议 /news-pulse 归因"))
    return alerts


def cmd_check(args):
    import datalayer as dl
    import ledger as ldg
    cfg = json.load(open(args.config, encoding="utf-8")) if args.config and os.path.exists(args.config) else {}
    default = cfg.get("_default", {})
    pos, _, _, _ = ldg.rebuild(ldg.load_ledger(args.ledger))
    held = {s: p for s, p in pos.items() if p.qty > 0}
    print("=" * 60)
    print(f"持仓监控 · {len(held)} 只 · {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 60)
    total_alerts = 0
    for s, p in held.items():
        trig = {**default, **cfg.get(s, {})}
        q = dl.fetch_quote(s, cross=False)
        entry = float(p.avg_cost)
        alerts = evaluate_triggers(entry, q["price"], trig, q.get("change_pct"))
        icon = "🔴" if any(l == "alert" for l, _ in alerts) else ("🟡" if alerts else "🟢")
        print(f"  {icon} {s:<10} 现价 {q['price']} {q['currency']} (成本 {entry:.2f}, "
              f"{(q['price'] / entry - 1) * 100:+.1f}%)")
        for level, msg in alerts:
            print(f"       {'🔴' if level == 'alert' else '🟡'} {msg}")
            total_alerts += 1
    print(f"\n  共 {total_alerts} 条告警" + ("（无触发器命中，一切正常）" if total_alerts == 0 else ""))


def cmd_calendar(args):
    today = datetime.strptime(args.today, "%Y-%m-%d") if args.today else datetime.now()
    rows = []
    with open(args.file, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = datetime.strptime(r["date"].strip(), "%Y-%m-%d")
            days = (d - today).days
            if 0 <= days <= args.within:
                rows.append((days, r["date"], r.get("symbol", ""), r.get("event", "")))
    print(f"未来 {args.within} 天催化剂/财报日历（{len(rows)} 项）")
    for days, date, sym, ev in sorted(rows):
        print(f"  T+{days:<3} {date} {sym:<10} {ev}")


def main():
    ap = argparse.ArgumentParser(description="持仓监控与告警（P1，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check", help="巡检持仓触发器")
    c.add_argument("--ledger", required=True)
    c.add_argument("--config", help="触发器配置 JSON（{symbol:{stop_loss_pct,...}, _default:{...}}）")
    cal = sub.add_parser("calendar", help="催化剂/财报日历")
    cal.add_argument("--file", required=True, help="CSV: date,symbol,event")
    cal.add_argument("--within", type=int, default=30)
    cal.add_argument("--today", help="YYYY-MM-DD（默认今天）")
    args = ap.parse_args()
    if args.cmd == "check":
        cmd_check(args)
    elif args.cmd == "calendar":
        cmd_calendar(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
