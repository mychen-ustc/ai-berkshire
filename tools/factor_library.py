#!/usr/bin/env python3
"""基本面因子库（T2-1，Barra 式命名因子，零外部依赖）。

`factor_model.py` 用 PCA 给统计因子(PC1/PC2 无经济含义)；本工具补**带经济含义的
命名因子**——价值/成长/动量/低波——做横截面标准化，回答两个机构核心问题：
  1) 组合到底在押哪些因子？("你名义分散，实则重仓 成长+动量")
  2) 在候选池里，哪些标的在目标因子上得分高？(因子化选股)

方法（对标 Barra/MSCI 风格因子）：
  · 每只股票取原始因子值 → 横截面 winsorize(去极值) → z-score 标准化(均值0标准差1)
  · 组合因子暴露 = Σ 权重 × z 分；>0 超配该因子、<0 低配
  · 因子相关：看你以为的多个因子是否其实高度重叠

数据源（诚实边界）：
  · 价值 = 前瞻盈利收益率 1/fwd_pe（us_consensus，美股）
  · 成长 = 预期 EPS CAGR（us_consensus）
  · 动量 = 12-1 月价格收益（datalayer，全市场）
  · 低波 = −年化波动（datalayer，全市场）
  · ⬜ 质量(ROE)/规模(市值) 需点时基本面库(路线图 Tier 1)，本版本未接入——诚实标注缺口。

用法：
  python3 tools/factor_library.py analyze --symbols "GOOGL,AXP,COST,NDAQ,KO" \
      --weights "GOOGL=30,AXP=15,COST=10,NDAQ=10,KO=35"
  python3 tools/factor_library.py rank --symbols "..." --factor value   # 因子化选股
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402

FACTORS = ["value", "growth", "momentum", "lowvol"]
FACTOR_CN = {"value": "价值", "growth": "成长", "momentum": "动量", "lowvol": "低波"}


# --------------------------------------------------------------------------
# 纯函数（可测）——横截面标准化数学
# --------------------------------------------------------------------------
def _median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def winsorize(values, n_mad=3.0):
    """按中位数 ± n_mad×MAD 截断去极值。None 原样保留。纯函数。"""
    valid = [v for v in values if v is not None]
    if len(valid) < 3:
        return list(values)
    med = _median(valid)
    mad = _median([abs(v - med) for v in valid]) or 0.0
    if mad == 0:
        return list(values)
    lo, hi = med - n_mad * 1.4826 * mad, med + n_mad * 1.4826 * mad
    return [None if v is None else min(hi, max(lo, v)) for v in values]


def zscore(values):
    """横截面 z-score：(x−均值)/标准差。None 保留为 None；std=0 时全 0。纯函数。"""
    valid = [v for v in values if v is not None]
    if len(valid) < 2:
        return [0.0 if v is not None else None for v in values]
    mu = sum(valid) / len(valid)
    var = sum((v - mu) ** 2 for v in valid) / (len(valid) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return [0.0 if v is not None else None for v in values]
    return [None if v is None else (v - mu) / sd for v in values]


def standardize_factor(raw_values):
    """去极值 + 标准化。纯函数。"""
    return zscore(winsorize(raw_values))


def portfolio_exposure(z_by_factor, weights):
    """组合因子暴露 = Σ 权重×z。weights 与 z 列表同序。缺失(None)的按有效权重重新归一。纯函数。"""
    out = {}
    for f, zs in z_by_factor.items():
        num = sum(w * z for w, z in zip(weights, zs) if z is not None)
        wsum = sum(w for w, z in zip(weights, zs) if z is not None)
        out[f] = (num / wsum) if wsum > 0 else None
    return out


def composite_score(z_by_factor, factor_weights):
    """按 factor_weights 加权多因子合成分(每只)。纯函数。"""
    factors = list(factor_weights)
    n = len(next(iter(z_by_factor.values())))
    scores = []
    for i in range(n):
        num = sum(factor_weights[f] * z_by_factor[f][i] for f in factors if z_by_factor[f][i] is not None)
        wsum = sum(factor_weights[f] for f in factors if z_by_factor[f][i] is not None)
        scores.append((num / wsum) if wsum > 0 else None)
    return scores


def factor_correlation(z_by_factor):
    """因子间横截面相关(看命名因子是否重叠)。纯函数。"""
    fs = list(z_by_factor)
    cor = {}
    for a in fs:
        for b in fs:
            if a >= b:
                continue
            pairs = [(x, y) for x, y in zip(z_by_factor[a], z_by_factor[b]) if x is not None and y is not None]
            if len(pairs) < 3:
                cor[(a, b)] = None
                continue
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            cov = sum((x - mx) * (y - my) for x, y in pairs)
            sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
            sy = math.sqrt(sum((y - my) ** 2 for y in ys))
            cor[(a, b)] = (cov / (sx * sy)) if sx and sy else None
    return cor


# --------------------------------------------------------------------------
# 数据采集（原始因子值）
# --------------------------------------------------------------------------
def _price_factors(symbol):
    """→ (momentum_12_1, ann_vol) 由周频价格算。全市场可用。"""
    try:
        pts = dl.fetch_history(symbol, freq="weekly", period="2y")["points"]
        px = [p[1] for p in pts]
        if len(px) < 60:
            return None, None
        # 12-1 月动量：约 52 周前 → 约 4 周前(跳过最近1月反转)
        mom = (px[-5] / px[-57] - 1) if len(px) >= 57 else None
        # 年化波动(近~1年周频)
        recent = px[-53:] if len(px) >= 53 else px
        rets = [math.log(recent[i] / recent[i - 1]) for i in range(1, len(recent))]
        mu = sum(rets) / len(rets)
        vol = math.sqrt(sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)) * math.sqrt(52)
        return mom, vol
    except Exception:  # noqa: BLE001
        return None, None


def _fundamental_factors(symbol):
    """→ (earnings_yield, eps_cagr) 由 us_consensus(美股) 算。"""
    try:
        import us_consensus as uc
        c = uc.analyze(symbol)
        fwd_pe = c.get("fwd_pe")
        ey = (1.0 / fwd_pe) if (fwd_pe and fwd_pe > 0) else None
        gr = c.get("eps_cagr_pct")
        return ey, gr
    except Exception:  # noqa: BLE001
        return None, None


def gather_raw(symbols):
    """每只 → {value, growth, momentum, lowvol} 原始因子值(缺失=None)。"""
    raw = {f: [] for f in FACTORS}
    meta = []
    for s in symbols:
        mom, vol = _price_factors(s)
        ey, gr = _fundamental_factors(s)
        raw["value"].append(ey)                        # 盈利收益率越高越"价值"
        raw["growth"].append(gr)                       # EPS CAGR 越高越"成长"
        raw["momentum"].append(mom)                    # 12-1月动量
        raw["lowvol"].append(-vol if vol is not None else None)  # 负波动:越高越"低波"
        meta.append({"symbol": s, "earnings_yield": ey, "eps_cagr": gr,
                     "mom_12_1": mom, "ann_vol": vol})
    return raw, meta


# --------------------------------------------------------------------------
# 编排
# --------------------------------------------------------------------------
def analyze(symbols, weights=None):
    raw, meta = gather_raw(symbols)
    z = {f: standardize_factor(raw[f]) for f in FACTORS}
    coverage = {f: sum(1 for v in raw[f] if v is not None) for f in FACTORS}
    result = {"symbols": symbols, "z": z, "meta": meta, "coverage": coverage,
              "factor_corr": factor_correlation(z)}
    if weights:
        w = [weights.get(s, 0.0) for s in symbols]
        tot = sum(w) or 1.0
        w = [x / tot for x in w]
        result["exposure"] = portfolio_exposure(z, w)
        result["weights"] = w
    return result


def _parse_weights(spec):
    w = {}
    for part in (spec or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            w[k.strip()] = float(v)
    return w


def render(res):
    print("=" * 74)
    print("基本面因子库 · 横截面命名因子暴露（价值/成长/动量/低波）")
    print("=" * 74)
    syms = res["symbols"]
    z = res["z"]
    print(f"\n① 个股因子 z 分（横截面标准化，>0 该因子偏强）:")
    print(f"  {'标的':<10}" + "".join(f"{FACTOR_CN[f]:>8}" for f in FACTORS))
    for i, s in enumerate(syms):
        row = "".join(f"{z[f][i]:>+8.2f}" if z[f][i] is not None else f"{'—':>8}" for f in FACTORS)
        print(f"  {s:<10}{row}")
    cov = res["coverage"]
    print(f"\n  数据覆盖: " + " · ".join(f"{FACTOR_CN[f]} {cov[f]}/{len(syms)}" for f in FACTORS))
    miss = [f for f in FACTORS if cov[f] < len(syms)]
    if miss:
        print(f"  ⚠️ {', '.join(FACTOR_CN[f] for f in miss)} 有缺失(多为 ETF 无个股基本面/非美股一致预期未接)")

    if "exposure" in res:
        print(f"\n② 组合因子暴露（Σ 权重×z，>0 超配该因子——'你在押什么'）:")
        exp = res["exposure"]
        for f in FACTORS:
            e = exp[f]
            if e is None:
                print(f"  {FACTOR_CN[f]:<6} 数据不足")
                continue
            bar = "█" * min(20, int(abs(e) * 10))
            tilt = "超配" if e > 0.15 else ("低配" if e < -0.15 else "中性")
            print(f"  {FACTOR_CN[f]:<6} {e:>+6.2f}  {bar:<20} {tilt}")
        strong = sorted([(f, exp[f]) for f in FACTORS if exp[f] is not None], key=lambda x: -abs(x[1]))
        if strong:
            lead = strong[0]
            print(f"\n  → 主导因子倾斜: {FACTOR_CN[lead[0]]} ({lead[1]:+.2f})——"
                  f"名义分散不代表因子分散，这是你真正的押注。")

    print(f"\n③ 因子间相关（命名因子是否重叠）:")
    for (a, b), c in res["factor_corr"].items():
        if c is not None and abs(c) > 0.5:
            print(f"  ⚠️ {FACTOR_CN[a]} vs {FACTOR_CN[b]}: {c:+.2f}（高度相关，实为同一押注）")
    print(f"\n  ⚠️ 诚实边界：仅价值/成长(美股一致预期)/动量/低波(价格)四因子；质量(ROE)/规模(市值)")
    print(f"     需点时基本面库(路线图 Tier 1)未接入。z 分为横截面相对值，样本少时不稳。")


def render_rank(res, factor, top):
    z = res["z"][factor]
    syms = res["symbols"]
    ranked = sorted([(syms[i], z[i]) for i in range(len(syms)) if z[i] is not None],
                    key=lambda x: -x[1])
    print("=" * 50)
    print(f"因子化选股 · 按【{FACTOR_CN[factor]}】因子 z 分排序")
    print("=" * 50)
    for i, (s, sc) in enumerate(ranked[:top], 1):
        print(f"  {i:>2}. {s:<10} z={sc:>+.2f}")
    print(f"\n  ⚠️ 单因子排序仅供筛选起点；须结合基本面质检与估值，不可单凭 z 分买入。")


def main():
    ap = argparse.ArgumentParser(description="基本面因子库：命名因子横截面暴露(T2-1，零依赖)")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("analyze", help="个股因子z分 + 组合因子暴露")
    a.add_argument("--symbols", required=True)
    a.add_argument("--weights", help='"GOOGL=30,AXP=15,..."(占比%)')
    r = sub.add_parser("rank", help="按单因子排序(因子化选股)")
    r.add_argument("--symbols", required=True)
    r.add_argument("--factor", required=True, choices=FACTORS)
    r.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    if args.cmd == "analyze":
        syms = [s.strip() for s in args.symbols.split(",") if s.strip()]
        res = analyze(syms, _parse_weights(args.weights) if args.weights else None)
        render(res)
    elif args.cmd == "rank":
        syms = [s.strip() for s in args.symbols.split(",") if s.strip()]
        res = analyze(syms)
        render_rank(res, args.factor, args.top)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
