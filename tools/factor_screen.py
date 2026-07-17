#!/usr/bin/env python3
"""因子 IS-FDR 三态筛（OOS-first，零外部依赖）——信号与策略路线图 P2。

一次性把 factor_library 的**可 PIT 重建**因子跑一遍 OOS 回测,并施加多重检验门,输出三态裁决:
  · 🟢通过 / 🔴拒 / **⚪不可判定**(样本欠功效→证据不足,≠因子无效)
门(经对抗性评审修正,见 reports/因子筛复盘-诚实边界-20260717.md):
  ① 功效层先行:power_at<0.5 → **⚪不可判定**(不进 AND 淘汰);并给 MDE("本样本仅能检出≥X%/年")
  ② 物质性:OOS CAGR ≥ 门槛
  ③ **相对同池等权(same-opportunity-set)净超额>0**——隔离选股技能与资产类别漂移
     (评审关键修正:原拿混合篮对比纯股 SPY,会系统性冤枉防御/低波因子;SPY 仅并列展示)
  ④ 显著性用**相对同池等权的配对超额** block-bootstrap p(而非 vs 0,后者在牛市里同义反复)
  ⑤ 家族层:BH-FDR 跨本次因子家族控 FDR;覆盖层:coverage_from_master

**诚实预期**:薄样本(每因子 OOS n≈10)下功效结构性 <0.15 → 多数因子应落 ⚪不可判定,
而非"证伪"。本工具是**流水线压力测试/假阳性拦截器**,当前数据不足以对因子有效性下任何方向定论。

**PIT 边界**:只筛能由本地源无前视重建的因子{quality=ROE,momentum,lowvol};
size 需历史股本、value/growth 非 PIT,**显式列"不可离线测"**,不静默跳过。

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


def universe_ew_periods(prices, universe, rebal):
    """全 universe 等权买入持有每期收益 = **same-opportunity-set 无技能基准**。纯函数。
    (评审修正)因子选股相对'等权持有同一批标的'才是选股技能;拿混合篮对比纯股 SPY 是苹果比橘子。"""
    out = []
    for i in range(len(rebal) - 1):
        d0, d1 = rebal[i], rebal[i + 1]
        avail = [s for s in universe
                 if prices.get(s, {}).get(d0) and prices.get(s, {}).get(d1)]
        if not avail:
            out.append({"d0": d0, "d1": d1, "net": 0.0, "turnover": 0.0})
            continue
        r = sum(prices[s][d1] / prices[s][d0] - 1.0 for s in avail) / len(avail)
        out.append({"d0": d0, "d1": d1, "net": round(r, 6), "turnover": 0.0})
    return out


def paired_excess(factor_periods, bench_periods_):
    """逐期(因子净额 − 基准净额)的配对差。纯函数。用于'相对基准'显著性(而非 vs 0)。"""
    bm = {b["d0"]: b["net"] for b in bench_periods_}
    return [p["net"] - bm.get(p["d0"], 0.0) for p in factor_periods]


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


def screen_verdict(factor, oos_cagr, oos_p_excess, net_excess_ew, fdr_survives,
                   power, mde, holdings, min_material=0.03, min_power=0.5):
    """三态裁决:🟢通过 / 🔴拒 / ⚪不可判定。纯函数。
    (经评审#净超额/#功效修正)核心区分:
    - **功效不足 → ⚪不可判定**(证据不足,≠因子无效;不进 AND 淘汰);
    - 功效够 → 按经济门判:物质性 + **相对同池等权净超额>0**(隔离选股技能,非资产漂移) + FDR 显著。
    net_excess_ew/oos_p_excess 都相对**同池等权**(same-opportunity-set),不再拿混合篮对比纯股 SPY。"""
    econ, reasons = {}, []
    econ["material"] = (oos_cagr is not None and oos_cagr >= min_material)
    econ["net_excess_ew"] = (net_excess_ew is not None and net_excess_ew > 0)
    econ["alpha_fdr"] = bool(fdr_survives)
    powered = (power is not None and power >= min_power)
    thin = (holdings is not None and holdings < 3)
    if not powered:
        status = "inconclusive"
        reasons.append(f"功效 {_p3(power)} < {min_power}:n 太薄、证据不足→**不可判定**"
                       f"(≠因子无效);本样本仅能检出 ≥{_p(mde)}/期的边际")
    elif all(econ.values()):
        status = "pass"
        reasons.append("功效达标且经济门全过(相对同池等权有正超额;仍需时间外确认)")
    else:
        status = "reject"
        if not econ["material"]:
            reasons.append(f"OOS CAGR {_p(oos_cagr)} < 物质性门槛 {min_material:.0%}")
        if not econ["net_excess_ew"]:
            reasons.append(f"相对同池等权净超额 {_p(net_excess_ew)} ≤ 0(无选股技能)")
        if not econ["alpha_fdr"]:
            reasons.append(f"相对同池等权 BH-FDR 家族校正后不显著(p≈{_p3(oos_p_excess)})")
    if thin:
        reasons.append(f"⚠️ 实际平均持仓仅 {holdings} 只,不足以称'因子检验'")
    return {"factor": factor, "status": status, "econ_gates": econ,
            "powered": powered, "holdings": holdings, "reasons": reasons}


# 兼容旧调用名(已弃用,内部转三态)
def double_gate_verdict(factor, oos_cagr, oos_p, net_excess, fdr_survives,
                        power, min_material=0.03, min_power=0.5):
    v = screen_verdict(factor, oos_cagr, oos_p, net_excess, fdr_survives, power,
                       None, None, min_material, min_power)
    return {"factor": factor, "pass": v["status"] == "pass",
            "gates": {**v["econ_gates"], "power": v["powered"]},
            "reasons": v["reasons"], "status": v["status"]}


def _p(x):
    return f"{x:+.2%}" if isinstance(x, (int, float)) else "—"


def _p3(x):
    return f"{x:.3f}" if isinstance(x, (int, float)) else "—"


# --------------------------------------------------------------------------
# IO:跑一因子的 OOS 回测,收统计
# --------------------------------------------------------------------------
def backtest_factor(factor, prices, dates, syms, rebal, top_frac, cost_bps,
                    oos_frac, benchmark):
    """跑单因子 OOS 回测 → 统计行。price 因子由 CSV 离线重建;quality 由本地 ROE。
    (评审修正)显著性与净超额都相对**同池等权(same-opportunity-set)**——隔离选股技能与资产漂移;
    SPY 仅并列展示。功效用 OOS 期数、并给 MDE。"""
    import pit_financials as pf
    recs = pf.load()
    universe = ([s for s in syms if pf.as_of(recs, s, "roe", dates[-1])]
                if factor == "quality" else syms)
    scores = score_factor_local(factor, universe, rebal, prices)
    periods = sb.backtest_periods(rebal, scores, prices, top_frac, cost_bps)
    _, oos_p = sb.split_is_oos(periods, oos_frac)
    oos_perf = sb.perf(oos_p)
    holdings = round(sum(p["n_sel"] for p in oos_p) / len(oos_p), 1) if oos_p else 0
    # 同池等权基准(无技能对照) + 相对它的净超额与配对显著性
    ewp = universe_ew_periods(prices, universe, rebal)
    _, ew_oos = sb.split_is_oos(ewp, oos_frac)
    ew_cagr = sb.perf(ew_oos)["cagr"]
    net_excess_ew = sb.net_excess_cagr(oos_perf["cagr"], ew_cagr)
    excess_series = paired_excess(oos_p, ew_oos)                # 逐期(因子−同池等权)
    boot_excess = sl.block_bootstrap_pvalue(excess_series, null_mean=0.0, block=3, seed=0)
    # SPY 仅并列展示(不作判定基准)
    net_excess_spy = None
    if benchmark in prices:
        bp = sb.bench_periods(prices, benchmark, rebal)
        _, bench_oos = sb.split_is_oos(bp, oos_frac)
        net_excess_spy = sb.net_excess_cagr(oos_perf["cagr"], sb.perf(bench_oos)["cagr"])
    # 功效 + MDE:n、月波动、待检效应(物质性门槛月化)。MDE 直白说"本样本能看出多大边际"
    vol_m = oos_perf["vol"] / (12 ** 0.5) if oos_perf["vol"] else 0.0
    power = sl.power_at(oos_perf["n"], 0.03 / 12, vol_m) if vol_m else None
    mde_m = sl.min_detectable_effect(oos_perf["n"], vol_m, power=0.5) if vol_m else None
    mde_annual = mde_m * 12 if mde_m is not None else None
    return {"factor": factor, "universe_n": len(universe), "oos_n": oos_perf["n"],
            "holdings": holdings, "oos_cagr": oos_perf["cagr"],
            "oos_sharpe": oos_perf["sharpe"], "oos_vol": oos_perf["vol"],
            "ew_cagr": ew_cagr, "net_excess_ew": net_excess_ew,
            "oos_p_excess": boot_excess["p_value"], "net_excess_spy": net_excess_spy,
            "power": power, "mde_annual": mde_annual}


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
    # FDR 施加于**相对同池等权的配对超额** p 值(而非 vs 0),与经济门口径一致
    fdr = apply_family_fdr({r["factor"]: r["oos_p_excess"] for r in ok_rows}, alpha=alpha)
    verdicts = [screen_verdict(
        r["factor"], r["oos_cagr"], r["oos_p_excess"], r["net_excess_ew"],
        fdr.get(r["factor"], {}).get("survives", False), r["power"],
        r["mde_annual"], r["holdings"], min_material=min_material) for r in ok_rows]
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


_ICON = {"pass": "🟢通过", "reject": "🔴拒", "inconclusive": "⚪不可判定"}


def _render(res, args):
    print("=" * 82)
    print(f"因子 IS-FDR 三态筛 · {res['n_syms']} 标的 · {res['n_rebal']} 个月末再平衡 · "
          f"离线可筛 {res['family_size']} 因子 · 基准=同池等权 · BH-FDR α={res['alpha']}")
    print("=" * 82)
    print(f"{'因子':<9}{'持仓':>5}{'OOS n':>6}{'OOS CAGR':>10}{'超额vs同池':>11}"
          f"{'超额vsSPY':>10}{'配对p':>7}{'FDR':>5}{'功效':>6}{'MDE/年':>8}  裁决")
    print("-" * 82)
    vmap = {v["factor"]: v for v in res["verdicts"]}
    for r in res["rows"]:
        if "error" in r:
            print(f"{r['factor']:<9}  ✗ {r['error'][:50]}")
            continue
        v = vmap[r["factor"]]
        fdr_ok = "✓" if res["fdr"].get(r["factor"], {}).get("survives") else "✗"
        sh = f"{r['holdings']}" if r["holdings"] is not None else "—"
        pw = f"{r['power']:.2f}" if r["power"] is not None else "—"
        print(f"{r['factor']:<9}{sh:>5}{r['oos_n']:>6}{_p(r['oos_cagr']):>10}"
              f"{_p(r['net_excess_ew']):>11}{_p(r['net_excess_spy']):>10}"
              f"{_p3(r['oos_p_excess']):>7}{fdr_ok:>5}{pw:>6}{_p(r['mde_annual']):>8}  {_ICON[v['status']]}")
    print("-" * 82)
    by = {"pass": [], "reject": [], "inconclusive": []}
    for v in res["verdicts"]:
        by[v["status"]].append(v["factor"])
    print(f"🟢通过: {by['pass'] or '无'}  ·  🔴拒(功效够但跑输同池等权): {by['reject'] or '无'}  ·  "
          f"⚪不可判定(样本欠功效): {by['inconclusive'] or '无'}")
    for v in res["verdicts"]:
        print(f"  {_ICON[v['status']]} {v['factor']}: {'; '.join(v['reasons'][:2])}")
    print(f"\n本矩阵不可离线诚实回测(附因):")
    for f, why in res["skipped"].items():
        print(f"  · {f}: {why}")
    print(f"覆盖率: {res['coverage']['verdict']}")
    print(f"\n⚠️ 判定基准=**同池等权**(same-opportunity-set,隔离选股技能与资产漂移);SPY 仅并列展示。")
    print(f"   门:功效<0.5→⚪不可判定(证据不足≠因子无效);功效够才判 OOS CAGR≥{res['min_material']:.0%} 且"
          f" 相对同池等权净超额>0 且 配对超额 BH-FDR(α={res['alpha']})显著。")
    print(f"   bootstrap 启发式非严格零分布,n 小→p 只看数量级(有效独立块≈n/3)、勿据以给因子排序;"
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
