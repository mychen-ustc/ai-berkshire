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
  · 质量 = ROE（pit_financials 点时库，EDGAR 真实财报，无前视）← 已接入
  · 成长 = 预期 EPS CAGR（us_consensus）
  · 动量 = 12-1 月价格收益（datalayer，全市场）
  · 低波 = −年化波动（datalayer，全市场）
  · ⬜ 规模(市值) 待接股本；质量已由 EDGAR 点时库跑通(用 edgar_financials.py 摄取)。

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

FACTORS = ["value", "quality", "growth", "momentum", "lowvol", "size"]
FACTOR_CN = {"value": "价值", "quality": "质量", "growth": "成长",
             "momentum": "动量", "lowvol": "低波", "size": "规模"}


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
# PIT 安全性(评审#1纠正):as_of 回测时只有这些因子可无前视重建。
PIT_SAFE_FACTORS = {"quality", "momentum", "lowvol", "size"}   # 点时库/截断价格可重建
NON_PIT_FACTORS = {"value", "growth"}                          # 前瞻一致预期(us_consensus),历史不可 PIT 重建


def factor_pit_status():
    """声明各因子是否可 PIT(as_of)无前视重建。回测须只用 PIT_SAFE 子集。纯函数。"""
    return {"pit_safe": sorted(PIT_SAFE_FACTORS), "non_pit": sorted(NON_PIT_FACTORS),
            "note": "value/growth 读当前前瞻一致预期,历史 as_of 无法重建→回测须排除"}


def _price_history_asof(symbol, as_of=None):
    """周频前复权收盘,**截断到 <= as_of**(PIT:只用当时已知)。纯截断,无前视。"""
    period = "5y" if as_of else "2y"                   # as_of 需更长历史以回溯足量
    pts = dl.fetch_history(symbol, freq="weekly", period=period)["points"]
    if as_of:
        pts = [p for p in pts if p[0] <= as_of]        # ← PIT 截断:严格 <= as_of
    return [p[1] for p in pts]


def _price_factors_from(px):
    """从(已按 as_of 截断的)价格序列算 (momentum_12_1, ann_vol, price_last)。纯函数。"""
    if len(px) < 60:
        return None, None, (px[-1] if px else None)
    mom = (px[-5] / px[-57] - 1) if len(px) >= 57 else None    # 12-1月动量(跳最近1月)
    recent = px[-53:] if len(px) >= 53 else px
    rets = [math.log(recent[i] / recent[i - 1]) for i in range(1, len(recent))]
    mu = sum(rets) / len(rets)
    vol = math.sqrt(sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)) * math.sqrt(52)
    return mom, vol, px[-1]


def _fundamental_factors(symbol, as_of=None, pit=False):
    """→ (earnings_yield, eps_cagr) 由 us_consensus。**pit=True(历史回测)时返回 (None,None)**——
    前瞻一致预期是"当前"值,无法为过去日期 PIT 重建(评审#1)。"""
    if pit:
        return None, None
    try:
        import us_consensus as uc
        c = uc.analyze(symbol)
        fwd_pe = c.get("fwd_pe")
        ey = (1.0 / fwd_pe) if (fwd_pe and fwd_pe > 0) else None
        return ey, c.get("eps_cagr_pct")
    except Exception:  # noqa: BLE001
        return None, None


def _quality_factor(symbol, as_of=None):
    """→ ROE(质量) 由点时财务库取"当时已披露"(available_at<=as_of,无前视)。"""
    try:
        import pit_financials as pf
        from datetime import date
        d = as_of or date.today().strftime("%Y-%m-%d")
        hit = pf.as_of(pf.load(), symbol, "roe", d)    # pf.as_of 已强制 available_at<=d
        return hit["value"] if hit else None
    except Exception:  # noqa: BLE001
        return None


def _shares_asof(symbol, as_of=None):
    try:
        import pit_financials as pf
        from datetime import date
        d = as_of or date.today().strftime("%Y-%m-%d")
        hit = pf.as_of(pf.load(), symbol, "shares", d)
        return hit["value"] if hit else None
    except Exception:  # noqa: BLE001
        return None


def _size_from(shares, price):
    """规模 = −log(市值)。市值=股本×**as_of 价**(非当前价,评审#1修:as_of 时不得用现价)。纯函数。"""
    if not (shares and price):
        return None
    mktcap = price * shares
    return -math.log(mktcap) if mktcap > 0 else None


def gather_raw(symbols, as_of=None, pit=None):
    """每只 → 六因子原始值(缺失=None)。
    pit 未指定时:as_of 给出即视为 PIT 回测模式(自动 pit=True);as_of=None 则当前横截面(pit=False)。
    PIT 模式下 value/growth 置 None(前瞻一致预期不可历史重建),momentum/lowvol/size 用 <=as_of 截断价。"""
    if pit is None:
        pit = as_of is not None
    raw = {f: [] for f in FACTORS}
    meta = []
    for s in symbols:
        px = _price_history_asof(s, as_of)             # 已按 as_of 截断
        mom, vol, price_asof = _price_factors_from(px)
        ey, gr = _fundamental_factors(s, as_of, pit=pit)
        roe = _quality_factor(s, as_of)
        shares = _shares_asof(s, as_of)
        # size:as_of 模式用截断历史的 as_of 价;当前模式用实时报价
        px_for_size = price_asof if as_of else (dl.fetch_quote(s, cross=False).get("price") if not pit else price_asof)
        sz = _size_from(shares, px_for_size)
        raw["value"].append(ey)
        raw["quality"].append(roe)
        raw["growth"].append(gr)
        raw["momentum"].append(mom)
        raw["lowvol"].append(-vol if vol is not None else None)
        raw["size"].append(sz)
        meta.append({"symbol": s, "earnings_yield": ey, "roe": roe, "eps_cagr": gr,
                     "mom_12_1": mom, "ann_vol": vol, "neg_log_mktcap": sz, "pit": pit})
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
    print("基本面因子库 · Barra 式六因子横截面暴露（价值/质量/成长/动量/低波/规模）")
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
    print(f"\n  ⚠️ 诚实边界：Barra 式六因子全接——价值/成长(一致预期)、动量/低波(价格)、"
          f"质量(ROE)/规模(市值,EDGAR点时库)。")
    print(f"     规模 +z=小盘倾斜/−z=大盘(规模溢价在小盘侧)；质量/规模为点时(无前视)；z 为横截面相对值，样本少时不稳。")


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
