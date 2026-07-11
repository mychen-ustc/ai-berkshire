#!/usr/bin/env python3
"""卖出纪律：系统化卖出信号（P1，零外部依赖）。

研究界普遍重买入、轻卖出。本工具把"何时该走"规则化，按优先级评估：
  1) 论点证伪 → 卖    2) 止损触发 → 卖    3) 显著超内在价值/达目标 → 减/卖
  4) 预期回报 < 无风险利率(机会成本) → 卖    5) 存在明显更优机会 → 换仓减仓
与 thesis-tracker(红线) / dcf(内在价值) / performance(预期回报) 联动。

用法：
  python3 tools/sell_discipline.py eval --entry 100 --current 130 --fair-value 100 \
      --stop-loss 25 --expected-return 0.03 --risk-free 0.04
  python3 tools/sell_discipline.py eval --entry 100 --current 60 --stop-loss 20 --thesis-broken
"""
import argparse

_SEVERITY = {"SELL": 3, "TRIM": 2, "HOLD": 1}


def sell_verdict(entry=None, current=None, fair_value=None, target=None, stop_loss_pct=None,
                 thesis_broken=False, expected_return=None, risk_free=None,
                 better_opp_return=None, opp_threshold=0.05):
    """返回 (verdict, reasons[])。verdict 取所有命中信号里最强者（SELL>TRIM>HOLD）。"""
    signals = []  # (verdict, reason)
    if thesis_broken:
        signals.append(("SELL", "论点已证伪：核心假设被推翻，无论盈亏都应离场"))
    if entry and current and stop_loss_pct is not None:
        dd = (current / entry - 1) * 100
        if dd <= -abs(stop_loss_pct):
            signals.append(("SELL", f"止损触发：较成本 {dd:+.1f}% ≤ -{abs(stop_loss_pct)}%"))
    ref = fair_value if fair_value is not None else target
    if ref and current is not None:
        if current >= ref * 1.2:
            signals.append(("SELL", f"显著超内在价值/目标：现价 {current} ≥ {ref}×1.2（马克斯：钟摆偏贪婪）"))
        elif current >= ref:
            signals.append(("TRIM", f"达到内在价值/目标：现价 {current} ≥ {ref}，考虑分批减仓"))
    if expected_return is not None and risk_free is not None and expected_return < risk_free:
        signals.append(("SELL", f"机会成本：预期回报 {expected_return:.1%} < 无风险利率 {risk_free:.1%}，不如持币"))
    if (better_opp_return is not None and expected_return is not None
            and better_opp_return - expected_return > opp_threshold):
        signals.append(("TRIM", f"换仓：更优机会预期 {better_opp_return:.1%} 显著高于当前 {expected_return:.1%}"))
    if not signals:
        return "HOLD", ["无卖出信号：论点未破、未触止损、未超内在价值、回报仍优于现金"]
    verdict = max((v for v, _ in signals), key=lambda v: _SEVERITY[v])
    return verdict, [r for _, r in signals]


def cmd_eval(args):
    verdict, reasons = sell_verdict(
        entry=args.entry, current=args.current, fair_value=args.fair_value, target=args.target,
        stop_loss_pct=args.stop_loss, thesis_broken=args.thesis_broken,
        expected_return=args.expected_return, risk_free=args.risk_free,
        better_opp_return=args.better_opp, opp_threshold=args.opp_threshold)
    icon = {"SELL": "🔴", "TRIM": "🟡", "HOLD": "🟢"}[verdict]
    print("=" * 58)
    print(f"卖出纪律评估 → {icon} {verdict}")
    print("=" * 58)
    for r in reasons:
        print(f"  • {r}")
    print("\n  纪律：卖出应基于规则而非情绪；论点证伪与止损优先于一切侥幸。")


def main():
    ap = argparse.ArgumentParser(description="卖出纪律：系统化卖出信号（P1，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    e = sub.add_parser("eval", help="评估一只持仓是否该卖")
    e.add_argument("--entry", type=float)
    e.add_argument("--current", type=float)
    e.add_argument("--fair-value", type=float, dest="fair_value", help="内在价值(如 dcf.py 得)")
    e.add_argument("--target", type=float, help="目标价(fair-value 缺失时用)")
    e.add_argument("--stop-loss", type=float, dest="stop_loss", help="止损百分比(如 20)")
    e.add_argument("--thesis-broken", action="store_true", dest="thesis_broken", help="论点证伪(thesis-tracker 红线)")
    e.add_argument("--expected-return", type=float, dest="expected_return", help="当前预期年化回报 0-1")
    e.add_argument("--risk-free", type=float, dest="risk_free", help="无风险利率 0-1")
    e.add_argument("--better-opp", type=float, dest="better_opp", help="更优机会预期回报 0-1")
    e.add_argument("--opp-threshold", type=float, default=0.05, dest="opp_threshold")
    args = ap.parse_args()
    if args.cmd == "eval":
        cmd_eval(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
