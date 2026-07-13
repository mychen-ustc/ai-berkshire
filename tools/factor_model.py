#!/usr/bin/env python3
"""多因子风险模型（零外部依赖，仅 stdlib）。

回答机构风控的核心问题：**"这份分散是真的吗？超额是 alpha 还是 beta？风险压在哪个共同因子上？"**

方法（价量/收益驱动，无需横截面基本面库）：
  ① 收益相关矩阵的 PCA（纯 stdlib Jacobi 特征分解）——
     有效独立因子数（participation ratio）、PC1/PC2/PC3 方差占比、PC1 主导因子载荷；
     N_eff ≪ 名义持仓数 或 PC1 占比过高 ⇒ **伪分散**（名义分散实则押同一因子）。
  ② 系统性 vs 特质：组合对基准的 beta（多少收益是市场 beta）。
  ③ 特征因子倾斜（价量可算）：动量(12-1月) / 波动 的横截面 z 分与组合加权倾斜。

诚实边界：PC 是**统计因子**（需事后解读，通常 PC1≈市场）；价值/质量/成长/规模因子需
横截面基本面数据，本版本未接入（见 P4 路线图）。窗口短则相关性/特征值不稳。

用法：
  python3 tools/factor_model.py analyze --from-datalayer "VOO,AAPL,GOOGL,BRK.B,COST,KO,AXP,603986,9660.HK,06082.HK" \
      --weights "VOO=14,AAPL=12,..." --benchmark VOO --freq weekly --period 2y
  python3 tools/factor_model.py analyze --from-ledger reports/private/xxx.csv --fx "USD=1,HKD=0.128,CNY=0.14"
  python3 tools/factor_model.py analyze --prices data/wide.csv --benchmark SPY
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portfolio_risk as pr  # noqa: E402  复用：build_matrix / pct_returns / correlation / ann_vol / beta


# --------------------------------------------------------------------------
# 线性代数：对称矩阵 Jacobi 特征分解（纯 stdlib）
# --------------------------------------------------------------------------
def jacobi_eigen(A, sweeps=200, tol=1e-12):
    """对称矩阵 A → (特征值降序, 特征向量列表)。eigenvectors[k] 为第 k 个特征向量。"""
    n = len(A)
    a = [row[:] for row in A]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(sweeps):
        off = math.sqrt(sum(a[i][j] ** 2 for i in range(n) for j in range(i + 1, n)))
        if off < tol:
            break
        for p in range(n):
            for q in range(p + 1, n):
                if abs(a[p][q]) < 1e-300:
                    continue
                theta = (a[q][q] - a[p][p]) / (2 * a[p][q])
                t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1))
                c = 1.0 / math.sqrt(t * t + 1)
                s = t * c
                for k in range(n):                       # 右乘 J
                    akp, akq = a[k][p], a[k][q]
                    a[k][p] = c * akp - s * akq
                    a[k][q] = s * akp + c * akq
                for k in range(n):                       # 左乘 Jᵀ
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k] = c * apk - s * aqk
                    a[q][k] = s * apk + c * aqk
                for k in range(n):                       # 累积特征向量
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p] = c * vkp - s * vkq
                    v[k][q] = s * vkp + c * vkq
    eig = [a[i][i] for i in range(n)]
    vecs = [[v[i][j] for i in range(n)] for j in range(n)]  # vecs[j] = 第 j 列 = 第 j 个特征向量
    order = sorted(range(n), key=lambda i: -eig[i])
    return [eig[i] for i in order], [vecs[i] for i in order]


# --------------------------------------------------------------------------
# 相关矩阵 + PCA 指标
# --------------------------------------------------------------------------
def corr_matrix(rets, syms, n):
    return [[pr.correlation(rets[a][:n], rets[b][:n]) for b in syms] for a in syms]


def pca_metrics(corr):
    """→ dict：特征值、方差占比、有效独立因子数、PC1/PC2 载荷。"""
    n = len(corr)
    eig, vecs = jacobi_eigen(corr)
    eig = [max(e, 0.0) for e in eig]           # 数值噪声可能产生极小负值，截断
    total = sum(eig) or 1.0                     # 相关矩阵迹 = n
    var_ratio = [e / total for e in eig]
    n_eff = (total ** 2) / sum(e * e for e in eig) if any(eig) else float("nan")
    return {"eigenvalues": eig, "var_ratio": var_ratio, "n_eff": n_eff,
            "pc1": vecs[0], "pc2": vecs[1] if n > 1 else None}


def sign_align(vec):
    """特征向量符号不定：翻到"多数为正"，便于解读为共同方向。"""
    if sum(1 for x in vec if x < 0) > len(vec) / 2:
        return [-x for x in vec]
    return vec


# --------------------------------------------------------------------------
# 特征因子（价量可算）：动量 / 波动 / beta
# --------------------------------------------------------------------------
def zscores(vals):
    xs = [v for v in vals if v is not None]
    if len(xs) < 2:
        return [0.0 for _ in vals]
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs)) or 1.0
    return [((v - m) / sd if v is not None else 0.0) for v in vals]


def momentum_12_1(prices):
    """12-1 月动量：约 252 交易日前 → 21 日前（周线按比例），剔除最近1月反转。"""
    n = len(prices)
    lo = n - 1 - min(n - 1, 52 if n > 60 else max(1, n // 5))   # 频率无关的稳健近似
    hi = n - 1 - min(n - 1, 4 if n > 12 else 1)
    if lo >= hi or prices[lo] == 0:
        return None
    return prices[hi] / prices[lo] - 1


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def analyze(args):
    dates, cols, auto_w, label = pr.build_matrix(args)
    syms = list(cols)
    if len(syms) < 2 or len(dates) < 3:
        raise SystemExit(f"标的或周期不足（{len(syms)} 只 / {len(dates)} 期）：因子模型需 ≥2 只、≥3 期")
    ppy = {"daily": 252, "weekly": 52, "monthly": 12}.get(args.freq) or pr.periods_per_year(dates)

    if auto_w:
        w = {k: v for k, v in auto_w.items() if k in cols}
    elif args.weights:
        w = pr.parse_weights(args.weights, syms)
    else:
        w = {s: 1 / len(syms) for s in syms}
    tot = sum(w.values()) or 1.0
    w = {s: w.get(s, 0.0) / tot for s in syms}

    rets = {s: pr.pct_returns(cols[s]) for s in syms}
    n = min(len(r) for r in rets.values())

    corr = corr_matrix(rets, syms, n)
    pca = pca_metrics(corr)

    print("=" * 68)
    print(f"多因子风险模型 · {label} · {len(syms)} 只 · {n} 期收益 · 年化因子 {ppy}")
    print("=" * 68)

    # ① 风险集中度 / 伪分散
    N = len(syms)
    neff = pca["n_eff"]
    pc1 = pca["var_ratio"][0] * 100
    pc123 = sum(pca["var_ratio"][:3]) * 100
    print("\n① 风险集中度（相关矩阵 PCA）:")
    print(f"    名义持仓数:          {N}")
    print(f"    有效独立因子数:      {neff:.2f}   ← 真正独立的「赌注」数")
    print(f"    PC1 方差占比:        {pc1:.1f}%   ← 单一共同因子的主导度")
    print(f"    PC1–3 累计占比:      {pc123:.1f}%")
    ratio = neff / N if N else 1.0
    if pc1 >= 50 or ratio < 0.5:
        verdict = "🔴 伪分散：名义分散，实则高度押注同一共同因子"
    elif pc1 >= 38 or ratio < 0.65:
        verdict = "🟡 中度集中：存在明显共同因子暴露"
    else:
        verdict = "🟢 分散较真实：独立因子数接近名义持仓数"
    print(f"    判定:                {verdict}")

    # PC1 主导因子载荷（谁在共同驱动）
    pc1v = sign_align(pca["pc1"])
    loads = sorted(zip(syms, pc1v), key=lambda x: -abs(x[1]))
    print("\n    PC1 主导因子载荷（|载荷|越大越受该共同因子驱动，通常 PC1≈市场）:")
    for s, l in loads[:min(6, N)]:
        bar = "█" * int(abs(l) * 24)
        print(f"      {s:<10}{l:+.2f} {bar}")

    # ② 系统性 vs 特质（beta）
    if args.benchmark and args.benchmark in cols:
        bench = pr.pct_returns(cols[args.benchmark])[:n]
        port = [sum(w[s] * rets[s][i] for s in syms) for i in range(n)]
        b = pr.beta(port, bench)
        r = pr.correlation(port, bench)
        print(f"\n② 系统性暴露（对基准 {args.benchmark}）:")
        print(f"    组合 Beta:           {b:.2f}   (R={r:.2f}, R²={r * r:.2f} 的收益由基准解释)")

    # ③ 特征因子倾斜（价量可算）
    mom = {s: momentum_12_1(cols[s]) for s in syms}
    vol = {s: pr.ann_vol(rets[s][:n], ppy) for s in syms}
    mom_z = dict(zip(syms, zscores([mom[s] for s in syms])))
    vol_z = dict(zip(syms, zscores([vol[s] for s in syms])))
    port_mom = sum(w[s] * mom_z[s] for s in syms)
    port_vol = sum(w[s] * vol_z[s] for s in syms)
    print("\n③ 特征因子倾斜（组合加权 z 分，横截面为本组合；>0 超配该因子）:")
    print(f"    动量因子(12-1月):    {port_mom:+.2f}   {'偏动量' if port_mom > 0.15 else ('偏反转' if port_mom < -0.15 else '中性')}")
    print(f"    波动因子:            {port_vol:+.2f}   {'偏高波' if port_vol > 0.15 else ('偏低波' if port_vol < -0.15 else '中性')}")

    print("\n④ 诚实边界:")
    print("    · PC 为统计因子，需事后解读（PC1 常≈市场，PC2/3 可能是行业/地域/风格）。")
    print("    · 价值/质量/成长/规模因子需横截面基本面库，本版本未接入（见 P4 路线图）。")
    print("    · 相关性/特征值在短窗口不稳；新股截断会放大 PC1 主导度。")

    return {"n": N, "n_eff": neff, "pc1_pct": pc1, "pc123_pct": pc123,
            "pc1_loadings": dict(zip(syms, pc1v)), "verdict": verdict,
            "port_momentum_z": port_mom, "port_vol_z": port_vol}


def main():
    ap = argparse.ArgumentParser(description="多因子风险模型（PCA 伪分散检测 + beta + 特征因子倾斜，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("analyze", help="分析组合的因子暴露与风险集中度")
    src = a.add_mutually_exclusive_group(required=True)
    src.add_argument("--prices", help="宽表价格 CSV: date,SYM1,SYM2,...")
    src.add_argument("--from-datalayer", help='符号列表 "VOO,AAPL,600519,0700.HK"')
    src.add_argument("--from-ledger", help="交易账本 CSV")
    a.add_argument("--fx", help='多币种权重换算 "USD=1,HKD=0.128,CNY=0.14"（--from-ledger 用）')
    a.add_argument("--period", default="2y", choices=["1y", "2y", "5y", "10y", "max"])
    a.add_argument("--freq", default="weekly", choices=["daily", "weekly", "monthly"])
    a.add_argument("--weights", help='如 "VOO=14,AAPL=12,..."；缺省等权/按账本市值')
    a.add_argument("--benchmark", help="系统性暴露基准列名（价格表/符号之一）")
    a.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd != "analyze":
        ap.print_help()
        return
    out = analyze(args)
    if args.json:
        import json
        print("\n" + json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
