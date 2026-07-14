#!/usr/bin/env python3
"""组合优化器（P2，零外部依赖）。

价值投资约束下的权重建议——不是黑箱均值方差最优，而是"透明、可解释 + 硬约束"：
  - 逆波动(风险平价近似)：波动越低权重越高，让各标的风险贡献更均衡。
  - 等权：朴素基准。
  - IPS 单一持仓上限硬约束：超限则封顶并把超出部分按比例再分配（迭代收敛）。

波动经数据层前复权历史计算(float)；上限默认读 config/investment-policy.json。
与 portfolio_risk(诊断) 互补：risk 是"体检"，optimizer 是"开方"。

用法：
  python3 tools/portfolio_optimizer.py optimize --from-datalayer "600519,0700.HK,AAPL,VOO" \
      --method inverse-vol --period 5y
"""
import argparse
import json
import math
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY = os.path.join(ROOT, "config", "investment-policy.json")


def inverse_vol_weights(vols):
    """w_i = (1/vol_i) / Σ(1/vol)。波动低者权重高（风险平价近似）。"""
    inv = {k: 1.0 / v for k, v in vols.items() if v > 0}
    s = sum(inv.values())
    return {k: x / s for k, x in inv.items()} if s else {}


def equal_weights(keys):
    n = len(keys)
    return {k: 1.0 / n for k in keys} if n else {}


def enforce_caps(weights, cap):
    """迭代：超上限者封顶，超出部分按现权重比例再分配给未超限者，直至收敛。"""
    w = dict(weights)
    for _ in range(100):
        over = {k: v for k, v in w.items() if v > cap + 1e-12}
        if not over:
            break
        excess = sum(v - cap for v in over.values())
        for k in over:
            w[k] = cap
        under = {k: v for k, v in w.items() if v < cap - 1e-12}
        tot = sum(under.values())
        if tot <= 0:
            break  # 无法再分配（cap 过小 / 名额不足）
        for k in under:
            w[k] += excess * (w[k] / tot)
    return w


def ann_vol_from_prices(prices, ppy=52):
    rets = [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]
    return statistics.pstdev(rets) * math.sqrt(ppy) if len(rets) > 1 else 0.0


# --------------------------------------------------------------------------
# 协方差 + 矩阵求逆 + 最小方差 / 风险平价（纯函数，零依赖）
# --------------------------------------------------------------------------
def cov_matrix(rets, syms, n):
    means = {s: sum(rets[s][:n]) / n for s in syms}
    return [[sum((rets[a][k] - means[a]) * (rets[b][k] - means[b]) for k in range(n)) / n
             for b in syms] for a in syms]


def mat_inverse(A):
    """Gauss-Jordan 求逆（纯 stdlib）。奇异则抛错。"""
    n = len(A)
    M = [[float(A[i][j]) for j in range(n)] + [1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-14:
            raise ValueError("协方差矩阵近奇异，无法求逆（标的高度共线/周期不足）")
        M[col], M[piv] = M[piv], M[col]
        d = M[col][col]
        M[col] = [x / d for x in M[col]]
        for r in range(n):
            if r != col:
                f = M[r][col]
                M[r] = [a - f * b for a, b in zip(M[r], M[col])]
    return [row[n:] for row in M]


def min_variance_weights(cov):
    """w ∝ Σ⁻¹·1，长仓：负权重截零后归一（长仓近似）。"""
    n = len(cov)
    inv = mat_inverse(cov)
    raw = [sum(inv[i][j] for j in range(n)) for i in range(n)]
    clipped = [max(0.0, x) for x in raw]
    s = sum(clipped)
    return [x / s for x in clipped] if s > 0 else [1.0 / n] * n


def risk_parity_weights(cov, iters=10000, tol=1e-12):
    """等风险贡献(ERC)：平方根阻尼不动点 w_i ← w_i·√(b_i/RC_i)（稳定收敛，b_i=1/n）。"""
    n = len(cov)
    w = [1.0 / n] * n
    b = 1.0 / n
    for _ in range(iters):
        mrc = [sum(cov[i][j] * w[j] for j in range(n)) for i in range(n)]  # 边际风险贡献
        rc = [w[i] * mrc[i] for i in range(n)]                            # 风险贡献
        nw = [w[i] * math.sqrt(b / rc[i]) if rc[i] > 1e-18 else w[i] for i in range(n)]
        s = sum(nw)
        nw = [x / s for x in nw]
        if max(abs(nw[i] - w[i]) for i in range(n)) < tol:
            return nw
        w = nw
    return w


def _ips_cap(path=POLICY):
    if not os.path.exists(path):
        return None
    pol = json.load(open(path, encoding="utf-8"))
    c = pol.get("position_limits", {}).get("single_name_max_pct")
    return c / 100.0 if c is not None else None


def optimize(args):
    import datalayer as dl
    syms = [s.strip() for s in args.from_datalayer.split(",") if s.strip()]
    # 取历史 → 交集对齐(按 ISO 周) → 波动
    from portfolio_risk import _align_histories
    hists = {s: dl.fetch_history(s, freq="weekly", period=args.period)["points"] for s in syms}
    _, cols = _align_histories(hists, "weekly")
    vols = {s: ann_vol_from_prices(cols[s]) for s in cols if len(cols[s]) > 2}
    if not vols:
        raise SystemExit("可用历史不足以计算波动")
    syms_v = list(vols)
    if args.method in ("min-variance", "risk-parity"):
        rets = {s: [cols[s][i] / cols[s][i - 1] - 1 for i in range(1, len(cols[s]))] for s in syms_v}
        n = min(len(rets[s]) for s in syms_v)
        cov = cov_matrix(rets, syms_v, n)
        wl = min_variance_weights(cov) if args.method == "min-variance" else risk_parity_weights(cov)
        base = {s: wl[i] for i, s in enumerate(syms_v)}
    elif args.method == "inverse-vol":
        base = inverse_vol_weights(vols)
    else:
        base = equal_weights(syms_v)
    cap = args.cap if args.cap is not None else _ips_cap(args.policy)
    final = enforce_caps(base, cap) if cap else base
    print("=" * 62)
    print(f"组合优化 · {args.method} · IPS 单一上限 {cap*100:.0f}%" if cap else f"组合优化 · {args.method} · 无上限")
    print("=" * 62)
    print(f"  {'标的':<10}{'年化波动':>10}{'原始权重':>12}{'上限后权重':>12}")
    for s in sorted(final, key=lambda x: -final[x]):
        capped = "  ←封顶" if cap and abs(final[s] - cap) < 1e-9 and base[s] > cap else ""
        print(f"  {s:<10}{vols[s]*100:>9.1f}%{base[s]*100:>11.1f}%{final[s]*100:>11.1f}%{capped}")
    hhi = sum(v * v for v in final.values())
    print(f"\n  HHI {hhi:.3f} · 有效持仓数 {1/hhi:.2f} · 权重和 {sum(final.values()):.3f}")
    print("  说明：逆波动让低波资产权重更高、风险贡献更均衡；这是纪律化配置，非收益最大化。")


def main():
    ap = argparse.ArgumentParser(description="组合优化器：逆波动/等权 + IPS 上限（P2，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    o = sub.add_parser("optimize", help="给出建议权重")
    o.add_argument("--from-datalayer", required=True, help='"600519,0700.HK,AAPL,VOO"')
    o.add_argument("--method", choices=["inverse-vol", "equal", "min-variance", "risk-parity"], default="inverse-vol")
    o.add_argument("--period", default="5y", choices=["1y", "2y", "5y", "10y", "max"])
    o.add_argument("--cap", type=float, help="单一上限(0-1)，默认读 IPS")
    o.add_argument("--policy", default=POLICY)
    args = ap.parse_args()
    if args.cmd == "optimize":
        optimize(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
