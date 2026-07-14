#!/usr/bin/env python3
"""尾部与流动性风险 + 压力测试引擎（零外部依赖，仅 stdlib）。P4-3 机构级风控。

portfolio_risk 给"常态"风险(波动/回撤/相关性)；本工具补"极端与生存"风险：
  ① VaR/CVaR：历史法 + 参数法(含 Acklam 逆正态,不依赖 scipy)，95%/99%，日/周/期口径。
  ② 压力测试引擎：历史危机情景(beta 映射)、假设情景(市场/单一持仓归零)、反向压力测试(多大冲击击穿风险预算)。
  ③ 流动性风险(--from-ledger)：按 ADV 估清算天数与变现难度。

诚实边界：VaR 只是"正常极端"、**不含黑天鹅**(2008/2020 实际远超);历史情景用 beta 线性映射、
低估非线性与相关性跳升;流动性用 ADV 近似。风控是生存底线、非收益预测；VaR 不替代回撤/流动性/尾部情景。

用法：
  python3 tools/tail_risk.py analyze --from-ledger data/portfolio/transactions.csv --fx "USD=1,HKD=0.128,CNY=0.14" --benchmark VOO
  python3 tools/tail_risk.py analyze --from-datalayer "VOO,AAPL,GOOGL,BRK.B" --weights "VOO=40,AAPL=20,GOOGL=20,BRK.B=20" --benchmark VOO
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portfolio_risk as pr  # noqa: E402


# --------------------------------------------------------------------------
# 逆正态（Acklam 有理逼近）+ VaR/CVaR（纯函数）
# --------------------------------------------------------------------------
def norm_ppf(p):
    """标准正态逆 CDF（Acklam 算法，|误差|<1.15e-9）。"""
    if not 0 < p < 1:
        raise ValueError("p 必须在 (0,1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


def var_cvar(returns, alpha=0.95):
    """→ 单期损失（正数）：历史 VaR、历史 CVaR(ES)、参数 VaR。alpha=置信度。"""
    n = len(returns)
    if n < 5:
        return None
    sr = sorted(returns)
    k = max(0, int(math.floor((1 - alpha) * n)) - 1)     # 下尾分位索引
    hist_var = -sr[k]
    tail = sr[:k + 1]
    hist_cvar = -sum(tail) / len(tail)
    mu = sum(returns) / n
    sd = math.sqrt(sum((r - mu) ** 2 for r in returns) / n)
    param_var = -(mu - norm_ppf(alpha) * sd)
    return {"hist_var": hist_var, "hist_cvar": hist_cvar, "param_var": param_var, "n": n}


# --------------------------------------------------------------------------
# 压力测试（纯函数）
# --------------------------------------------------------------------------
def stress_market(beta, shocks=(-0.10, -0.20, -0.35)):
    """历史/假设市场冲击 → 组合近似损失（beta 线性映射，忽略 alpha 与非线性）。"""
    return [{"shock": s, "port_impact": round(beta * s, 4)} for s in shocks]


def reverse_stress(beta, loss_targets=(-0.15, -0.20, -0.30)):
    """反向压力：要造成 X% 组合损失，需多大市场冲击。"""
    out = []
    for lt in loss_targets:
        out.append({"port_loss": lt, "implied_market": round(lt / beta, 4) if beta else None})
    return out


def single_name_shock(weights, drops=(-0.5, -1.0)):
    """单一最大持仓下跌/归零对组合的冲击。"""
    if not weights:
        return []
    top = max(weights, key=lambda k: weights[k])
    w = weights[top]
    return [{"name": top, "weight": w, "drop": d, "port_impact": round(w * d, 4)} for d in drops]


def days_to_liquidate(position_value, adv_value, participation=0.2):
    """清算天数 = 持仓市值 / (参与率 × 日均成交额)。adv_value 与 position_value 同币种。"""
    denom = participation * adv_value
    return (position_value / denom) if denom else float("inf")


# --------------------------------------------------------------------------
# 主流程（复用 portfolio_risk 的数据装载）
# --------------------------------------------------------------------------
def analyze(args):
    dates, cols, auto_w, label = pr.build_matrix(args)
    if not cols or len(dates) < 6:
        raise SystemExit(f"周期不足（{len(dates)} 期），无法估计尾部风险")
    ppy = {"daily": 252, "weekly": 52, "monthly": 12}.get(args.freq) or pr.periods_per_year(dates)
    freq_cn = {252: "日", 52: "周", 12: "月"}.get(ppy, "期")

    syms = list(cols)
    if auto_w:
        tot = sum(auto_w.values()) or 1.0
        weights = {k: v / tot for k, v in auto_w.items() if k in cols}
    elif args.weights:
        weights = pr.parse_weights(args.weights, syms)
    else:
        weights = {s: 1 / len(syms) for s in syms}

    rets = {s: pr.pct_returns(cols[s]) for s in weights}
    n = min(len(r) for r in rets.values())
    port = [sum(weights[s] * rets[s][i] for s in weights) for i in range(n)]

    print("=" * 66)
    print(f"尾部与流动性风险 · {label} · {len(port)} 期({freq_cn}) · 年化因子 {ppy}")
    print("=" * 66)

    # ① VaR/CVaR
    print("\n① VaR / CVaR（单期损失，正数=亏损）:")
    for a in (0.95, 0.99):
        v = var_cvar(port, a)
        if v:
            ann = math.sqrt(ppy)
            print(f"  {int(a*100)}%: 历史VaR {v['hist_var']*100:5.2f}% · 历史CVaR(ES) {v['hist_cvar']*100:5.2f}% · 参数VaR {v['param_var']*100:5.2f}%"
                  f"   (年化参数VaR≈{v['param_var']*ann*100:.1f}%)")
    print(f"  最差单{freq_cn}: {min(port)*100:.2f}% · 最大回撤: {pr.max_drawdown(pr.nav_from_returns(port))*100:.2f}%")

    # ② 压力测试
    beta = None
    if args.benchmark and args.benchmark in cols:
        bench = pr.pct_returns(cols[args.benchmark])[:n]
        beta = pr.beta(port, bench)
        print(f"\n② 压力测试（组合 Beta={beta:.2f} vs {args.benchmark}）:")
        print("  历史/假设市场冲击 → 组合近似损失:")
        for s in stress_market(beta):
            print(f"    市场 {s['shock']*100:+.0f}%  →  组合 {s['port_impact']*100:+.1f}%")
        print("  反向压力（要亏这么多，需多大市场冲击）:")
        for r in reverse_stress(beta):
            im = f"{r['implied_market']*100:+.0f}%" if r['implied_market'] is not None else "—"
            print(f"    组合 {r['port_loss']*100:+.0f}%  ←  市场 {im}")
    else:
        print("\n② 压力测试: 需 --benchmark 提供市场基准以估 beta")
    print("  单一最大持仓冲击:")
    for s in single_name_shock(weights):
        print(f"    {s['name']}(权重{s['weight']*100:.0f}%) {s['drop']*100:+.0f}% → 组合 {s['port_impact']*100:+.1f}%")

    # ③ 流动性风险（仅 --from-ledger，需股数 + 成交量）
    if getattr(args, "from_ledger", None):
        print("\n③ 流动性风险（20% 参与率下清算天数）:")
        try:
            import datalayer as dl
            import ledger
            pos, _, _, _ = ledger.rebuild(ledger.load_ledger(args.from_ledger))
            fx = pr._parse_fx(args.fx)
            for s, p in sorted(pos.items(), key=lambda kv: -float(kv[1].qty)):
                if p.qty <= 0:
                    continue
                env = dl.fetch_ohlcv(s, freq="daily", period="1y")
                bars = [b for b in env["bars"] if b.get("volume")][-20:]
                if not bars:
                    continue
                cur = env["currency"]
                adv_native = sum((b["close"] * b["volume"]) for b in bars) / len(bars)
                pos_val = float(p.qty) * bars[-1]["close"]
                d = days_to_liquidate(pos_val, adv_native)
                flag = "🔴" if d > 5 else ("🟡" if d > 1 else "🟢")
                print(f"    {flag} {s:<10} 清算 {d:5.2f} 天  (持仓 {pos_val/1e4:.1f}万{cur} / 日均额 {adv_native/1e8:.2f}亿{cur})")
        except Exception as e:  # noqa: BLE001
            print(f"    (流动性估计失败: {e})")

    print("\n  ⚠️ VaR 只是常态极端、不含黑天鹅(2008/2020 实际远超)；历史情景用 beta 线性映射、低估相关性跳升；"
          "流动性用 ADV 近似。风控是生存底线，须与回撤/情景/现金缓冲合看。")


def main():
    ap = argparse.ArgumentParser(description="尾部与流动性风险 + 压力测试（P4-3，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("analyze", help="组合尾部/压力/流动性风险")
    src = a.add_mutually_exclusive_group(required=True)
    src.add_argument("--prices"); src.add_argument("--from-datalayer"); src.add_argument("--from-ledger")
    a.add_argument("--fx", default="USD=1,HKD=0.128,CNY=0.14")
    a.add_argument("--weights"); a.add_argument("--benchmark")
    a.add_argument("--period", default="2y", choices=["1y", "2y", "5y", "10y", "max"])
    a.add_argument("--freq", default="weekly", choices=["daily", "weekly", "monthly"])
    args = ap.parse_args()
    if args.cmd != "analyze":
        ap.print_help()
        return
    analyze(args)


if __name__ == "__main__":
    main()
