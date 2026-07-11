#!/usr/bin/env python3
"""事件驱动/特殊机会：并购套利计算（P1，零外部依赖）。

并购套利年化收益与期望值——这是与大盘低相关、确定性较高的 alpha 来源。
其余特殊机会（分拆/困境反转/私有化/指数调入调出/回购增持）以框架为主，
见 skills/special-situations.md。

用法：
  python3 tools/special_situations.py merger-arb --current 95 --deal 100 --days 90
  python3 tools/special_situations.py merger-arb --current 95 --deal 100 --days 90 --downside 80 --prob 0.9
"""
import argparse


def merger_arb(current, deal, days, downside=None, prob=None):
    """并购套利：毛利差 + 年化 + （给破裂价与成交概率时）期望值。"""
    gross = deal / current - 1
    annualized = (deal / current) ** (365.0 / days) - 1 if days > 0 else None
    out = {"gross_spread": gross, "annualized": annualized}
    if downside is not None and prob is not None:
        ev = prob * deal + (1 - prob) * downside
        out.update({"expected_value": ev, "ev_return": ev / current - 1,
                    "ev_annualized": (ev / current) ** (365.0 / days) - 1 if days > 0 else None,
                    "loss_if_broken": downside / current - 1})
    return out


def cmd_merger(args):
    r = merger_arb(args.current, args.deal, args.days, args.downside, args.prob)
    print("=" * 58)
    print(f"并购套利 · 现价 {args.current} → 对价 {args.deal} · {args.days} 天")
    print("=" * 58)
    print(f"  毛利差:      {r['gross_spread']:+.2%}")
    print(f"  年化(复利):  {r['annualized']:+.1%}" if r['annualized'] is not None else "")
    if "expected_value" in r:
        print(f"  破裂下行:    {r['loss_if_broken']:+.1%}（跌到 {args.downside}）")
        print(f"  成交概率:    {args.prob:.0%}")
        print(f"  期望值:      {r['expected_value']:.2f}（期望收益 {r['ev_return']:+.2%}）")
        print(f"  期望年化:    {r['ev_annualized']:+.1%}")
        odds = (args.deal - args.current) / (args.current - args.downside) if args.current > args.downside else None
        if odds:
            print(f"  非对称赔率:  {odds:.2f}:1（上行/下行）→ 可接 position_sizing 定仓")
    print("\n  提示：套利收益的敌人是【交易告吹】——务必评估监管/融资/股东投票风险。")


def main():
    ap = argparse.ArgumentParser(description="事件驱动：并购套利（P1，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    m = sub.add_parser("merger-arb", help="并购套利年化/期望值")
    m.add_argument("--current", type=float, required=True, help="标的现价")
    m.add_argument("--deal", type=float, required=True, help="收购对价")
    m.add_argument("--days", type=int, required=True, help="预计成交天数")
    m.add_argument("--downside", type=float, help="交易告吹的下行价")
    m.add_argument("--prob", type=float, help="成交概率 0-1")
    args = ap.parse_args()
    if args.cmd == "merger-arb":
        cmd_merger(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
