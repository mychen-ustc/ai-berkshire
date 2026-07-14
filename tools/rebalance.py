#!/usr/bin/env python3
"""再平衡引擎（零外部依赖，仅 stdlib）。P4-11：把手写调仓脚本产品化。

给当前账本 + 目标权重 → 计算买卖股数、多币种换汇提示、交易成本估计，生成可执行调仓 CSV。
目标权重之外的持仓自动清仓(target=0)。

用法：
  python3 tools/rebalance.py --from-ledger data/portfolio/transactions.csv \
      --target "VOO=21,BRK.B=15,GOOGL=14,KO=13,AAPL=9,AXP=9,COST=6,603986=4" \
      --fx "USD=1,HKD=0.128,CNY=0.14" --cost-bps 10 --out reports/private/transactions.rebalance-新.csv
诚实边界：按实时报价折算股数，实际成交价会滑动；跨币种买卖需另加换汇行(工具会提示缺口)；
成本为线性估计。调仓是决策与纪律的执行，仍须人工确认(税务/流动性/择时)。
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portfolio_risk as pr  # noqa: E402
import datalayer as dl  # noqa: E402
import ledger  # noqa: E402

MKT_CN = {"A": "A股", "HK": "港股", "US": "美股"}


# --------------------------------------------------------------------------
# 纯逻辑：由现状 + 目标 → 订单
# --------------------------------------------------------------------------
def compute_orders(current_qty, prices, ccy, fx, target_pct, total_base):
    """→ [订单]。current_qty/prices/ccy 按符号；target_pct 占总资产%；缺席目标=清仓。纯函数。"""
    orders = []
    for s in sorted(set(current_qty) | set(target_pct)):
        price = prices.get(s)
        if not price:
            continue
        price_base = price * fx.get(ccy.get(s, "USD"), 1.0)
        tgt = target_pct.get(s, 0.0)
        tgt_qty = round(total_base * tgt / 100.0 / price_base) if price_base else 0
        cur = current_qty.get(s, 0.0)
        d = tgt_qty - cur
        if abs(d) < 1e-9:
            continue
        orders.append({"symbol": s, "action": "BUY" if d > 0 else "SELL", "shares": abs(d),
                       "price": round(price, 3), "ccy": ccy.get(s, "USD"), "target_pct": tgt,
                       "delta_base": round(d * price_base, 2)})
    return orders


def fx_gaps(orders, cash_base_by_ccy, fx):
    """估各币种净现金流，提示需换汇的缺口(base 币种)。纯函数。"""
    flow = dict(cash_base_by_ccy)
    for o in orders:
        # 买入消耗该币种现金、卖出补充(base 计价)
        flow[o["ccy"]] = flow.get(o["ccy"], 0.0) + (-o["delta_base"])
    return {c: round(v, 2) for c, v in flow.items()}


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def run(args):
    fx = pr._parse_fx(args.fx)
    pos, cash, _, _ = ledger.rebuild(ledger.load_ledger(args.from_ledger))
    target = {}
    for part in args.target.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            target[dl.detect(k.strip())["symbol"]] = float(v)

    current_qty, prices, ccy = {}, {}, {}
    for s, p in pos.items():
        if p.qty > 0:
            current_qty[dl.detect(s)["symbol"]] = float(p.qty)
    for s in set(current_qty) | set(target):
        try:
            q = dl.fetch_quote(s, cross=False)
            prices[s] = q.get("price")
            ccy[s] = q.get("currency") or dl.detect(s)["currency"]
        except Exception:  # noqa: BLE001
            pass

    total_base = sum(current_qty.get(s, 0) * prices[s] * fx.get(ccy.get(s, "USD"), 1.0)
                     for s in current_qty if prices.get(s)) + sum(float(v) * fx.get(k, 1.0) for k, v in cash.items())
    orders = compute_orders(current_qty, prices, ccy, fx, target, total_base)

    print("=" * 66)
    print(f"再平衡 · {os.path.basename(args.from_ledger)} · 总资产 {total_base:,.0f} (base)")
    print("=" * 66)
    print(f"  {'标的':<10}{'动作':<6}{'股数变化':>16}{'现价':>12}{'目标%':>7}")
    for o in sorted(orders, key=lambda x: -abs(x["delta_base"])):
        cur = current_qty.get(o["symbol"], 0)
        nxt = cur + (o["shares"] if o["action"] == "BUY" else -o["shares"])
        tag = "🔴清仓" if o["target_pct"] == 0 else ""
        print(f"  {o['symbol']:<10}{o['action']:<6}{cur:>7.0f}→{nxt:<7.0f}{o['price']:>12}{o['target_pct']:>6.0f}% {tag}")
    turnover = sum(abs(o["delta_base"]) for o in orders)
    cost = turnover * args.cost_bps / 10000.0
    print(f"\n  换手额 {turnover:,.0f} · 估计成本({args.cost_bps}bps) {cost:,.0f} · 笔数 {len(orders)}")
    cash_base = {c: float(v) * fx.get(c, 1.0) for c, v in cash.items()}
    gaps = fx_gaps(orders, cash_base, fx)
    neg = {c: v for c, v in gaps.items() if v < -1}
    if neg:
        print("  ⚠️ 换汇提示（负=该币种现金不足，需从其它币种换入）: "
              + " · ".join(f"{c} {v:+,.0f}" for c, v in neg.items()))

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        shutil.copyfile(args.from_ledger, args.out)
        with open(args.out, "a", encoding="utf-8") as f:
            for o in orders:
                mkt = MKT_CN.get(dl.detect(o["symbol"])["market"], "")
                note = "再平衡清仓" if o["target_pct"] == 0 else "再平衡调仓"
                f.write(f"2026-07-14,{o['action']},{o['symbol']},{mkt},{o['ccy']},{o['shares']},{o['price']},0,,{note}\n")
        print(f"  已生成调仓 CSV → {args.out}（{len(orders)} 笔；跨币种买卖请按上方提示补 FX 行）")
    print("\n  ⚠️ 报价折算股数、实际成交会滑动；跨币种需补换汇行；成本线性估计。调仓须人工确认(税/流动性/择时)。")


def main():
    ap = argparse.ArgumentParser(description="再平衡引擎：现状+目标→订单+成本+换汇提示+CSV（零依赖）")
    ap.add_argument("--from-ledger", required=True)
    ap.add_argument("--target", required=True, help='目标权重(占总资产%) "VOO=21,AAPL=9,..."；缺席=清仓')
    ap.add_argument("--fx", default="USD=1,HKD=0.128,CNY=0.14")
    ap.add_argument("--cost-bps", type=float, default=10.0)
    ap.add_argument("--out", help="导出调仓 CSV(追加到账本)")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
