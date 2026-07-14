#!/usr/bin/env python3
"""公司行动引擎（T1-2，零外部依赖）。

security_master 有 PIT 快照(标的属性)，但缺**公司行动的复权与代码接续**。本引擎
记录拆股/合股/分红/并购/更名/退市，并给出：
  1) 价格复权因子——跨拆股/分红的历史收益才准确(不复权则拆股当日"暴跌50%"是假信号)
  2) 股数/成本基准调整——你的持仓在拆股后股数×2、成本÷2
  3) 代码接续——更名/并购后老代码→新代码的映射

为什么重要：不复权的历史价格会污染动量/回撤/回测(拆股被误读为暴跌、分红被漏计)。
这是 datalayer 前复权之外、**对自己持仓与公司行动做正确账务**的一层。

隐私：真实公司行动存 data/corporate_actions.jsonl(gitignore)；结构见 .example。

用法：
  # 拆股 1拆4(每1股变4股)
  python3 tools/corporate_actions.py record --symbol NVDA --type split --date 2024-06-10 --ratio 4
  # 现金分红(每股)
  python3 tools/corporate_actions.py record --symbol KO --type dividend --date 2026-06-15 --amount 0.51
  # 更名/代码接续
  python3 tools/corporate_actions.py record --symbol FB --type rename --date 2022-06-09 --new-symbol META
  # 某标的在某历史价格上的复权因子(把行动前价格调到可比口径)
  python3 tools/corporate_actions.py factor --symbol NVDA --date 2024-01-01
  # 持仓经公司行动后的股数/成本
  python3 tools/corporate_actions.py adjust-position --symbol NVDA --shares 100 --cost 500 --from 2024-01-01
"""
import argparse
import json
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "data", "corporate_actions.jsonl")
TYPES = ("split", "dividend", "rename", "merger", "delist", "spinoff")


# --------------------------------------------------------------------------
# 纯函数（可测）——复权与接续
# --------------------------------------------------------------------------
def _d(s):
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def price_adjust_factor(actions, symbol, ref_date, price_ref=None):
    """把 ref_date(含)之前的价格，调整到"最新口径"的乘法因子。
    拆股 r:1(1股拆r股) → 之前价格 ×(1/r)；现金分红 d → 之前价格 ×(1 − d/price_ref)(近似前复权)。
    只计 ref_date 之后发生的行动(之前的已反映在当时价格)。纯函数。"""
    d0 = _d(ref_date) if isinstance(ref_date, str) else ref_date
    f = 1.0
    for a in actions:
        if a["symbol"] != symbol:
            continue
        ad = _d(a["date"])
        if ad <= d0:
            continue
        if a["type"] == "split":
            f *= 1.0 / float(a["ratio"])
        elif a["type"] == "dividend" and price_ref:
            f *= max(0.0, 1.0 - float(a["amount"]) / float(price_ref))
    return f


def share_adjust_factor(actions, symbol, from_date):
    """持仓股数随拆股变化的乘法因子(from_date 之后的拆股)。1拆4 → 股数×4。纯函数。"""
    d0 = _d(from_date) if isinstance(from_date, str) else from_date
    f = 1.0
    for a in actions:
        if a["symbol"] == symbol and a["type"] == "split" and _d(a["date"]) > d0:
            f *= float(a["ratio"])
    return f


def resolve_symbol(actions, symbol, as_of_date=None):
    """跟随 rename/merger 链，返回某时点后的现行代码。纯函数。"""
    cur = symbol
    chain = sorted([a for a in actions if a["type"] in ("rename", "merger") and a.get("new_symbol")],
                   key=lambda a: a["date"])
    d0 = _d(as_of_date) if as_of_date else None
    changed = True
    while changed:
        changed = False
        for a in chain:
            if a["symbol"] == cur and (d0 is None or _d(a["date"]) <= d0):
                cur = a["new_symbol"]
                changed = True
    return cur


def total_dividends(actions, symbol, start_date, end_date):
    """区间内每股现金分红合计(用于总回报口径)。纯函数。"""
    s, e = _d(start_date), _d(end_date)
    return sum(float(a["amount"]) for a in actions
              if a["symbol"] == symbol and a["type"] == "dividend"
              and a.get("amount") and s <= _d(a["date"]) <= e)


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
    rec = {"symbol": args.symbol, "type": args.type, "date": args.date}
    if args.type == "split":
        if not args.ratio:
            raise SystemExit("split 需 --ratio(如 4 表示 1拆4)")
        rec["ratio"] = args.ratio
    elif args.type == "dividend":
        if args.amount is None:
            raise SystemExit("dividend 需 --amount(每股现金)")
        rec["amount"] = args.amount
    elif args.type in ("rename", "merger"):
        if not args.new_symbol:
            raise SystemExit(f"{args.type} 需 --new-symbol")
        rec["new_symbol"] = args.new_symbol
    if args.note:
        rec["note"] = args.note
    append(rec, args.path)
    print(f"✅ 已记录公司行动：{args.symbol} {args.type} @ {args.date} "
          + (f"ratio={args.ratio}" if args.ratio else "")
          + (f"amount={args.amount}" if args.amount is not None else "")
          + (f"→{args.new_symbol}" if args.new_symbol else ""))


def cmd_factor(args):
    acts = load(args.path)
    f = price_adjust_factor(acts, args.symbol, args.date, args.price_ref)
    sf = share_adjust_factor(acts, args.symbol, args.date)
    print("=" * 58)
    print(f"复权因子 · {args.symbol} · {args.date} 之后的公司行动")
    print("=" * 58)
    print(f"  价格复权因子: ×{f:.4f}  (把 {args.date} 的价格调到最新口径)")
    print(f"  股数调整因子: ×{sf:.4f}  (持仓股数随拆股变化)")
    later = [a for a in acts if a["symbol"] == args.symbol and _d(a["date"]) > _d(args.date)]
    if later:
        print(f"\n  期间行动({len(later)}):")
        for a in sorted(later, key=lambda x: x["date"]):
            det = (f"1拆{a['ratio']}" if a["type"] == "split" else
                   f"分红{a.get('amount')}/股" if a["type"] == "dividend" else
                   f"→{a.get('new_symbol','')}")
            print(f"    · {a['date']} {a['type']} {det}")
    else:
        print(f"\n  {args.date} 之后无公司行动，价格口径不变。")
    if not args.price_ref and any(a["type"] == "dividend" for a in later):
        print(f"  ⚠️ 含分红但未提供 --price-ref，分红复权未计入(需当时价格做前复权近似)。")


def cmd_adjust_position(args):
    acts = load(args.path)
    sf = share_adjust_factor(acts, args.symbol, args.frm)
    new_shares = args.shares * sf
    new_cost = (args.cost / sf) if sf else args.cost
    cur = resolve_symbol(acts, args.symbol)
    print("=" * 58)
    print(f"持仓调整 · {args.symbol}" + (f" (现行代码 {cur})" if cur != args.symbol else ""))
    print("=" * 58)
    print(f"  原始: {args.shares:.0f} 股 @ 成本 {args.cost}")
    print(f"  经拆股调整(×{sf:.2f}): {new_shares:.0f} 股 @ 成本 {new_cost:.4f}")
    print(f"  (总市值/总成本不变，仅每股口径变化)")


def cmd_list(args):
    acts = [a for a in load(args.path) if not args.symbol or a["symbol"] == args.symbol]
    print(f"公司行动（{len(acts)} 条）")
    for a in sorted(acts, key=lambda x: (x["symbol"], x["date"])):
        det = (f"1拆{a['ratio']}" if a["type"] == "split" else
               f"分红{a.get('amount')}/股" if a["type"] == "dividend" else
               f"→{a.get('new_symbol','')}" if a.get("new_symbol") else "")
        print(f"  {a['symbol']:<8} {a['date']} {a['type']:<9} {det}")


def main():
    ap = argparse.ArgumentParser(description="公司行动引擎(T1-2，复权/接续，零依赖)")
    ap.add_argument("--path", default=STORE)
    sub = ap.add_subparsers(dest="cmd")

    rc = sub.add_parser("record", help="记录一次公司行动")
    rc.add_argument("--symbol", required=True)
    rc.add_argument("--type", required=True, choices=TYPES)
    rc.add_argument("--date", required=True)
    rc.add_argument("--ratio", type=float, help="split: 1拆N 的 N")
    rc.add_argument("--amount", type=float, help="dividend: 每股现金")
    rc.add_argument("--new-symbol", dest="new_symbol", help="rename/merger 后代码")
    rc.add_argument("--note", default="")

    fa = sub.add_parser("factor", help="某历史日之后的价格/股数复权因子")
    fa.add_argument("--symbol", required=True)
    fa.add_argument("--date", required=True)
    fa.add_argument("--price-ref", dest="price_ref", type=float, help="分红复权需当时价格")

    ap2 = sub.add_parser("adjust-position", help="持仓经拆股后的股数/成本")
    ap2.add_argument("--symbol", required=True)
    ap2.add_argument("--shares", type=float, required=True)
    ap2.add_argument("--cost", type=float, required=True)
    ap2.add_argument("--from", dest="frm", required=True, help="买入日 YYYY-MM-DD")

    li = sub.add_parser("list", help="列出")
    li.add_argument("--symbol")

    args = ap.parse_args()
    {"record": cmd_record, "factor": cmd_factor, "adjust-position": cmd_adjust_position,
     "list": cmd_list}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
