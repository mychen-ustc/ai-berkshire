#!/usr/bin/env python3
"""统一回测框架（零外部依赖，仅 stdlib）。

给策略信号一个**点时(point-in-time)、含成本**的统一检验台：任何择时/动量/趋势信号
（technicals / factor_model 产出的规则）都在这里跑同一口径，才谈得上"有没有历史 edge"。

内置策略（信号仅用回看窗口、严格不看未来）：
  · buyhold  —— 等权买入持有（基准）。
  · trend    —— 逐标的择时：收盘 > SMA(n) 才持有、否则空仓（趋势跟踪）。
  · momentum —— 横截面动量：按回看收益排名，持有前 N 名等权，定期再平衡。
含交易成本（bps/换手）。输出净值曲线指标：CAGR/波动/最大回撤/Sharpe/换手/胜率 + 对基准。

诚实边界（务必读）：
  · **幸存者偏差**：股票池是"当前还活着"的标的，未纳入退市/失败样本 → 结果偏乐观（真回测需退市库，见路线图 P3-6）。
  · **点时仅限价格**：信号只用历史价格、不看未来；但未接入点时基本面，估值类信号无法在此检验。
  · 成本/滑点为简化线性模型；短窗口、少标的结果不稳；**过去有效 ≠ 未来有效**。

用法：
  python3 tools/backtest.py run --from-datalayer "AAPL,GOOGL,MSFT,AMZN,NVDA,META,SPY" \
      --strategy momentum --lookback 12 --top 3 --benchmark SPY --freq monthly --period 5y --cost-bps 10
  python3 tools/backtest.py run --from-datalayer "600519,000858,300750" --strategy trend --sma 30 --freq weekly
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portfolio_risk as pr  # noqa: E402  复用 build_matrix / ann_vol / max_drawdown / nav_from_returns / cagr


# --------------------------------------------------------------------------
# 信号 → 目标权重（仅用 prices[<=i]，严格无未来函数）
# --------------------------------------------------------------------------
def w_buyhold(cols, syms, i, args):
    return {s: 1.0 / len(syms) for s in syms}


def w_trend(cols, syms, i, args):
    n = args.sma
    passed = []
    for s in syms:
        if i + 1 >= n:
            sma = sum(cols[s][i - n + 1:i + 1]) / n
            if cols[s][i] > sma:
                passed.append(s)
    if not passed:
        return {s: 0.0 for s in syms}            # 全空仓（持币）
    return {s: (1.0 / len(passed) if s in passed else 0.0) for s in syms}


def w_momentum(cols, syms, i, args):
    lb = args.lookback
    if i < lb:
        return {s: 1.0 / len(syms) for s in syms}
    rets = {s: (cols[s][i] / cols[s][i - lb] - 1) if cols[s][i - lb] else -1e9 for s in syms}
    ranked = sorted(syms, key=lambda s: -rets[s])
    top = ranked[:max(1, args.top)]
    return {s: (1.0 / len(top) if s in top else 0.0) for s in syms}


STRATEGIES = {"buyhold": w_buyhold, "trend": w_trend, "momentum": w_momentum}


# --------------------------------------------------------------------------
# 回测引擎
# --------------------------------------------------------------------------
def backtest(cols, syms, dates, args):
    sig = STRATEGIES[args.strategy]
    cost_rate = args.cost_bps / 10000.0
    T = len(dates)
    warmup = {"buyhold": 1, "trend": args.sma, "momentum": args.lookback + 1}[args.strategy]
    start = max(1, warmup)
    prev_w = {s: 0.0 for s in syms}
    port_rets, turnovers = [], []
    for i in range(start - 1, T - 1):                 # 在 i 定权重，吃 [i→i+1] 收益
        w = sig(cols, syms, i, args)
        turnover = sum(abs(w[s] - prev_w[s]) for s in syms)
        gross = sum(w[s] * (cols[s][i + 1] / cols[s][i] - 1) for s in syms)
        net = gross - cost_rate * turnover
        port_rets.append(net)
        turnovers.append(turnover)
        prev_w = w
    return port_rets, turnovers, start


def metrics(rets, ppy):
    if not rets:
        return {}
    nav = pr.nav_from_returns(rets)
    n = len(rets)
    return {"periods": n, "cagr": pr.cagr(nav, ppy, n), "vol": pr.ann_vol(rets, ppy),
            "mdd": pr.max_drawdown(nav), "final_nav": nav[-1],
            "sharpe": (pr.cagr(nav, ppy, n) / pr.ann_vol(rets, ppy)) if pr.ann_vol(rets, ppy) else float("nan"),
            "hit_rate": sum(1 for r in rets if r > 0) / n,
            "best": max(rets), "worst": min(rets)}


def run(args):
    dates, cols, _, label = pr.build_matrix(args)
    syms = [s for s in cols if s != args.benchmark] if (args.benchmark and args.strategy != "buyhold" and args.benchmark in cols and len(cols) > 1) else list(cols)
    if len(dates) < 10:
        raise SystemExit(f"周期过短（{len(dates)} 期），无法回测")
    ppy = {"daily": 252, "weekly": 52, "monthly": 12}.get(args.freq) or pr.periods_per_year(dates)

    rets, turns, start = backtest(cols, syms, dates, args)
    m = metrics(rets, ppy)

    # 基准：等权买入持有全体（或指定基准列）
    if args.benchmark and args.benchmark in cols:
        bench_rets = pr.pct_returns(cols[args.benchmark])[start - 1:]
        bench_label = args.benchmark
    else:
        bh = w_buyhold(cols, list(cols), 0, args)
        bench_rets = [sum(bh[s] * (cols[s][i + 1] / cols[s][i] - 1) for s in cols)
                      for i in range(start - 1, len(dates) - 1)]
        bench_label = "等权买入持有"
    bm = metrics(bench_rets, ppy)

    print("=" * 66)
    print(f"回测 · {label} · 策略={args.strategy} · {m.get('periods', 0)} 期 · 年化因子 {ppy}")
    cfg = {"trend": f"SMA={args.sma}", "momentum": f"回看={args.lookback}/持有前{args.top}", "buyhold": "等权"}[args.strategy]
    print(f"配置: {cfg} · 成本 {args.cost_bps}bps/换手 · 标的 {len(syms)} 只")
    print("=" * 66)
    hdr = f"  {'指标':<12}{'策略':>14}{bench_label[:12]:>14}"
    print(hdr)
    print("  " + "-" * (len(hdr)))

    def row(name, kv, kb, pct=True, pp=2):
        f = (lambda x: f"{x * 100:.{pp}f}%") if pct else (lambda x: f"{x:.{pp}f}")
        sv = f(m[kv]) if kv in m else "—"
        bv = f(bm[kb]) if kb in bm else "—"
        print(f"  {name:<12}{sv:>14}{bv:>14}")

    row("年化收益", "cagr", "cagr")
    row("年化波动", "vol", "vol")
    row("最大回撤", "mdd", "mdd")
    row("Sharpe", "sharpe", "sharpe", pct=False)
    row("胜率", "hit_rate", "hit_rate")
    print(f"  {'累计净值':<12}{m.get('final_nav', 1):>13.2f}x{bm.get('final_nav', 1):>13.2f}x")
    if turns:
        print(f"  平均换手/期:  {sum(turns) / len(turns):.2f}")
    excess = (m.get("cagr", 0) - bm.get("cagr", 0)) * 100
    print(f"\n  超额年化(vs {bench_label}): {excess:+.2f}pp  "
          f"{'✅策略跑赢' if excess > 0 else '❌未跑赢，信号无 edge 或被成本吃掉'}")
    print("\n  ⚠️ 幸存者偏差(未含退市样本→偏乐观) · 点时仅限价格 · 过去有效≠未来有效。")
    return {"strategy": args.strategy, "metrics": m, "benchmark": bm, "excess_pp": excess}


def main():
    ap = argparse.ArgumentParser(description="统一回测框架（点时+含成本+多策略，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="跑一次回测")
    src = r.add_mutually_exclusive_group(required=True)
    src.add_argument("--prices", help="宽表价格 CSV")
    src.add_argument("--from-datalayer", help='符号列表 "AAPL,GOOGL,SPY"')
    src.add_argument("--from-ledger", help="交易账本 CSV")
    r.add_argument("--fx")
    r.add_argument("--strategy", default="momentum", choices=list(STRATEGIES))
    r.add_argument("--sma", type=int, default=30, help="trend 策略的均线周期")
    r.add_argument("--lookback", type=int, default=12, help="momentum 回看周期数")
    r.add_argument("--top", type=int, default=3, help="momentum 持有前 N 名")
    r.add_argument("--cost-bps", type=float, default=10.0, help="每单位换手成本(bps)")
    r.add_argument("--benchmark", help="基准列（不参与选股，仅比较）")
    r.add_argument("--period", default="5y", choices=["1y", "2y", "5y", "10y", "max"])
    r.add_argument("--freq", default="monthly", choices=["daily", "weekly", "monthly"])
    r.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd != "run":
        ap.print_help()
        return
    out = run(args)
    if args.json:
        import json
        print("\n" + json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
