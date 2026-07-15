#!/usr/bin/env python3
"""量化五指标：Alpha / Beta / 夏普 / 最大回撤 / 信息比率（零外部依赖）。

机构衡量"收益到底好不好"的五个核心指标——脱离风险谈收益是耍流氓：
  · Beta(β)     —— 对市场的敏感度。β=1 同涨跌、<1 防御、>1 进攻。
  · Alpha(α)    —— 剔除 β 暴露后的超额(詹森 alpha)。>0 才是真本事、非靠加杠杆。
  · 夏普比率     —— 每单位总风险赚多少超额。>1 良好、>2 优秀、<0.5 弱。
  · 最大回撤     —— 峰值到谷底最大跌幅。复利杀手,低回撤才能长期活。
  · 信息比率(IR) —— 相对基准的超额 / 跟踪误差。衡量主动管理"技艺"。>0.5 良好、>1 优秀。

对齐口径:简单收益(算术),周频年化因子 52。基准默认 SPY,无风险利率默认 4%(可改)。

用法：
  python3 tools/quant_metrics.py eval --from-datalayer "GOOGL=16,MTUM=14,VOO=14,..." \
      --benchmark SPY --period 2y --freq weekly --rf 0.04
"""
import argparse
import math

PPY = {"daily": 252, "weekly": 52, "monthly": 12}


# --------------------------------------------------------------------------
# 纯函数（可测）——五指标
# --------------------------------------------------------------------------
def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs, sample=True):
    n = len(xs)
    if n < 2:
        return 0.0
    m = _mean(xs)
    d = n - 1 if sample else n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / d)


def beta(port, bench):
    """β = Cov(p,b)/Var(b)。纯函数。"""
    n = min(len(port), len(bench))
    if n < 2:
        return None
    p, b = port[-n:], bench[-n:]
    mp, mb = _mean(p), _mean(b)
    cov = sum((p[i] - mp) * (b[i] - mb) for i in range(n)) / (n - 1)
    varb = sum((x - mb) ** 2 for x in b) / (n - 1)
    return cov / varb if varb else None


def alpha_annual(port, bench, rf_annual, ppy):
    """詹森 α(年化) = (E[Rp]−rf) − β(E[Rm]−rf)，逐期后×ppy。纯函数。"""
    b = beta(port, bench)
    if b is None:
        return None
    rf_p = rf_annual / ppy
    a_period = (_mean(port) - rf_p) - b * (_mean(bench) - rf_p)
    return a_period * ppy


def sharpe(rets, rf_annual, ppy):
    """夏普 = (E[R]−rf)/σ，年化。纯函数。"""
    sd = _std(rets)
    if sd == 0:
        return None
    rf_p = rf_annual / ppy
    return (_mean(rets) - rf_p) / sd * math.sqrt(ppy)


def max_drawdown(rets):
    """由简单收益序列构权益曲线，算最大回撤(负数)。纯函数。"""
    eq = 1.0
    peak = 1.0
    mdd = 0.0
    for r in rets:
        eq *= (1 + r)
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    return mdd


def tracking_error(port, bench, ppy):
    """跟踪误差 = std(主动收益)年化。纯函数。"""
    n = min(len(port), len(bench))
    active = [port[-n:][i] - bench[-n:][i] for i in range(n)]
    return _std(active) * math.sqrt(ppy)


def information_ratio(port, bench, ppy):
    """IR = 年化超额 / 跟踪误差。纯函数。"""
    n = min(len(port), len(bench))
    active = [port[-n:][i] - bench[-n:][i] for i in range(n)]
    te = _std(active)
    if te == 0:
        return None
    return _mean(active) / te * math.sqrt(ppy)


def evaluate(port, bench, rf_annual=0.04, ppy=52):
    """五指标 + 定性评价。纯函数。"""
    b = beta(port, bench)
    a = alpha_annual(port, bench, rf_annual, ppy)
    sh = sharpe(port, rf_annual, ppy)
    mdd = max_drawdown(port)
    ir = information_ratio(port, bench, ppy)
    te = tracking_error(port, bench, ppy)
    ann_ret = ((1 + _mean(port)) ** ppy - 1)
    return {
        "beta": b, "alpha_annual": a, "sharpe": sh, "max_drawdown": mdd,
        "information_ratio": ir, "tracking_error": te, "ann_return": ann_ret,
        "verdicts": {
            "beta": _v_beta(b), "alpha": _v_alpha(a), "sharpe": _v_sharpe(sh),
            "max_drawdown": _v_mdd(mdd), "information_ratio": _v_ir(ir),
        },
    }


def _v_beta(b):
    if b is None:
        return "—"
    if b < 0.8:
        return "🛡️ 防御(低于市场波动)"
    if b > 1.2:
        return "⚡ 进攻(放大市场波动)"
    return "≈ 市场同步"


def _v_alpha(a):
    if a is None:
        return "—"
    if a > 0.03:
        return "✅ 显著正α(真超额)"
    if a > 0:
        return "🟢 微正α"
    return "🔴 负α(未跑赢β应得)"


def _v_sharpe(s):
    if s is None:
        return "—"
    if s > 2:
        return "✅ 优秀(>2)"
    if s > 1:
        return "🟢 良好(>1)"
    if s > 0.5:
        return "🟡 一般"
    return "🔴 弱(<0.5)"


def _v_mdd(m):
    if m is None:
        return "—"
    if m > -0.15:
        return "🟢 可控(<15%)"
    if m > -0.30:
        return "🟡 中等"
    return "🔴 大(>30%)"


def _v_ir(ir):
    if ir is None:
        return "—"
    if ir > 1:
        return "✅ 优秀(>1，主动技艺强)"
    if ir > 0.5:
        return "🟢 良好(>0.5)"
    if ir > 0:
        return "🟡 微正"
    return "🔴 跑输基准"


# --------------------------------------------------------------------------
# 数据层集成
# --------------------------------------------------------------------------
def _simple_rets(prices):
    return [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]


def evaluate_from_datalayer(weights, benchmark, period="2y", freq="weekly", rf=0.04):
    """取组合各标的与基准价格 → 组合加权简单收益 vs 基准 → 五指标。"""
    import datalayer as dl
    ppy = PPY[freq]
    syms = list(weights)
    px = {}
    for s in syms + [benchmark]:
        try:
            pts = dl.fetch_history(s, freq=freq, period=period)["points"]
            px[s] = [p[1] for p in pts]
        except Exception:  # noqa: BLE001
            pass
    have = [s for s in syms if s in px and len(px[s]) > 10]
    if benchmark not in px or not have:
        raise SystemExit("取数不足(基准或成分缺失)")
    ml = min(len(px[s]) for s in have + [benchmark])
    rets = {s: _simple_rets(px[s][-ml:]) for s in have + [benchmark]}
    tot = sum(weights[s] for s in have) or 1.0
    w = {s: weights[s] / tot for s in have}
    n = ml - 1
    port = [sum(w[s] * rets[s][i] for s in have) for i in range(n)]
    res = evaluate(port, rets[benchmark], rf, ppy)
    res["benchmark"] = benchmark
    res["n_periods"] = n
    res["freq"] = freq
    res["covered"] = have
    return res


def _parse_weights(spec):
    w = {}
    for part in spec.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            w[k.strip()] = float(v)
    return w


def render(res):
    print("=" * 62)
    print(f"量化五指标 · vs {res['benchmark']} · {res['n_periods']} 期({res['freq']}) · rf {res.get('rf', 0.04):.0%}")
    print("=" * 62)
    v = res["verdicts"]
    def fmt(x, pct=False):
        return "—" if x is None else (f"{x:+.1%}" if pct else f"{x:+.2f}")
    print(f"  Beta(β)     {fmt(res['beta']):>8}   {v['beta']}")
    print(f"  Alpha(年化) {fmt(res['alpha_annual'], True):>8}   {v['alpha']}")
    print(f"  夏普比率     {fmt(res['sharpe']):>8}   {v['sharpe']}")
    print(f"  最大回撤     {fmt(res['max_drawdown'], True):>8}   {v['max_drawdown']}")
    print(f"  信息比率(IR) {fmt(res['information_ratio']):>8}   {v['information_ratio']}")
    print(f"  (跟踪误差 {fmt(res['tracking_error'], True)} · 组合年化 {fmt(res['ann_return'], True)})")
    print(f"\n  ⚠️ 基于历史区间、简单收益、单一基准；α/β 随窗口漂移；不含黑天鹅。"
          f"指标是结果的体检、非未来的保证。")


def main():
    ap = argparse.ArgumentParser(description="量化五指标:Alpha/Beta/夏普/最大回撤/信息比率(零依赖)")
    sub = ap.add_subparsers(dest="cmd")
    e = sub.add_parser("eval", help="评估组合五指标")
    e.add_argument("--from-datalayer", required=True, help='"GOOGL=16,MTUM=14,..."')
    e.add_argument("--benchmark", default="SPY")
    e.add_argument("--period", default="2y", choices=["1y", "2y", "5y", "10y", "max"])
    e.add_argument("--freq", default="weekly", choices=["daily", "weekly", "monthly"])
    e.add_argument("--rf", type=float, default=0.04, help="无风险年利率(默认4%)")
    args = ap.parse_args()
    if args.cmd == "eval":
        res = evaluate_from_datalayer(_parse_weights(args.from_datalayer), args.benchmark,
                                      args.period, args.freq, args.rf)
        res["rf"] = args.rf
        render(res)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
