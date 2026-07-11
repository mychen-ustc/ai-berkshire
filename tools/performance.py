#!/usr/bin/env python3
"""业绩计算（P0-5，零外部依赖，仅 stdlib）。

提供两种口径的收益率（机构标准）：
  - TWR 时间加权收益：剔除出入金影响，衡量"投资能力"（对比基准用它）。
  - MWR 货币加权收益(XIRR)：含出入金时点，衡量"这笔钱的实际年化"。
另有总回报/年化。现金流用 Decimal（货币精度），收益率解用 float。

用法：
  # 货币加权(XIRR)：从账本读出入金 + 期末市值
  python3 tools/performance.py mwr --ledger data/portfolio/transactions.example.csv \
      --currency HKD --terminal-value 400000 --as-of 2026-07-04

  # 时间加权：给净值序列(+可选外部现金流)
  python3 tools/performance.py twr --nav nav.csv [--flows flows.csv]

  # 通用 XIRR：给现金流 CSV(date,amount；投入为负、取回为正)
  python3 tools/performance.py xirr --flows flows.csv
"""
import argparse
import csv
from datetime import datetime
from decimal import Decimal


def _d(s):
    s = (str(s).strip() if s is not None else "")
    return Decimal(s) if s else Decimal("0")


def _date(s):
    return datetime.strptime(str(s).strip(), "%Y-%m-%d")


# ---------------------------------------------------------------------------
# XIRR（货币加权 / 内部收益率）—— 现金流贴现求根
# ---------------------------------------------------------------------------
def xnpv(rate, flows):
    """flows: [(datetime, float_amount)]。以首日为基准贴现，年 = days/365。"""
    t0 = min(d for d, _ in flows)
    return sum(a / (1.0 + rate) ** ((d - t0).days / 365.0) for d, a in flows)


def xirr(flows, lo=-0.9999, hi=10.0, tol=1e-8, max_iter=200):
    """二分法求 XNPV=0 的年化利率。需存在一次符号变化；否则返回 None。"""
    flows = [(d, float(a)) for d, a in flows]
    if len(flows) < 2:
        return None
    f_lo, f_hi = xnpv(lo, flows), xnpv(hi, flows)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if (f_lo > 0) == (f_hi > 0):
        return None  # 无符号变化，无法求解
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = xnpv(mid, flows)
        if abs(f_mid) < tol:
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------
# TWR（时间加权）—— 剔除出入金
# ---------------------------------------------------------------------------
def twr(valuations, flows=None):
    """valuations: [(datetime, nav_float)] 按日期升序；flows: {datetime: 外部净流入}。
    子区间收益(流入视为期末发生): r = (nav_end - flow) / nav_start - 1。
    返回 (twr, annualized)。"""
    flows = flows or {}
    valuations = sorted(valuations, key=lambda x: x[0])
    growth = 1.0
    for i in range(1, len(valuations)):
        (d0, v0), (d1, v1) = valuations[i - 1], valuations[i]
        f = sum(a for dd, a in flows.items() if d0 < dd <= d1)
        if v0 <= 0:
            continue
        growth *= (v1 - f) / v0
    total = growth - 1.0
    days = (valuations[-1][0] - valuations[0][0]).days
    ann = (growth ** (365.0 / days) - 1.0) if days > 0 else 0.0
    return total, ann


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------
def load_flows_csv(path):
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append((_date(r["date"]), Decimal(str(r["amount"]).strip())))
    return out


def load_nav_csv(path):
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append((_date(r["date"]), float(r["nav"])))
    return out


def flows_from_ledger(path, currency, as_of=None):
    """从账本抽外部现金流：DEPOSIT→投入(负)，WITHDRAW→取回(正)。"""
    flows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if as_of and r.get("date", "") > as_of:
                continue
            if currency and r.get("currency", "").strip() != currency:
                continue
            act = r.get("action", "").strip().upper()
            amt = _d(r.get("amount"))
            if act == "DEPOSIT":
                flows.append((_date(r["date"]), -amt))
            elif act == "WITHDRAW":
                flows.append((_date(r["date"]), amt))
    return flows


def main():
    ap = argparse.ArgumentParser(description="业绩计算：TWR / MWR(XIRR) / 总回报（零依赖）")
    sub = ap.add_subparsers(dest="cmd")

    m = sub.add_parser("mwr", help="货币加权(XIRR)：账本出入金 + 期末市值")
    m.add_argument("--ledger", required=True)
    m.add_argument("--currency", required=True, help="现金流币种(单币口径)")
    m.add_argument("--terminal-value", required=True, type=float, help="期末市值(该币种)")
    m.add_argument("--as-of", help="期末日期 YYYY-MM-DD(默认取现金流最后一日)")

    t = sub.add_parser("twr", help="时间加权：净值序列(+可选外部现金流)")
    t.add_argument("--nav", required=True, help="CSV: date,nav")
    t.add_argument("--flows", help="CSV: date,amount(外部净流入)")

    x = sub.add_parser("xirr", help="通用 XIRR：现金流 CSV(date,amount)")
    x.add_argument("--flows", required=True)

    args = ap.parse_args()

    if args.cmd == "mwr":
        flows = flows_from_ledger(args.ledger, args.currency, args.as_of)
        if not flows:
            raise SystemExit("未从账本读到该币种的出入金")
        as_of = _date(args.as_of) if args.as_of else max(d for d, _ in flows)
        flows.append((as_of, Decimal(str(args.terminal_value))))
        r = xirr(flows)
        print("=" * 60)
        print(f"货币加权收益 MWR/XIRR · {args.currency}")
        print("=" * 60)
        for d, a in sorted(flows):
            tag = "投入" if a < 0 else ("期末市值" if (d, a) == (as_of, flows[-1][1]) else "取回")
            print(f"  {d:%Y-%m-%d}  {a:>14}  {tag}")
        print(f"\n  XIRR(年化): {r * 100:.2f}%" if r is not None else "\n  无法求解(现金流无符号变化)")

    elif args.cmd == "twr":
        navs = load_nav_csv(args.nav)
        flows = {d: a for d, a in load_flows_csv(args.flows)} if args.flows else {}
        total, ann = twr(navs, {d: float(a) for d, a in flows.items()})
        print("=" * 60)
        print("时间加权收益 TWR（剔除出入金）")
        print("=" * 60)
        print(f"  区间: {navs[0][0]:%Y-%m-%d} → {navs[-1][0]:%Y-%m-%d}  ({len(navs)} 个估值点)")
        print(f"  累计 TWR: {total * 100:.2f}%")
        print(f"  年化 TWR: {ann * 100:.2f}%")

    elif args.cmd == "xirr":
        flows = load_flows_csv(args.flows)
        r = xirr(flows)
        print(f"XIRR(年化): {r * 100:.2f}%" if r is not None else "无法求解")

    else:
        ap.print_help()


if __name__ == "__main__":
    main()
