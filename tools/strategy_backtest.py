#!/usr/bin/env python3
"""因子策略回测脊柱（OOS-first，零外部依赖）——信号与策略路线图 P0 ⑤。

诊断:backtest_rigorous 只是审计器、无产收益引擎;因子→可验证策略闭环不存在。本工具补脊柱:
  PIT 因子打分(仅 PIT_SAFE) → 月度纯多头选股 → 扣 TCA 净额 → **walk-forward 样本外(OOS)** → 显著性。

评审纪律全焊入:
  · **只用 PIT_SAFE 因子**(factor_pit_status;ROE 质量走 pit_financials.as_of,available_at<=d 无前视)
  · **OOS-first**:样本内(IS)/样本外(OOS)分开报告,OOS 才算数(全样本永不作头条)
  · **扣 TCA 净额**为唯一头条(很多样本内 alpha 扣成本后消失)
  · **coverage_from_master** 诚实标覆盖率(无分母→coverage-unknown,不称"无幸存者偏差")
  · 每次回测写**哈希链试验台账**(多重比较分母)

诚实边界:最小实现(纯多头/月度/单因子);universe 受价格矩阵限(薄);ROE 只有美股点时库;
预期多为 null(样本薄)——"证伪也是成果"。非交易建议。

用法:
  python3 tools/strategy_backtest.py run --prices data/build_universe_prices_2y.csv --factor quality \
      --top-frac 0.5 --cost-bps 10 --oos-frac 0.4
"""
import argparse
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quant_metrics as qm       # noqa: E402  复用 sharpe/max_drawdown
import signal_lab as sl          # noqa: E402  OOS 切分/覆盖率/台账


# --------------------------------------------------------------------------
# 纯函数（可测）
# --------------------------------------------------------------------------
def month_end_dates(sorted_dates):
    """每个(年,月)的最后一个日期(月末再平衡点)。纯函数。"""
    last = {}
    for d in sorted_dates:
        last[d[:7]] = d          # 'YYYY-MM' → 该月最后见到的日期
    return [last[k] for k in sorted(last)]


def select_top(scores, top_frac=0.5):
    """按分数(降序)选前 top_frac 的标的(去 None)。纯函数。"""
    valid = [(s, v) for s, v in scores.items() if v is not None]
    if not valid:
        return []
    valid.sort(key=lambda x: x[1], reverse=True)
    k = max(1, int(round(len(valid) * top_frac)))
    return [s for s, _ in valid[:k]]


def equal_weight(symbols):
    """等权。纯函数。"""
    n = len(symbols)
    return {s: 1.0 / n for s in symbols} if n else {}


def holding_return(prices, weights, d0, d1):
    """持有期组合收益 = Σ w·(P[d1]/P[d0]−1)。缺价的标的剔除并**重归一**。纯函数。"""
    avail = {s: w for s, w in weights.items()
             if s in prices and prices[s].get(d0) and prices[s].get(d1)}
    tot = sum(avail.values())
    if tot <= 0:
        return 0.0
    r = 0.0
    for s, w in avail.items():
        r += (w / tot) * (prices[s][d1] / prices[s][d0] - 1.0)
    return r


def turnover(w_prev, w_new):
    """单边换手 = 0.5·Σ|Δw|(0=不变,1=全换)。纯函数。"""
    keys = set(w_prev) | set(w_new)
    return 0.5 * sum(abs(w_new.get(k, 0.0) - w_prev.get(k, 0.0)) for k in keys)


def backtest_periods(rebal_dates, scores_by_date, prices, top_frac=0.5, cost_bps=10.0):
    """逐再平衡期回测。→ [{d0,d1,n_sel,gross,turnover,net}]。纯函数(scores/prices 预取)。
    net = gross − 单边换手 × cost_bps/1e4。"""
    periods, w_prev = [], {}
    for i in range(len(rebal_dates) - 1):
        d0, d1 = rebal_dates[i], rebal_dates[i + 1]
        sel = select_top(scores_by_date.get(d0, {}), top_frac)
        w = equal_weight(sel)
        gross = holding_return(prices, w, d0, d1)
        to = turnover(w_prev, w)
        net = gross - to * (cost_bps / 1e4)
        periods.append({"d0": d0, "d1": d1, "n_sel": len(sel),
                        "gross": round(gross, 6), "turnover": round(to, 4), "net": round(net, 6)})
        w_prev = w
    return periods


def split_is_oos(periods, oos_frac=0.4):
    """按时间切:前 (1−oos_frac) 为样本内 IS,后 oos_frac 为样本外 OOS。纯函数。"""
    n = len(periods)
    k = int(round(n * (1 - oos_frac)))
    return periods[:k], periods[k:]


def bench_periods(prices, bench, rebal_dates):
    """基准(如 SPY)按同再平衡日的买入持有每期收益。纯函数。"""
    out = []
    for i in range(len(rebal_dates) - 1):
        d0, d1 = rebal_dates[i], rebal_dates[i + 1]
        px = prices.get(bench, {})
        r = (px[d1] / px[d0] - 1.0) if px.get(d0) and px.get(d1) else 0.0
        out.append({"d0": d0, "d1": d1, "net": round(r, 6), "turnover": 0.0})
    return out


def net_excess_cagr(strat_cagr, bench_cagr):
    """策略相对基准的净超额 CAGR。纯函数。"""
    if strat_cagr is None or bench_cagr is None:
        return None
    return strat_cagr - bench_cagr


def strategy_param_hash(factor, universe, top_frac, cost_bps, oos_frac):
    """策略参数指纹(预注册与回测须一致,否则 promote 视为改参)。纯函数。"""
    import signal_lab as _sl
    return _sl.param_hash("strategy", factor, universe, top_frac, cost_bps, oos_frac)


def perf(periods, ppy=12, rf=0.04):
    """一段期收益的绩效:CAGR/波动/最大回撤/Sharpe(净额)。复用 quant_metrics。纯函数。"""
    rets = [p["net"] for p in periods]
    if not rets:
        return {"n": 0, "cagr": None, "vol": None, "maxdd": None, "sharpe": None}
    cum = 1.0
    for r in rets:
        cum *= (1 + r)
    years = len(rets) / ppy
    cagr = cum ** (1 / years) - 1 if years > 0 and cum > 0 else None
    mu = sum(rets) / len(rets)
    vol = (math.sqrt(sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)) * math.sqrt(ppy)) if len(rets) > 1 else None
    return {"n": len(rets), "cagr": cagr, "vol": vol,
            "maxdd": qm.max_drawdown(rets), "sharpe": qm.sharpe(rets, rf, ppy),
            "avg_turnover": round(sum(p["turnover"] for p in periods) / len(periods), 3)}


# --------------------------------------------------------------------------
# IO：装载价格 + PIT 因子打分
# --------------------------------------------------------------------------
def load_prices(path):
    """宽表 CSV(date,SYM1,...) → ({sym:{date:px}}, sorted_dates, symbols)。"""
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    syms = [c for c in rows[0].keys() if c != "date"] if rows else []
    prices = {s: {} for s in syms}
    for r in rows:
        for s in syms:
            try:
                prices[s][r["date"]] = float(r[s])
            except (ValueError, TypeError):
                pass
    return prices, sorted(r["date"] for r in rows), syms


def _roe_asof(symbol, d, recs):
    hit = __import__("pit_financials").as_of(recs, symbol, "roe", d)
    return hit["value"] if hit else None


def scores_pit(symbols, rebal_dates, factor="quality"):
    """在每个再平衡日算 PIT 因子分(仅 PIT_SAFE)。quality=ROE(pit_financials.as_of,无前视)。"""
    import factor_library as fl
    if factor not in fl.PIT_SAFE_FACTORS:
        raise SystemExit(f"因子 {factor} 非 PIT_SAFE({sorted(fl.PIT_SAFE_FACTORS)});回测只用可无前视重建的因子")
    import pit_financials as pf
    recs = pf.load()
    out = {}
    for d in rebal_dates:
        if factor == "quality":
            out[d] = {s: _roe_asof(s, d, recs) for s in symbols}
        else:
            # momentum/lowvol/size:用 factor_library PIT(as_of 截断);单日单因子
            raw, meta = fl.gather_raw(symbols, as_of=d)
            out[d] = {m["symbol"]: raw[factor][i] for i, m in enumerate(meta)}
    return out


def cmd_run(args):
    prices, dates, syms = load_prices(args.prices)
    import pit_financials as pf
    recs = pf.load()
    # 只保留有该 PIT 因子数据的标的(quality→有 ROE 的)
    universe = [s for s in syms if pf.as_of(recs, s, "roe", dates[-1])] if args.factor == "quality" else syms
    rebal = month_end_dates(dates)
    if len(rebal) < 6:
        print(f"⚠️ 再平衡点仅 {len(rebal)},样本过薄,结果仅演示引擎。")
    scores = scores_pit(universe, rebal, args.factor)
    periods = backtest_periods(rebal, scores, prices, args.top_frac, args.cost_bps)
    is_p, oos_p = split_is_oos(periods, args.oos_frac)
    is_perf, oos_perf, all_perf = perf(is_p), perf(oos_p), perf(periods)
    # 覆盖率门禁(诚实:无成分主表分母→coverage-unknown)
    cov = sl.coverage_from_master(universe, sl_delist(), universe=args.universe)
    # OOS 显著性(net 收益 vs 0)
    oos_boot = sl.block_bootstrap_pvalue([p["net"] for p in oos_p], null_mean=0.0, block=3, seed=0)
    res = {"factor": args.factor, "universe_n": len(universe), "rebalances": len(periods),
           "IS": is_perf, "OOS": oos_perf, "ALL_biased": all_perf,
           "oos_bootstrap_p": oos_boot["p_value"], "coverage": cov}
    # 相对基准净超额(OOS):基准存在于价格矩阵时按同再平衡日买入持有
    bench = args.benchmark if args.benchmark in prices else None
    if bench:
        bp = bench_periods(prices, bench, rebal)
        _, bench_oos = split_is_oos(bp, args.oos_frac)
        bench_perf = perf(bench_oos)
        res["bench"] = bench
        res["bench_oos_cagr"] = bench_perf["cagr"]
        oos_perf["net_excess_vs_bench"] = net_excess_cagr(oos_perf["cagr"], bench_perf["cagr"])
    # 晋级门禁:找预注册(须先注册后验证),按**预注册**阈值判 promote
    ph = strategy_param_hash(args.factor, args.universe, args.top_frac, args.cost_bps, args.oos_frac)
    res["param_hash"] = ph
    prereg = sl.find_prereg(ph)
    if prereg:
        oos_for_gate = {"cagr": oos_perf["cagr"], "bootstrap_p": res["oos_bootstrap_p"],
                        "net_excess_vs_bench": oos_perf.get("net_excess_vs_bench")}
        res["promotion"] = {**sl.promotion_verdict(oos_for_gate, prereg),
                            "prereg_id": prereg.get("chain_hash", "")[:12]}
    else:
        res["promotion"] = {"promote": False, "status": "no-prereg",
                            "reasons": [f"无匹配预注册(param_hash {ph[:12]});未预注册的策略仅探索性、不得晋级"],
                            "note": "先 `strategy_backtest.py prereg` 冻结阈值,再 run 才可判 promote"}
    if not args.no_record:
        _record(args, res)
        res["trial_id_recorded"] = True
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        return
    _render(args, res, universe)


def sl_delist():
    try:
        import delisting as dz
        return [r["symbol"] for r in dz.load()]
    except Exception:  # noqa: BLE001
        return []


def _record(args, res):
    import run_audit as ra
    from datetime import datetime
    rec = {"recorded_at": datetime.now().isoformat(timespec="seconds"), "git_sha": (ra.git_sha() or "")[:7],
           "kind": "strategy_backtest", "factor": args.factor, "universe": args.universe,
           "top_frac": args.top_frac, "cost_bps": args.cost_bps, "oos_frac": args.oos_frac,
           "oos_cagr": res["OOS"]["cagr"], "oos_sharpe": res["OOS"]["sharpe"],
           "oos_bootstrap_p": res["oos_bootstrap_p"], "coverage": res["coverage"]["verdict"]}
    rec["param_hash"] = strategy_param_hash(args.factor, args.universe, args.top_frac, args.cost_bps, args.oos_frac)
    rec["promote"] = res.get("promotion", {}).get("promote")
    sl.record_trial(rec)


def cmd_prereg(args):
    """OOS 跑之前冻结晋级阈值(哈希链)。param_hash 与 run 一致 → run 时自动判 promote。"""
    ph = strategy_param_hash(args.factor, args.universe, args.top_frac, args.cost_bps, args.oos_frac)
    spec = {"kind": "prereg", "strategy": "factor-longonly", "factor": args.factor,
            "universe": args.universe, "top_frac": args.top_frac, "cost_bps": args.cost_bps,
            "oos_frac": args.oos_frac, "param_hash": ph,
            "min_material_edge": args.min_material_edge, "max_p": args.max_p,
            "min_net_excess_vs_bench": args.min_net_excess, "alpha": 0.05, "target_power": 0.8}
    r = sl.preregister(spec)
    print(f"✅ 预注册冻结 · prereg_id {r['prereg_id'][:12]} · param_hash {ph[:12]}")
    print(f"   阈值:material_edge≥{args.min_material_edge} · p≤{args.max_p}"
          + (f" · 净超额≥{args.min_net_excess}" if args.min_net_excess is not None else ""))
    print(f"   现在跑 `run --factor {args.factor} --universe {args.universe} ...`(同参)即自动判 promote")


def _pct(x):
    return f"{x:+.2%}" if isinstance(x, (int, float)) else "—"


def _render(args, res, universe):
    print("=" * 66)
    print(f"因子策略回测(OOS-first) · {args.factor} · universe {len(universe)} · {res['rebalances']} 次月度再平衡")
    print("=" * 66)
    print(f"  universe: {', '.join(universe)}")
    for tag, k in (("样本内 IS", "IS"), ("★样本外 OOS", "OOS"), ("全样本(有偏,勿作头条)", "ALL_biased")):
        p = res[k]
        print(f"  {tag:<22} n={p['n']:>2} · CAGR {_pct(p['cagr'])} · 波动 {_pct(p['vol'])} · "
              f"回撤 {_pct(p['maxdd'])} · Sharpe {p['sharpe'] if p['sharpe'] is None else round(p['sharpe'],2)}")
    print(f"\n  OOS 净额显著性(vs 0,启发式 bootstrap): p={res['oos_bootstrap_p']:.3f}"
          + ("(弱证据/不显著)" if res['oos_bootstrap_p'] >= 0.05 else "(有证据)"))
    if res.get("bench"):
        print(f"  相对基准 {res['bench']}(OOS): 策略 {_pct(res['OOS']['cagr'])} − 基准 "
              f"{_pct(res.get('bench_oos_cagr'))} = 净超额 {_pct(res['OOS'].get('net_excess_vs_bench'))}")
    print(f"  覆盖率门禁: {res['coverage']['verdict']}")
    for f in res["coverage"]["flags"]:
        print(f"    ⚠️ {f[:80]}")
    pr = res.get("promotion", {})
    icon = "🟢 晋级" if pr.get("promote") else ("⚪ 无预注册" if pr.get("status") == "no-prereg" else "🔴 不晋级")
    print(f"\n  晋级门禁: {icon}" + (f" · prereg {pr['prereg_id']}" if pr.get("prereg_id") else ""))
    for rsn in pr.get("reasons", []):
        print(f"    · {rsn[:88]}")
    print(f"\n  ⚠️ OOS 才算数(全样本有偏);净额已扣 {args.cost_bps}bps 换手成本;universe 薄+单因子=演示引擎;"
          "覆盖率 coverage-unknown 表示无幸存者分母、不得称'无偏差';预期多为 null。非交易建议。")


def main():
    ap = argparse.ArgumentParser(description="因子策略回测脊柱(OOS-first,PIT安全,零依赖)")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="跑一条因子策略回测(IS/OOS 分报)")
    r.add_argument("--prices", required=True, help="宽表价格 CSV: date,SYM1,...")
    r.add_argument("--factor", default="quality", help="PIT_SAFE 因子(quality/momentum/lowvol/size)")
    r.add_argument("--top-frac", dest="top_frac", type=float, default=0.5)
    r.add_argument("--cost-bps", dest="cost_bps", type=float, default=10.0, help="单边换手成本 bps")
    r.add_argument("--oos-frac", dest="oos_frac", type=float, default=0.4, help="样本外比例(时间轴后段)")
    r.add_argument("--universe", default="price-matrix", help="universe 标识(供覆盖率分母查找)")
    r.add_argument("--benchmark", default="SPY", help="相对基准(须在价格矩阵内,如 SPY);缺则跳过净超额")
    r.add_argument("--no-record", dest="no_record", action="store_true")
    r.add_argument("--json", action="store_true")

    pr = sub.add_parser("prereg", help="OOS 跑前冻结晋级阈值(哈希链);param_hash 与 run 一致")
    pr.add_argument("--factor", default="quality")
    pr.add_argument("--top-frac", dest="top_frac", type=float, default=0.5)
    pr.add_argument("--cost-bps", dest="cost_bps", type=float, default=10.0)
    pr.add_argument("--oos-frac", dest="oos_frac", type=float, default=0.4)
    pr.add_argument("--universe", default="price-matrix")
    pr.add_argument("--min-material-edge", dest="min_material_edge", type=float, default=0.05,
                    help="OOS CAGR 最低门槛(年化)")
    pr.add_argument("--max-p", dest="max_p", type=float, default=0.05, help="OOS 显著性 p 上限")
    pr.add_argument("--min-net-excess", dest="min_net_excess", type=float, default=None,
                    help="相对基准 OOS 净超额最低(可选)")
    args = ap.parse_args()
    {"run": cmd_run, "prereg": cmd_prereg}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
