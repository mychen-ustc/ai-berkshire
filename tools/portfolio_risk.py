#!/usr/bin/env python3
"""组合风险分析（P0-5，零外部依赖，仅 stdlib）。

给定价格历史（宽表 CSV：date + 每个标的一列）与当前权重，计算：
  年化波动、最大回撤、下行波动、beta/相关性(对基准)、相关性矩阵、
  HHI 集中度/有效持仓数、历史压力（最差单期/最差回撤），
  并读取 config/investment-policy.json 检查集中度是否越限。

统计量用 float（波动/beta/回撤是统计估计，非货币精度；货币精度用 ledger.py 的 Decimal）。
组合口径为"固定权重"——即"当前配置在历史区间的风险画像"，
不依赖完整历史账本（那属 P0-3 数据层）。

用法：
  python3 tools/portfolio_risk.py analyze \
    --prices data/correlation_3stocks_2021-2026.csv \
    --weights "TENCENT=0.47,PDD=0.42,MEITUAN=0.11" \
    --benchmark TENCENT --rf 0.04
"""
import argparse
import csv
import json
import math
import os
import statistics
from datetime import datetime


def load_wide_prices(path):
    """宽表 CSV → (dates[datetime], {symbol: [float]})。"""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        syms = header[1:]
        dates, cols = [], {s: [] for s in syms}
        for row in reader:
            if not row or not row[0].strip():
                continue
            dates.append(datetime.strptime(row[0].strip(), "%Y-%m-%d"))
            for s, v in zip(syms, row[1:]):
                cols[s].append(float(v))
    return dates, cols


def pct_returns(prices):
    return [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]


def periods_per_year(dates):
    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    med = statistics.median(gaps) if gaps else 7
    if med <= 2:
        return 252
    if med <= 10:
        return 52
    if med <= 45:
        return 12
    return 1


def ann_vol(returns, ppy):
    return statistics.pstdev(returns) * math.sqrt(ppy) if len(returns) > 1 else 0.0


def nav_from_returns(returns):
    nav = [1.0]
    for r in returns:
        nav.append(nav[-1] * (1 + r))
    return nav


def max_drawdown(nav):
    peak, mdd = nav[0], 0.0
    for v in nav:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    return mdd  # 负数


def downside_dev(returns, ppy, mar=0.0):
    downs = [min(0.0, r - mar) for r in returns]
    var = sum(d * d for d in downs) / len(downs) if downs else 0.0
    return math.sqrt(var) * math.sqrt(ppy)


def cagr(nav, ppy, n_periods):
    if n_periods <= 0 or nav[0] <= 0:
        return 0.0
    return (nav[-1] / nav[0]) ** (ppy / n_periods) - 1


def beta(port, bench):
    if len(port) < 2:
        return float("nan")
    mb = statistics.fmean(bench)
    var_b = sum((b - mb) ** 2 for b in bench) / len(bench)
    mp = statistics.fmean(port)
    cov = sum((p - mp) * (b - mb) for p, b in zip(port, bench)) / len(port)
    return cov / var_b if var_b else float("nan")


def correlation(a, b):
    if len(a) < 2:
        return float("nan")
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else float("nan")


def hhi(weights):
    return sum(w * w for w in weights)


def parse_weights(spec, available):
    w = {}
    for part in spec.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            if k not in available:
                raise SystemExit(f"权重标的 {k} 不在价格表中；可用: {available}")
            w[k] = float(v)
    total = sum(w.values())
    if total <= 0:
        raise SystemExit("权重之和必须 > 0")
    return {k: v / total for k, v in w.items()}  # 归一化


def analyze(args):
    dates, cols = load_wide_prices(args.prices)
    ppy = {"daily": 252, "weekly": 52, "monthly": 12}.get(args.freq) or periods_per_year(dates)

    weights = (parse_weights(args.weights, list(cols))
               if args.weights else {s: 1 / len(cols) for s in cols})

    rets = {s: pct_returns(cols[s]) for s in weights}
    n = min(len(r) for r in rets.values())
    port = [sum(weights[s] * rets[s][i] for s in weights) for i in range(n)]
    nav = nav_from_returns(port)

    print("=" * 66)
    print(f"组合风险分析 · {os.path.basename(args.prices)} · {len(port)} 期 · 年化因子 {ppy}")
    print("=" * 66)
    print("  权重（归一化）:")
    for s, w in sorted(weights.items(), key=lambda x: -x[1]):
        print(f"    {s:<12}{w * 100:6.2f}%")

    v = ann_vol(port, ppy)
    mdd = max_drawdown(nav)
    dd = downside_dev(port, ppy)
    g = cagr(nav, ppy, n)
    print("\n  组合层指标:")
    print(f"    年化收益(CAGR):  {g * 100:7.2f}%")
    print(f"    年化波动:        {v * 100:7.2f}%")
    print(f"    最大回撤:        {mdd * 100:7.2f}%")
    print(f"    下行波动:        {dd * 100:7.2f}%")
    if args.rf is not None and v > 0:
        print(f"    Sharpe(rf={args.rf}):  {(g - args.rf) / v:7.2f}")
        if dd > 0:
            print(f"    Sortino:         {(g - args.rf) / dd:7.2f}")
    print(f"    最差单期:        {min(port) * 100:7.2f}%")

    if args.benchmark:
        if args.benchmark not in cols:
            raise SystemExit(f"基准 {args.benchmark} 不在价格表中")
        bench = pct_returns(cols[args.benchmark])[:n]
        print(f"\n  对基准 {args.benchmark}:")
        print(f"    Beta:            {beta(port, bench):7.2f}")
        print(f"    相关性:          {correlation(port, bench):7.2f}")

    syms = list(weights)
    if len(syms) > 1:
        print("\n  相关性矩阵:")
        print("    " + "".ljust(12) + "".join(f"{s[:8]:>9}" for s in syms))
        for a in syms:
            line = f"    {a[:12]:<12}"
            for b in syms:
                line += f"{correlation(rets[a][:n], rets[b][:n]):>9.2f}"
            print(line)

    h = hhi([weights[s] for s in weights])
    print("\n  集中度:")
    print(f"    HHI:             {h:7.3f}")
    print(f"    有效持仓数:      {1 / h:7.2f}  (共 {len(weights)} 只)")

    # IPS 检查
    if args.policy and os.path.exists(args.policy):
        with open(args.policy, encoding="utf-8") as f:
            pol = json.load(f)
        lim = pol.get("position_limits", {})
        cap = lim.get("single_name_max_pct")
        cap3 = lim.get("top3_max_pct")
        breaches = []
        for s, w in weights.items():
            if cap is not None and w * 100 > cap:
                breaches.append(f"{s} {w * 100:.1f}% > 单一上限 {cap}%")
        top3 = sum(sorted((w * 100 for w in weights.values()), reverse=True)[:3])
        if cap3 is not None and top3 > cap3:
            breaches.append(f"前三大 {top3:.1f}% > {cap3}%")
        print(f"\n  IPS 集中度检查（{os.path.basename(args.policy)}, status={pol.get('status')}）:")
        if breaches:
            for b in breaches:
                print(f"    ⚠️ {b}")
        else:
            print("    ✅ 未越限")


def main():
    ap = argparse.ArgumentParser(description="组合风险分析（P0-5，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("analyze", help="分析当前权重组合的历史风险画像")
    a.add_argument("--prices", required=True, help="宽表价格 CSV: date,SYM1,SYM2,...")
    a.add_argument("--weights", help='如 "TENCENT=0.47,PDD=0.42"；缺省等权')
    a.add_argument("--benchmark", help="基准列名（价格表中的某列）")
    a.add_argument("--freq", choices=["daily", "weekly", "monthly"], help="频率(默认从日期推断)")
    a.add_argument("--rf", type=float, help="无风险利率(年化，算 Sharpe/Sortino)")
    a.add_argument("--policy", default="config/investment-policy.json")
    args = ap.parse_args()
    if args.cmd != "analyze":
        ap.print_help()
        return
    analyze(args)


if __name__ == "__main__":
    main()
