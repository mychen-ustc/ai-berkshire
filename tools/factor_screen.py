#!/usr/bin/env python3
"""五面因子 IS-FDR 双门筛（OOS-first，零外部依赖）——信号与策略路线图 P2。

一次性把 factor_library 的**可 PIT 重建**因子跑一遍 OOS 回测,并施加**多重检验双门**:
  ① 每因子:OOS 净额 vs 0 的 block-bootstrap p(启发式证据) + 相对基准净超额(真 alpha)
  ② 家族层:BH-FDR 跨"本次测试的因子家族"控假发现率(多重检验分母=跑了几个因子)
  ③ 功效层:power_at(样本数,效应,波动) 标注"这个样本能不能得结论"
  ④ 覆盖层:coverage_from_master(无历史成分分母→coverage-unknown)

**诚实预期**:38 标的×2 年、单因子重叠窗——绝大多数因子会被 FDR/功效/净超额门拒掉。
"证伪也是成果":本工具的价值是**拦截假阳性**,不是产出赢家。

**PIT 边界**:只筛 PIT_SAFE 因子{quality,momentum,lowvol,size};value/growth 用前瞻一致预期、
历史不可无前视重建,**无法诚实 OOS 回测**——显式列为"不可测",不静默跳过。

非交易建议。用法:
  python3 tools/factor_screen.py run --prices data/build_universe_prices_2y.csv --benchmark SPY
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strategy_backtest as sb   # noqa: E402  复用 OOS-first 回测脊柱
import signal_lab as sl          # noqa: E402  FDR/功效/覆盖率
import factor_library as fl      # noqa: E402  因子集与 PIT 状态

# 因子分类(决定能否在**本价格矩阵 + 本地库**上诚实离线回测):
SCREENED_PRICE = {"momentum", "lowvol"}          # 直接由 CSV 价格矩阵 PIT 重建(as_of 截断)
SCREENED_FUND = {"quality"}                       # 由 pit_financials ROE(as_of,无前视)
NEEDS_SHARES = {"size"}                           # 需历史股本;security_master 空/ETF 无股本→不可离线
SKIP_REASON = {
    "size": "需历史流通股本(security_master 空、ETF 无股本)→ 本矩阵不可离线 PIT 重建",
    "value": "非 PIT:用前瞻一致预期(us_consensus),历史不可无前视重建",
    "growth": "非 PIT:用前瞻一致预期,历史不可无前视重建",
}


# --------------------------------------------------------------------------
# 纯函数:由价格矩阵 PIT 重建 price-based 因子(momentum/lowvol),as_of 截断
# --------------------------------------------------------------------------
def _closes_asof(prices, symbol, as_of):
    """标的在 as_of(含)及之前的 (date, close) 有序序列。纯函数,无前视。"""
    px = prices.get(symbol, {})
    return [(d, px[d]) for d in sorted(px) if d <= as_of and px[d] is not None]


def momentum_asof(prices, symbol, as_of, look=52, skip=4):
    """12−1 动量(周频近似):回看 look 周、跳过最近 skip 周(避免短期反转)的累计收益。
    纯函数;数据不足→None。"""
    seq = _closes_asof(prices, symbol, as_of)
    if len(seq) < look + 1:
        return None
    end = seq[-1 - skip][1]                    # skip 周前
    start = seq[-1 - look][1]                  # look 周前
    if not start:
        return None
    return end / start - 1.0


def lowvol_asof(prices, symbol, as_of, window=26):
    """低波因子:最近 window 周周收益标准差的**负值**(波动越低分越高)。纯函数;不足→None。"""
    seq = _closes_asof(prices, symbol, as_of)
    if len(seq) < window + 1:
        return None
    rets = [seq[i][1] / seq[i - 1][1] - 1.0 for i in range(len(seq) - window + 1, len(seq))
            if seq[i - 1][1]]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return -math.sqrt(var)


def score_factor_local(factor, universe, rebal, prices):
    """按因子从**本地源**在每个再平衡日打分(无网络)。→ {date: {sym: score}}。"""
    if factor in SCREENED_FUND:                 # quality = ROE(pit_financials,as_of)
        return sb.scores_pit(universe, rebal, factor)
    if factor == "momentum":
        return {d: {s: momentum_asof(prices, s, d) for s in universe} for d in rebal}
    if factor == "lowvol":
        return {d: {s: lowvol_asof(prices, s, d) for s in universe} for d in rebal}
    raise ValueError(f"因子 {factor} 不在离线可筛集")


# --------------------------------------------------------------------------
# 纯函数:双门判定
# --------------------------------------------------------------------------
def apply_family_fdr(factor_pvals, alpha=0.10):
    """对"本次因子家族"施加 BH-FDR。→ {factor: {survives, rank, crit}}。纯函数。
    多重检验分母 = len(factor_pvals);控 FDR(非 FWER)。"""
    items = [(f, p) for f, p in factor_pvals.items() if p is not None]
    if not items:
        return {f: {"survives": False, "reason": "无 p 值"} for f in factor_pvals}
    pvals = [p for _, p in items]
    bh = sl.benjamini_hochberg(pvals, alpha=alpha)          # {rejected:[bool原序], threshold, n_reject}
    out = {}
    for i, (f, p) in enumerate(items):
        out[f] = {"survives": bool(bh["rejected"][i]), "p": p,
                  "bh_threshold": bh.get("threshold")}
    for f, p in factor_pvals.items():
        if p is None:
            out[f] = {"survives": False, "p": None, "reason": "无 p 值(样本不足)"}
    return out


def double_gate_verdict(factor, oos_cagr, oos_p, net_excess, fdr_survives,
                        power, min_material=0.03, min_power=0.5):
    """把四道门合成单因子裁决。纯函数。全过才 pass(诚实预期:多数不过)。"""
    reasons, gates = [], {}
    # 门①物质性:OOS CAGR ≥ 门槛
    gates["material"] = (oos_cagr is not None and oos_cagr >= min_material)
    if not gates["material"]:
        reasons.append(f"OOS CAGR {_p(oos_cagr)} < 物质性门槛 {min_material:.0%}")
    # 门②相对基准净超额 > 0(真 alpha,非搭大盘便车)
    gates["net_excess"] = (net_excess is not None and net_excess > 0)
    if not gates["net_excess"]:
        reasons.append(f"相对基准净超额 {_p(net_excess)} ≤ 0(无真 alpha/跑输基准)")
    # 门③FDR:家族多重检验后仍显著
    gates["alpha_fdr"] = bool(fdr_survives)
    if not gates["alpha_fdr"]:
        reasons.append(f"BH-FDR 家族校正后不显著(p={_p3(oos_p)})")
    # 门④功效:样本能撑起结论
    gates["power"] = (power is not None and power >= min_power)
    if not gates["power"]:
        reasons.append(f"功效 {_p3(power)} < {min_power}(样本太薄,结论不可信)")
    ok = all(gates.values())
    return {"factor": factor, "pass": ok, "gates": gates,
            "reasons": reasons or ["四门全过(仍需 OOS 时间外确认)"]}


def _p(x):
    return f"{x:+.2%}" if isinstance(x, (int, float)) else "—"


def _p3(x):
    return f"{x:.3f}" if isinstance(x, (int, float)) else "—"


# --------------------------------------------------------------------------
# IO:跑一因子的 OOS 回测,收统计
# --------------------------------------------------------------------------
def backtest_factor(factor, prices, dates, syms, rebal, top_frac, cost_bps,
                    oos_frac, benchmark):
    """跑单因子 OOS 回测 → 统计行。price 因子由 CSV 离线重建;quality 由本地 ROE。"""
    import pit_financials as pf
    recs = pf.load()
    universe = ([s for s in syms if pf.as_of(recs, s, "roe", dates[-1])]
                if factor == "quality" else syms)
    scores = score_factor_local(factor, universe, rebal, prices)
    periods = sb.backtest_periods(rebal, scores, prices, top_frac, cost_bps)
    _, oos_p = sb.split_is_oos(periods, oos_frac)
    oos_perf = sb.perf(oos_p)
    oos_boot = sl.block_bootstrap_pvalue([p["net"] for p in oos_p],
                                         null_mean=0.0, block=3, seed=0)
    net_excess = None
    bench_cagr = None
    if benchmark in prices:
        bp = sb.bench_periods(prices, benchmark, rebal)
        _, bench_oos = sb.split_is_oos(bp, oos_frac)
        bench_cagr = sb.perf(bench_oos)["cagr"]
        net_excess = sb.net_excess_cagr(oos_perf["cagr"], bench_cagr)
    # 功效:以 OOS 期数为 n、月波动、以物质性门槛为待检效应(月化)
    vol_m = oos_perf["vol"] / (12 ** 0.5) if oos_perf["vol"] else 0.0
    power = sl.power_at(oos_perf["n"], 0.03 / 12, vol_m) if vol_m else None
    return {"factor": factor, "universe_n": len(universe), "oos_n": oos_perf["n"],
            "oos_cagr": oos_perf["cagr"], "oos_sharpe": oos_perf["sharpe"],
            "oos_vol": oos_perf["vol"], "oos_p": oos_boot["p_value"],
            "bench_cagr": bench_cagr, "net_excess": net_excess, "power": power}


def run_screen(prices_path, oos_frac=0.4, top_frac=0.5, cost_bps=10.0,
               benchmark="SPY", alpha=0.10, min_material=0.03):
    """跑全部 PIT_SAFE 因子 + 双门。→ {rows, verdicts, fdr, untestable}。IO。"""
    prices, dates, syms = sb.load_prices(prices_path)
    rebal = sb.month_end_dates(dates)
    rows = []
    screened = sorted(SCREENED_PRICE | SCREENED_FUND)   # 本矩阵可离线诚实回测的因子
    for factor in screened:
        try:
            rows.append(backtest_factor(factor, prices, dates, syms, rebal,
                                        top_frac, cost_bps, oos_frac, benchmark))
        except Exception as e:  # noqa: BLE001  单因子失败不拖垮全筛
            rows.append({"factor": factor, "error": f"{type(e).__name__}: {e}"})
    ok_rows = [r for r in rows if "error" not in r]
    fdr = apply_family_fdr({r["factor"]: r["oos_p"] for r in ok_rows}, alpha=alpha)
    verdicts = [double_gate_verdict(
        r["factor"], r["oos_cagr"], r["oos_p"], r["net_excess"],
        fdr.get(r["factor"], {}).get("survives", False), r["power"],
        min_material=min_material) for r in ok_rows]
    cov = sl.coverage_from_master(syms, sb.sl_delist(), universe="factor-screen")
    # 六面全景:哪些筛了、哪些因数据/PIT 限制不可离线测(附因)
    all_faces = sorted(set(fl.FACTORS))
    skipped = {f: SKIP_REASON[f] for f in all_faces if f not in screened}
    return {"rows": rows, "verdicts": verdicts, "fdr": fdr, "coverage": cov,
            "screened": screened, "skipped": skipped, "family_size": len(ok_rows),
            "alpha": alpha, "min_material": min_material,
            "n_rebal": len(rebal), "n_syms": len(syms)}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def cmd_run(args):
    res = run_screen(args.prices, oos_frac=args.oos_frac, top_frac=args.top_frac,
                     cost_bps=args.cost_bps, benchmark=args.benchmark,
                     alpha=args.alpha, min_material=args.min_material)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        return
    _render(res, args)


def _render(res, args):
    print("=" * 74)
    print(f"因子 IS-FDR 双门筛 · {res['n_syms']} 标的 · {res['n_rebal']} 个月末再平衡 · "
          f"离线可筛 {res['family_size']} 因子 · BH-FDR α={res['alpha']}")
    print("=" * 74)
    print(f"{'因子':<10}{'OOS n':>6}{'OOS CAGR':>11}{'Sharpe':>8}{'净超额':>10}"
          f"{'boot p':>8}{'FDR过':>7}{'功效':>7}  裁决")
    print("-" * 74)
    vmap = {v["factor"]: v for v in res["verdicts"]}
    for r in res["rows"]:
        if "error" in r:
            print(f"{r['factor']:<10}  ✗ {r['error'][:50]}")
            continue
        v = vmap[r["factor"]]
        fdr_ok = "✓" if res["fdr"].get(r["factor"], {}).get("survives") else "✗"
        verdict = "🟢 通过" if v["pass"] else "🔴 拒"
        sh = f"{r['oos_sharpe']:.2f}" if r["oos_sharpe"] is not None else "—"
        pw = f"{r['power']:.2f}" if r["power"] is not None else "—"
        print(f"{r['factor']:<10}{r['oos_n']:>6}{_p(r['oos_cagr']):>11}{sh:>8}"
              f"{_p(r['net_excess']):>10}{_p3(r['oos_p']):>8}{fdr_ok:>6}{pw:>7}  {verdict}")
    print("-" * 74)
    passed = [v["factor"] for v in res["verdicts"] if v["pass"]]
    print(f"四门全过因子: {passed if passed else '无(符合诚实预期:样本薄→多为 null)'}")
    for v in res["verdicts"]:
        if not v["pass"]:
            print(f"  🔴 {v['factor']}: {'; '.join(v['reasons'][:2])}")
    print(f"\n本矩阵不可离线诚实回测(附因):")
    for f, why in res["skipped"].items():
        print(f"  · {f}: {why}")
    print(f"覆盖率: {res['coverage']['verdict']}")
    print(f"\n⚠️ 门槛:OOS CAGR≥{res['min_material']:.0%} 且 相对基准净超额>0 且 BH-FDR(α={res['alpha']})显著 "
          f"且 功效≥0.5。bootstrap 是启发式非严格零分布;覆盖率无分母=coverage-unknown;"
          f"OOS 仍须时间外确认。非交易建议。")


def main():
    ap = argparse.ArgumentParser(description="五面因子 IS-FDR 双门筛(OOS-first,零依赖)")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="跑全部 PIT_SAFE 因子 + 多重检验双门")
    r.add_argument("--prices", required=True, help="宽表价格 CSV: date,SYM1,...")
    r.add_argument("--top-frac", dest="top_frac", type=float, default=0.5)
    r.add_argument("--cost-bps", dest="cost_bps", type=float, default=10.0)
    r.add_argument("--oos-frac", dest="oos_frac", type=float, default=0.4)
    r.add_argument("--benchmark", default="SPY", help="相对基准(须在价格矩阵内)")
    r.add_argument("--alpha", type=float, default=0.10, help="BH-FDR 假发现率上限")
    r.add_argument("--min-material", dest="min_material", type=float, default=0.03,
                   help="OOS CAGR 物质性门槛(年化)")
    r.add_argument("--json", action="store_true")
    args = ap.parse_args()
    {"run": cmd_run}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
