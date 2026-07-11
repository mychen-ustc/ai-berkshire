#!/usr/bin/env python3
"""交易账本 / 持仓重建工具（事实源，零外部依赖，仅 stdlib）。

从一份交易流水 CSV 重建任意历史日期的：持仓（股数/均价/成本）、
各币种现金、已实现盈亏。给定价格快照可进一步算市值/未实现盈亏/权重，
并读取 config/investment-policy.json 检查集中度是否越限。

设计原则（对齐 docs/TODO 的 P0-2 事实源）：
  - 只此一个事实源：风险/业绩/归因都应从本工具重建的持仓出发。
  - 任意历史日可重放：--as-of 截断到某日。
  - 隐私：真实账本只存本地（data/portfolio/transactions.csv 已 gitignore），
    仓库内只提供 transactions.example.csv 合成示例。

账本 CSV 列（表头必须一致）：
  date,action,symbol,market,currency,quantity,price,fee,amount,note

action 取值与语义：
  DEPOSIT   现金流入：cash[currency] += amount
  WITHDRAW  现金流出：cash[currency] -= amount
  BUY       买入：cost=quantity*price+fee；cash[currency]-=cost；持仓+，均价更新
  SELL      卖出：proceeds=quantity*price-fee；cash[currency]+=proceeds；已实现盈亏累计
  DIV       股息：cash[currency] += amount（并计入该 symbol 的累计分红）
  FEE       费用：cash[currency] -= (amount 或 fee)
  SPLIT     拆股：price 列填拆股比(如 2 表示 1拆2)；持仓股数×比，均价÷比
  FX        换汇：symbol=来源币种, quantity=来源金额, currency=目标币种, amount=目标金额

用法：
  python3 tools/ledger.py positions --ledger data/portfolio/transactions.example.csv
  python3 tools/ledger.py positions --ledger <账本> --as-of 2026-07-04 \
      --prices <价格.csv> --base HKD --fx "USD=7.80" --policy config/investment-policy.json
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_EVEN

Q2 = Decimal("0.01")


def D(x):
    """安全转 Decimal（空/None→0），经 str() 避免浮点污染。"""
    if x is None:
        return Decimal("0")
    s = str(x).strip()
    if s == "":
        return Decimal("0")
    return Decimal(s)


def load_ledger(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # 按日期稳定排序（同日按文件原序）
    return sorted(rows, key=lambda r: r.get("date", ""))


class Position:
    __slots__ = ("symbol", "market", "currency", "qty", "cost_basis", "dividends")

    def __init__(self, symbol, market, currency):
        self.symbol = symbol
        self.market = market
        self.currency = currency
        self.qty = Decimal("0")          # 持股数
        self.cost_basis = Decimal("0")   # 持仓总成本（含费用）
        self.dividends = Decimal("0")    # 累计分红

    @property
    def avg_cost(self):
        return (self.cost_basis / self.qty) if self.qty else Decimal("0")


def rebuild(rows, as_of=None):
    """回放交易，返回 (positions, cash, realized_pnl, warnings)。"""
    positions = {}
    cash = defaultdict(lambda: Decimal("0"))
    realized = Decimal("0")
    warnings = []

    def pos(symbol, market, currency):
        if symbol not in positions:
            positions[symbol] = Position(symbol, market, currency)
        return positions[symbol]

    for i, r in enumerate(rows):
        date = r.get("date", "").strip()
        if as_of and date > as_of:
            continue
        action = r.get("action", "").strip().upper()
        sym = r.get("symbol", "").strip()
        mkt = r.get("market", "").strip()
        ccy = r.get("currency", "").strip()
        qty = D(r.get("quantity"))
        price = D(r.get("price"))
        fee = D(r.get("fee"))
        amount = D(r.get("amount"))
        loc = f"[第{i + 2}行 {date} {action} {sym}]"

        if action == "DEPOSIT":
            cash[ccy] += amount
        elif action == "WITHDRAW":
            cash[ccy] -= amount
        elif action == "FEE":
            cash[ccy] -= (amount if amount else fee)
        elif action == "BUY":
            cost = qty * price + fee
            cash[ccy] -= cost
            p = pos(sym, mkt, ccy)
            p.qty += qty
            p.cost_basis += cost
        elif action == "SELL":
            p = pos(sym, mkt, ccy)
            if qty > p.qty:
                warnings.append(f"{loc} 卖出 {qty} 超过持仓 {p.qty}")
            avg = p.avg_cost
            proceeds = qty * price - fee
            cash[ccy] += proceeds
            realized += (price - avg) * qty - fee
            p.cost_basis -= avg * qty
            p.qty -= qty
            if p.qty <= 0:
                p.qty = Decimal("0")
                p.cost_basis = Decimal("0")
        elif action == "DIV":
            cash[ccy] += amount
            pos(sym, mkt, ccy).dividends += amount
        elif action == "SPLIT":
            p = pos(sym, mkt, ccy)
            ratio = price  # 1拆N，price 列填 N
            if ratio > 0:
                p.qty *= ratio  # 成本不变，均价自然÷ratio
        elif action == "FX":
            # symbol=来源币种, quantity=来源金额, currency=目标币种, amount=目标金额
            cash[sym] -= qty
            cash[ccy] += amount
        else:
            warnings.append(f"{loc} 未知 action: {action!r}")

    for ccy, bal in cash.items():
        if bal < 0:
            warnings.append(f"现金为负：{ccy} {bal}")

    live = {s: p for s, p in positions.items() if p.qty > 0}
    return live, dict(cash), realized, warnings


def load_prices(path):
    prices = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            prices[r["symbol"].strip()] = D(r["price"])
    return prices


def parse_fx(spec, base):
    """'USD=7.80,CNY=1.09' → {'USD':7.80,...,base:1}。rate = 1 单位该币种 = ? 基础币种。"""
    fx = {base: Decimal("1")}
    if spec:
        for part in spec.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                fx[k.strip()] = D(v)
    return fx


def main():
    ap = argparse.ArgumentParser(description="交易账本 / 持仓重建（事实源，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("positions", help="重建持仓/现金/成本；给价格则算市值/权重并查 IPS")
    p.add_argument("--ledger", required=True)
    p.add_argument("--as-of", help="截断到该日期(YYYY-MM-DD)")
    p.add_argument("--prices", help="价格快照 CSV: symbol,price")
    p.add_argument("--base", default="HKD", help="计算权重/NAV 的基础币种")
    p.add_argument("--fx", help="汇率到基础币种，如 'USD=7.80,CNY=1.09'")
    p.add_argument("--policy", default="config/investment-policy.json", help="IPS 约束 JSON")
    args = ap.parse_args()

    if args.cmd != "positions":
        ap.print_help()
        return

    rows = load_ledger(args.ledger)
    positions, cash, realized, warnings = rebuild(rows, args.as_of)

    print("=" * 68)
    print(f"持仓重建（事实源） · 账本: {os.path.basename(args.ledger)}"
          + (f" · 截至 {args.as_of}" if args.as_of else ""))
    print("=" * 68)

    prices = load_prices(args.prices) if args.prices else {}
    fx = parse_fx(args.fx, args.base)

    header = f"  {'标的':<14}{'市场':<7}{'币种':<5}{'股数':>10}{'均价':>12}{'成本':>14}"
    if prices:
        header += f"{'现价':>10}{'市值':>14}{'未实现':>12}{'权重%':>8}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    nav_base = Decimal("0")   # 组合市值(基础币种)
    mv_rows = []
    for sym, p in sorted(positions.items()):
        line = (f"  {sym:<14}{p.market:<7}{p.currency:<5}"
                f"{p.qty:>10}{p.avg_cost.quantize(Q2):>12}{p.cost_basis.quantize(Q2):>14}")
        if prices:
            pr = prices.get(sym)
            if pr is None:
                line += f"{'—':>10}{'(缺价)':>14}"
                mv_rows.append((sym, None))
            else:
                mv = p.qty * pr
                unreal = mv - p.cost_basis
                rate = fx.get(p.currency)
                mv_base = mv * rate if rate is not None else None
                if mv_base is not None:
                    nav_base += mv_base
                mv_rows.append((sym, mv_base))
                line += (f"{pr.quantize(Q2):>10}{mv.quantize(Q2):>14}"
                         f"{unreal.quantize(Q2):>12}")
        print(line)

    # 现金
    print()
    for ccy, bal in sorted(cash.items()):
        print(f"  现金 {ccy}: {bal.quantize(Q2)}")
        rate = fx.get(ccy)
        if prices and rate is not None:
            nav_base += bal * rate

    print(f"\n  已实现盈亏(未跨币种换算): {realized.quantize(Q2)}")

    # 权重 + IPS 检查
    if prices and nav_base > 0:
        print(f"\n  组合 NAV（{args.base}，含现金）: {nav_base.quantize(Q2)}")
        # 单一标的权重
        policy = None
        if args.policy and os.path.exists(args.policy):
            with open(args.policy, encoding="utf-8") as f:
                policy = json.load(f)
        single_cap = None
        if policy:
            single_cap = policy.get("position_limits", {}).get("single_name_max_pct")
        # 重新打印权重列（需要基础币种市值）
        print("\n  权重（按基础币种市值 / NAV）:")
        weights = []
        for sym, mv_base in mv_rows:
            if mv_base is None:
                continue
            w = (mv_base / nav_base * 100)
            weights.append((sym, w))
            flag = ""
            if single_cap is not None and w > Decimal(str(single_cap)):
                flag = f"  ⚠️ 超单一标的上限 {single_cap}%"
            print(f"    {sym:<14}{w.quantize(Q2):>7}%{flag}")
        cash_base = sum((cash[c] * fx[c]) for c in cash if c in fx)
        print(f"    {'现金':<14}{(cash_base / nav_base * 100).quantize(Q2):>7}%")
        # top3 检查
        if policy and weights:
            top3 = sum(sorted((w for _, w in weights), reverse=True)[:3])
            cap3 = policy.get("position_limits", {}).get("top3_max_pct")
            msg = ""
            if cap3 is not None and top3 > Decimal(str(cap3)):
                msg = f"  ⚠️ 超前三大上限 {cap3}%"
            print(f"    前三大合计: {top3.quantize(Q2)}%{msg}")
        if single_cap is not None:
            print(f"\n  （IPS 约束来自 {args.policy}，status={policy.get('status') if policy else '—'}）")

    if warnings:
        print("\n  ⚠️ 校验警告：")
        for w in warnings:
            print(f"    - {w}")
    else:
        print("\n  ✅ 无校验警告")


if __name__ == "__main__":
    main()
