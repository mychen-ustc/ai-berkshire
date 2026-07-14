#!/usr/bin/env python3
"""交易成本分析（T3-1，TCA，零外部依赖）。

rebalance.py 只有线性成本(bps×换手)——那只是佣金/税。真实交易成本还有两块被它忽略：
  1) 价差成本 —— 买付卖价、卖收买价，每笔付半个价差(小盘/冷门更宽)。
  2) 冲击成本 —— 大额单会推动价格(平方根定律:成本∝√(订单/ADV))，是大额/小盘的主成本。
另外事后要算 **执行落差(implementation shortfall)**：决策价 vs 实际成交均价的差——
衡量"想做的"和"做到的"之间被市场吃掉多少。

为什么重要：rebalance 报"成本$57"可能只算了佣金；一笔占 ADV 30% 的小盘单，冲击成本
可能是佣金的十几倍。TCA 让你在下单前就知道"这笔能不能这么大、要不要拆单"。

用法：
  # 预交易:估一笔单的全成本(佣金+价差+冲击)
  python3 tools/tca.py estimate --notional 500000 --adv 3000000 --daily-vol 0.02 --spread-bps 5
  # 一篮子调仓的 TCA 汇总(CSV: symbol,notional,adv,daily_vol,spread_bps)
  python3 tools/tca.py basket --file orders.csv
  # 事后:执行落差
  python3 tools/tca.py shortfall --decision-price 100 --exec-price 100.4 --qty 5000 --side buy
"""
import argparse
import csv
import math
import os


# --------------------------------------------------------------------------
# 纯函数（可测）——成本模型
# --------------------------------------------------------------------------
def spread_cost_bps(spread_bps):
    """价差成本 = 半个买卖价差(每笔付一半)。纯函数。"""
    return 0.5 * spread_bps


def impact_cost_bps(order_notional, adv_notional, daily_vol, coef=1.0):
    """冲击成本(bps) = coef × 日波动 × √(参与率)，参与率=订单额/ADV。平方根冲击定律。
    daily_vol 为小数(0.02=2%)。纯函数。"""
    if adv_notional <= 0 or order_notional <= 0:
        return 0.0
    participation = order_notional / adv_notional
    return coef * daily_vol * math.sqrt(participation) * 10000.0


def total_cost(order_notional, adv_notional, daily_vol, spread_bps, commission_bps=1.0, coef=1.0):
    """总成本分解 → {commission_bps, spread_bps, impact_bps, total_bps, total_cash}。纯函数。"""
    imp = impact_cost_bps(order_notional, adv_notional, daily_vol, coef)
    spr = spread_cost_bps(spread_bps)
    tot_bps = commission_bps + spr + imp
    return {"commission_bps": commission_bps, "spread_bps": spr, "impact_bps": imp,
            "total_bps": tot_bps, "total_cash": tot_bps / 10000.0 * order_notional,
            "participation": (order_notional / adv_notional) if adv_notional else None}


def implementation_shortfall(decision_price, exec_price, qty, side):
    """执行落差：相对决策价，实际成交多付/少收的钱。买入 exec>decision 为亏损。纯函数。"""
    sign = 1 if side.lower() == "buy" else -1
    slip_per_share = sign * (exec_price - decision_price)
    return {"slippage_per_share": slip_per_share, "slippage_bps": (slip_per_share / decision_price * 10000) if decision_price else 0.0,
            "total_cash": slip_per_share * qty}


def days_to_execute(order_notional, adv_notional, max_participation=0.2):
    """按最大参与率(默认20% ADV)，这笔单需几天完成(拆单)。纯函数。"""
    if adv_notional <= 0:
        return float("inf")
    return (order_notional / adv_notional) / max_participation


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
def cmd_estimate(args):
    c = total_cost(args.notional, args.adv, args.daily_vol, args.spread_bps,
                   args.commission_bps, args.coef)
    print("=" * 60)
    print(f"预交易成本估计 · 订单 ${args.notional:,.0f} · ADV ${args.adv:,.0f}")
    print("=" * 60)
    part = c["participation"]
    print(f"  参与率(订单/ADV): {part:.1%}" + ("  🔴 过大(>20%)" if part and part > 0.2 else
                                              ("  🟡 偏大(>10%)" if part and part > 0.1 else "  🟢 可接受")))
    print(f"\n  成本分解:")
    print(f"    佣金/税   {c['commission_bps']:>6.1f} bps")
    print(f"    价差      {c['spread_bps']:>6.1f} bps  (半价差)")
    print(f"    冲击      {c['impact_bps']:>6.1f} bps  (平方根定律)")
    print(f"    {'─'*30}")
    print(f"    合计      {c['total_bps']:>6.1f} bps  =  ${c['total_cash']:,.0f}")
    d = days_to_execute(args.notional, args.adv)
    if part and part > 0.2:
        print(f"\n  ⚠️ 参与率过大——建议拆单：按20%ADV上限约需 {d:.1f} 天完成，"
              f"或冲击成本会显著吃掉收益。")
    print(f"\n  ⚠️ 冲击系数(coef)与价差为估计;真实成本依赖流动性/时段/波动,大额小盘尤甚。")


def cmd_basket(args):
    rows = []
    with open(args.file, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    print("=" * 74)
    print(f"一篮子 TCA · {os.path.basename(args.file)}")
    print("=" * 74)
    print(f"  {'标的':<10}{'订单额':>12}{'参与率':>8}{'佣金':>7}{'价差':>7}{'冲击':>7}{'合计bps':>8}")
    tot_cash = 0.0
    for r in rows:
        notl = float(r["notional"]); adv = float(r["adv"])
        dv = float(r.get("daily_vol", 0.02)); sp = float(r.get("spread_bps", 5))
        c = total_cost(notl, adv, dv, sp, args.commission_bps, args.coef)
        tot_cash += c["total_cash"]
        part = c["participation"]
        flag = "🔴" if part and part > 0.2 else ("🟡" if part and part > 0.1 else "")
        print(f"  {r['symbol']:<10}{notl:>12,.0f}{(part or 0):>7.0%}{flag}"
              f"{c['commission_bps']:>6.1f}{c['spread_bps']:>7.1f}{c['impact_bps']:>7.1f}{c['total_bps']:>8.1f}")
    print(f"  {'─'*68}")
    print(f"  一篮子总交易成本(估计): ${tot_cash:,.0f}")
    print(f"\n  ⚠️ 红/黄标=参与率过大/偏大,冲击成本主导,考虑拆单或减小订单。")


def cmd_shortfall(args):
    s = implementation_shortfall(args.decision_price, args.exec_price, args.qty, args.side)
    print("=" * 56)
    print(f"执行落差(implementation shortfall) · {args.side.upper()}")
    print("=" * 56)
    print(f"  决策价 {args.decision_price} · 成交均价 {args.exec_price} · {args.qty:.0f} 股")
    print(f"  每股滑点: {s['slippage_per_share']:+.4f}  ({s['slippage_bps']:+.1f} bps)")
    print(f"  总落差:   ${s['total_cash']:+,.0f}  " +
          ("(负=多付/被吃)" if s["total_cash"] > 0 else "(正=占了便宜)"))
    print(f"\n  → 想做的(决策价) vs 做到的(成交价)之间的差,长期累积侵蚀收益,须纳入策略成本。")


def main():
    ap = argparse.ArgumentParser(description="交易成本分析 TCA(T3-1，佣金+价差+冲击+执行落差，零依赖)")
    ap.add_argument("--coef", type=float, default=1.0, help="冲击系数(默认1.0)")
    ap.add_argument("--commission-bps", dest="commission_bps", type=float, default=1.0)
    sub = ap.add_subparsers(dest="cmd")

    es = sub.add_parser("estimate", help="预交易:单笔全成本")
    es.add_argument("--notional", type=float, required=True, help="订单金额")
    es.add_argument("--adv", type=float, required=True, help="日均成交额 ADV")
    es.add_argument("--daily-vol", dest="daily_vol", type=float, default=0.02, help="日波动(小数)")
    es.add_argument("--spread-bps", dest="spread_bps", type=float, default=5.0)

    ba = sub.add_parser("basket", help="一篮子调仓 TCA(CSV)")
    ba.add_argument("--file", required=True, help="CSV: symbol,notional,adv,daily_vol,spread_bps")

    sf = sub.add_parser("shortfall", help="事后:执行落差")
    sf.add_argument("--decision-price", dest="decision_price", type=float, required=True)
    sf.add_argument("--exec-price", dest="exec_price", type=float, required=True)
    sf.add_argument("--qty", type=float, required=True)
    sf.add_argument("--side", required=True, choices=["buy", "sell"])

    args = ap.parse_args()
    {"estimate": cmd_estimate, "basket": cmd_basket, "shortfall": cmd_shortfall}.get(
        args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
