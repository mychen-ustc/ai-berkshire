#!/usr/bin/env python3
"""因子风险分解（Barra 式风险模型，零外部依赖）。

factor_library 给的是**因子暴露**;本工具补最后一块——**把组合波动分解为
各命名因子的贡献 + 特异(个股独有)风险**,回答"我的风险到底来自哪个因子"。

方法(单期暴露的横截面因子模型,Fama-MacBeth 式)：
  1) 每期做横截面 OLS：个股收益 r_i = Σ_k 暴露_ik × 因子收益_k + 特异_i
     → 解出每期各因子收益(需股票数 N > 因子数 K,否则 X'X 奇异)。
  2) 因子协方差 F = cov(因子收益时序);特异方差 D_i = var(特异残差)。
  3) 组合方差 = (w'X)·F·(w'X)' [因子风险] + Σ w_i²·D_i [特异风险]。
  4) 拆分:因子风险占比 vs 特异;并给每个因子的边际贡献。

用法：
  python3 tools/factor_risk.py analyze --symbols "GOOGL,AXP,KO,COST,NDAQ,MSFT,AAPL,..." \
      --weights "GOOGL=20,AXP=15,..." --period 2y
诚实边界见文末。
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import factor_library as fl  # noqa: E402
import portfolio_optimizer as po  # noqa: E402


# --------------------------------------------------------------------------
# 纯函数（可测）——矩阵与因子风险数学
# --------------------------------------------------------------------------
def _T(M):
    return [list(col) for col in zip(*M)] if M else []


def _matmul(A, B):
    Bt = _T(B)
    return [[sum(a * b for a, b in zip(row, col)) for col in Bt] for row in A]


def ols_factor_returns(X, r):
    """横截面 OLS：因子收益 f = (X'X)⁻¹X'r。X:N×K 暴露, r:N 收益 → (f[K], 残差[N])。纯函数。"""
    Xt = _T(X)
    XtX = _matmul(Xt, X)
    XtX_inv = po.mat_inverse(XtX)                       # 复用 Gauss-Jordan(奇异会抛)
    Xtr = [sum(Xt[k][i] * r[i] for i in range(len(r))) for k in range(len(Xt))]
    f = [sum(XtX_inv[a][b] * Xtr[b] for b in range(len(Xtr))) for a in range(len(XtX_inv))]
    fitted = [sum(X[i][k] * f[k] for k in range(len(f))) for i in range(len(X))]
    resid = [r[i] - fitted[i] for i in range(len(r))]
    return f, resid


def cov_matrix(series):
    """series: T×K(每行一期的 K 维) → K×K 协方差(样本)。纯函数。"""
    T, K = len(series), len(series[0]) if series else 0
    if T < 2:
        return [[0.0] * K for _ in range(K)]
    mean = [sum(series[t][k] for t in range(T)) / T for k in range(K)]
    cov = [[0.0] * K for _ in range(K)]
    for a in range(K):
        for b in range(K):
            cov[a][b] = sum((series[t][a] - mean[a]) * (series[t][b] - mean[b])
                            for t in range(T)) / (T - 1)
    return cov


def decompose(port_exposure, factor_cov, weights, specific_vars, ann=52):
    """组合风险分解。port_exposure:K(组合因子暴露 w'X), factor_cov:K×K, weights:N, specific_vars:N。
    → {factor_var, specific_var, total_var, factor_vol, specific_vol, total_vol,
       factor_pct, per_factor}。方差年化 ×ann。纯函数。"""
    K = len(port_exposure)
    # 因子风险 = e' F e
    Fe = [sum(factor_cov[a][b] * port_exposure[b] for b in range(K)) for a in range(K)]
    factor_var = sum(port_exposure[a] * Fe[a] for a in range(K)) * ann
    # 每因子边际贡献 = e_k × (Fe)_k
    per_factor = [port_exposure[k] * Fe[k] * ann for k in range(K)]
    # 特异风险 = Σ w_i² D_i
    specific_var = sum(weights[i] ** 2 * specific_vars[i] for i in range(len(weights))) * ann
    total_var = factor_var + specific_var
    return {
        "factor_var": factor_var, "specific_var": specific_var, "total_var": total_var,
        "factor_vol": math.sqrt(max(0, factor_var)), "specific_vol": math.sqrt(max(0, specific_var)),
        "total_vol": math.sqrt(max(0, total_var)),
        "factor_pct": (factor_var / total_var) if total_var > 0 else None,
        "per_factor": per_factor,
    }


# --------------------------------------------------------------------------
# 编排（取数 + 估计）
# --------------------------------------------------------------------------
def analyze(symbols, weights, period="2y", freq="weekly"):
    import datalayer as dl
    ppy = {"daily": 252, "weekly": 52, "monthly": 12}[freq]
    # 因子暴露(z 分)
    raw, _ = fl.gather_raw(symbols)
    z = {f: fl.standardize_factor(raw[f]) for f in fl.FACTORS}
    # 仅保留六因子全覆盖的股票(横截面回归要求无缺失)
    keep = [i for i in range(len(symbols)) if all(z[f][i] is not None for f in fl.FACTORS)]
    if len(keep) <= len(fl.FACTORS):
        raise SystemExit(f"可用股票 {len(keep)} ≤ 因子数 {len(fl.FACTORS)}——"
                         f"横截面回归需 N>K(股票数>因子数),请扩大 universe(≥~10 只全覆盖美股)")
    ksyms = [symbols[i] for i in keep]
    X = [[z[f][i] for f in fl.FACTORS] for i in keep]    # N×K 暴露
    # 收益矩阵
    px = {}
    for s in ksyms:
        try:
            px[s] = [p[1] for p in dl.fetch_history(s, freq=freq, period=period)["points"]]
        except Exception:  # noqa: BLE001
            pass
    have = [s for s in ksyms if s in px and len(px[s]) > 12]
    ml = min(len(px[s]) for s in have)
    rets = {s: [px[s][-ml:][t] / px[s][-ml:][t - 1] - 1 for t in range(1, ml)] for s in have}
    idx = [ksyms.index(s) for s in have]
    Xh = [X[ksyms.index(s)] for s in have]
    # 每期横截面 OLS → 因子收益时序 + 残差时序
    fret_series, resid_series = [], []
    for t in range(ml - 1):
        r = [rets[s][t] for s in have]
        try:
            f, resid = ols_factor_returns(Xh, r)
        except Exception:  # noqa: BLE001
            continue
        fret_series.append(f)
        resid_series.append(resid)
    if len(fret_series) < 12:
        raise SystemExit("有效期数不足,无法估计因子协方差")
    F = cov_matrix(fret_series)
    # 特异方差(残差按股票)
    nS = len(have)
    spec = []
    for i in range(nS):
        col = [resid_series[t][i] for t in range(len(resid_series))]
        m = sum(col) / len(col)
        spec.append(sum((x - m) ** 2 for x in col) / (len(col) - 1))
    # 组合权重(仅 have 内归一) + 组合因子暴露 w'X
    w_raw = {s: weights.get(s, 0.0) for s in have}
    tot = sum(w_raw.values()) or 1.0
    w = [w_raw[s] / tot for s in have]
    port_exp = [sum(w[i] * Xh[i][k] for i in range(nS)) for k in range(len(fl.FACTORS))]
    dec = decompose(port_exp, F, w, spec, ann=ppy)
    return {"symbols_used": have, "factors": fl.FACTORS, "port_exposure": port_exp,
            "decomp": dec, "n_periods": len(fret_series)}


def render(res):
    d = res["decomp"]
    print("=" * 62)
    print(f"因子风险分解 · {len(res['symbols_used'])}只 · {res['n_periods']}期 · Barra式")
    print("=" * 62)
    print(f"  组合年化波动(模型): {d['total_vol']:.1%}")
    print(f"    ├─ 因子风险: {d['factor_vol']:.1%}  占 {d['factor_pct']:.0%}" if d['factor_pct'] is not None else "")
    print(f"    └─ 特异风险: {d['specific_vol']:.1%}  占 {(1 - d['factor_pct']):.0%}" if d['factor_pct'] is not None else "")
    print(f"\n  各因子风险贡献(方差,年化;负=对冲降险):")
    pf = list(zip([fl.FACTOR_CN[f] for f in res["factors"]], res["port_exposure"], d["per_factor"]))
    for name, exp, contrib in sorted(pf, key=lambda x: -abs(x[2])):
        share = contrib / d["factor_var"] if d["factor_var"] else 0
        bar = "█" * min(20, int(abs(share) * 20))
        print(f"    {name:<5} 暴露{exp:>+5.2f} · 方差贡献 {contrib:>+.4f} ({share:>+4.0%}) {bar}")
    print(f"\n  → 因子风险占 {d['factor_pct']:.0%}=系统性(可对冲/择时),特异占 {(1 - d['factor_pct']):.0%}=选股独有。"
          if d['factor_pct'] is not None else "")
    print("  ⚠️ 单期暴露的横截面模型;因子收益由 OLS 估计,需 N>K 且暴露稳定;"
          "美股(因子覆盖)为主;α/β/协方差随窗口漂移;不含黑天鹅。")


def _parse_w(spec):
    w = {}
    for part in (spec or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            w[k.strip()] = float(v)
    return w


def main():
    ap = argparse.ArgumentParser(description="因子风险分解:因子风险vs特异+各因子贡献(Barra式,零依赖)")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("analyze", help="分解组合风险")
    a.add_argument("--symbols", required=True, help="估计universe(≥~10只全覆盖美股)")
    a.add_argument("--weights", required=True)
    a.add_argument("--period", default="2y", choices=["1y", "2y", "5y", "10y", "max"])
    a.add_argument("--freq", default="weekly", choices=["daily", "weekly", "monthly"])
    args = ap.parse_args()
    if args.cmd == "analyze":
        syms = [s.strip() for s in args.symbols.split(",") if s.strip()]
        render(analyze(syms, _parse_w(args.weights), args.period, args.freq))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
