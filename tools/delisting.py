#!/usr/bin/env python3
"""退市/失败样本库（T1-3，防幸存者偏差，零外部依赖）。

`backtest.py` 已诚实标注："股票池是当前还活着的标的，未纳入退市/失败样本 → 结果
偏乐观"。本库补这块地基：记录退市/破产/私有化/并购消失的标的及其**退市日、原因、
终值收益**，从而能构造"**某历史时点当时在市**的股票池"(含后来死掉的)——回测才不会
只在赢家里挑赢家。

为什么重要：幸存者偏差让所有回测系统性高估。真实世界里会退市/归零的标的，若从
历史池中消失，策略就像"只在活到今天的公司里选股"——这在当时是不可知的。

隐私：真实退市库存 data/delisting.jsonl(gitignore)；结构见 .example。

用法：
  # 记录退市(破产归零)
  python3 tools/delisting.py record --symbol LEHMQ --name "雷曼" --listed 1994-05-01 \
      --delisted 2008-09-15 --reason bankruptcy --terminal-return -1.0
  # 被并购消失(通常正收益)
  python3 tools/delisting.py record --symbol ATVI --name "动视暴雪" --listed 1993-01-01 \
      --delisted 2023-10-13 --reason merger --terminal-return 0.0
  # 构造某历史时点的"当时在市"股票池(含后来退市的)
  python3 tools/delisting.py universe-as-of --date 2008-06-01 --candidates "AAPL,LEHMQ,ATVI"
  # 幸存者偏差体检:给定当前池,看历史上还有哪些当时在市但已死
  python3 tools/delisting.py survivorship-check --date 2008-06-01
"""
import argparse
import json
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "data", "delisting.jsonl")
REASONS = ("bankruptcy", "merger", "acquisition", "private", "regulatory", "other")


# --------------------------------------------------------------------------
# 纯函数（可测）
# --------------------------------------------------------------------------
def _d(s):
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def was_listed(record, as_of_date):
    """该退市记录代表的标的，在 as_of_date 是否仍在市。纯函数。"""
    d = _d(as_of_date) if isinstance(as_of_date, str) else as_of_date
    if record.get("listed") and _d(record["listed"]) > d:
        return False                                 # 当时还没上市
    if record.get("delisted") and _d(record["delisted"]) < d:
        return False                                 # 当时已退市
    return True


def universe_as_of(records, candidates, as_of_date):
    """从候选池里，返回 as_of_date **当时在市**的标的(含后来退市的)。
    candidates 中不在退市库的，默认视为在市(存续至今)。纯函数。"""
    by_sym = {r["symbol"]: r for r in records}
    live = []
    for s in candidates:
        r = by_sym.get(s)
        if r is None or was_listed(r, as_of_date):
            live.append(s)
    return live


def delisted_between(records, start_date, end_date):
    """区间内退市的标的(回测中会"死掉"的样本)。纯函数。"""
    s, e = _d(start_date), _d(end_date)
    return [r for r in records if r.get("delisted") and s <= _d(r["delisted"]) <= e]


def survivorship_gap(records, as_of_date):
    """as_of_date 当时在市、但如今已退市的标的——这些正是幸存者偏差漏掉的样本。纯函数。"""
    return [r for r in records if was_listed(r, as_of_date) and r.get("delisted")]


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
    rec = {"symbol": args.symbol, "name": args.name or "", "listed": args.listed,
           "delisted": args.delisted, "reason": args.reason,
           "terminal_return": args.terminal_return}
    append(rec, args.path)
    tr = args.terminal_return
    print(f"✅ 已记录退市样本：{args.symbol} {args.name or ''} "
          f"({args.listed or '?'} → {args.delisted}, {args.reason}"
          + (f", 终值收益 {tr:+.0%}" if tr is not None else "") + ")")
    if args.reason == "bankruptcy" and (tr is None or tr > -0.9):
        print(f"  ⚠️ 破产退市终值收益通常≈-100%，请确认 --terminal-return(当前 {tr})。")


def cmd_universe_as_of(args):
    recs = load(args.path)
    cands = [s.strip() for s in args.candidates.split(",") if s.strip()]
    live = universe_as_of(recs, cands, args.date)
    dead = [s for s in cands if s not in live]
    print("=" * 60)
    print(f"当时在市股票池 · {args.date}（候选 {len(cands)} → 在市 {len(live)}）")
    print("=" * 60)
    print(f"  ✅ 当时在市: {', '.join(live) if live else '(无)'}")
    if dead:
        print(f"  ⬜ 当时不在市(未上市/已退市): {', '.join(dead)}")
    print(f"\n  → 回测应只在「当时在市」池里选股，且保留后来退市的样本(否则幸存者偏差高估)。")


def cmd_survivorship_check(args):
    recs = load(args.path)
    gap = survivorship_gap(recs, args.date)
    print("=" * 64)
    print(f"幸存者偏差体检 · {args.date}")
    print("=" * 64)
    if not gap:
        print(f"  退市库中无「{args.date}在市但如今已退市」的样本(库为空或需补录)。")
    else:
        print(f"  ⚠️ {args.date} 当时在市、如今已退市的样本 {len(gap)} 个——")
        print(f"     只用'活到今天'的股票池回测，会系统性漏掉这些，高估策略表现：")
        for r in sorted(gap, key=lambda x: x.get("delisted", "")):
            tr = r.get("terminal_return")
            print(f"     · {r['symbol']:<8}{r.get('name',''):<10} 退市 {r['delisted']} "
                  f"({r['reason']}" + (f", 终值 {tr:+.0%}" if tr is not None else "") + ")")
    print(f"\n  ⚠️ 诚实边界：本库靠手工/增量补录，非全市场退市数据库；覆盖不全时体检偏乐观。")


def cmd_list(args):
    recs = load(args.path)
    print(f"退市/失败样本库（{len(recs)} 条）")
    for r in sorted(recs, key=lambda x: x.get("delisted", "")):
        tr = r.get("terminal_return")
        print(f"  {r['symbol']:<8}{r.get('name',''):<12} {r.get('listed','?')}→{r['delisted']} "
              f"{r['reason']:<11}" + (f"终值{tr:+.0%}" if tr is not None else ""))


def main():
    ap = argparse.ArgumentParser(description="退市/失败样本库(T1-3，防幸存者偏差，零依赖)")
    ap.add_argument("--path", default=STORE)
    sub = ap.add_subparsers(dest="cmd")

    rc = sub.add_parser("record", help="记录一个退市/失败样本")
    rc.add_argument("--symbol", required=True)
    rc.add_argument("--name", default="")
    rc.add_argument("--listed", help="上市日 YYYY-MM-DD")
    rc.add_argument("--delisted", required=True, help="退市日 YYYY-MM-DD")
    rc.add_argument("--reason", required=True, choices=REASONS)
    rc.add_argument("--terminal-return", dest="terminal_return", type=float, help="退市终值收益(破产≈-1.0)")

    uas = sub.add_parser("universe-as-of", help="构造某时点当时在市的股票池")
    uas.add_argument("--date", required=True)
    uas.add_argument("--candidates", required=True)

    sc = sub.add_parser("survivorship-check", help="幸存者偏差体检")
    sc.add_argument("--date", required=True)

    sub.add_parser("list", help="列出")

    args = ap.parse_args()
    {"record": cmd_record, "universe-as-of": cmd_universe_as_of,
     "survivorship-check": cmd_survivorship_check,
     "list": cmd_list}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
