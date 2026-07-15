#!/usr/bin/env python3
"""多周期收益对比表（零外部依赖）。

按 1/3/5/10/15/20 年多个尺度，把组合核心指标(总回报/最终余额/年化/最大回撤/夏普
/Alpha/Beta/信息比率)列表，并与美股(QQQ/SPY)、A股(沪深300)、港股(恒生)主要指数对比。

统一按**月度**重采样(多年回测标准粒度)。组合按当前权重、月度再平衡回测。

★两条诚实边界(必须随表呈现)：
  1) 年轻持仓处理：长周期若某持仓当时未上市(如兆易2016)，将其**权重设0、其余重新归一**
     并在"剔除"列标出——故长周期是"当时已存在子集"的表现，非完整 v10。
  2) 时代错置/幸存者偏差：用"今天的持仓"回测历史 = 假设你当年就持有这些(还都活到今天)，
     系统性高估。这不是你当年的真实收益，只是"当前组合的历史特征画像"。

用法：
  python3 tools/horizon_compare.py --from-datalayer "GOOGL=16,MTUM=14,VOO=14,..." \
      --benchmarks "QQQ,SPY,sh000300,2800.HK" --rf 0.04 [--md]
"""
import argparse
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quant_metrics as qm  # noqa: E402

HORIZONS = [1, 3, 5, 10, 15, 20]
BENCH_CN = {"QQQ": "QQQ", "SPY": "SPY", "sh000300": "沪深300", "2800.HK": "恒生",
            "000001.SH": "上证"}


# --------------------------------------------------------------------------
# 纯函数（可测）
# --------------------------------------------------------------------------
def resample_monthly(points):
    """[(date,price)] → 月末重采样 [(YYYY-MM, price)]，每月取最后一个观测。纯函数。"""
    by_month = {}
    for d, p in points:
        by_month[d[:7]] = p        # 后者覆盖 → 该月最后观测
    return sorted(by_month.items())


def align_weekly(prices_by_sym, weights):
    """各标的周频价格(按日期键) → 共同日期上的组合加权周收益 + 共同起始日。
    prices_by_sym: {sym: [(date, price)]}。返回 (dates, port_returns, start_date)。纯函数。"""
    syms = [s for s in weights if s in prices_by_sym and len(prices_by_sym[s]) > 4]
    if not syms:
        return [], [], None
    date_sets = [set(d for d, _ in prices_by_sym[s]) for s in syms]
    common = sorted(set.intersection(*date_sets))
    if len(common) < 12:
        return [], [], None
    px = {s: dict(prices_by_sym[s]) for s in syms}
    tot = sum(weights[s] for s in syms) or 1.0
    w = {s: weights[s] / tot for s in syms}
    rets = []
    for i in range(1, len(common)):
        d0, d1 = common[i - 1], common[i]
        rets.append(sum(w[s] * (px[s][d1] / px[s][d0] - 1) for s in syms))
    return common, rets, common[0]


def horizon_slice(rets, years, ppy):
    """取最近 years 年的收益(约 years×ppy 期)。不足返回 None。纯函数。"""
    need = int(years * ppy)
    if len(rets) < need:
        return None
    return rets[-need:]


def series_metrics(rets, rf=0.04, ppy=12):
    """月收益序列 → {total_return, final_balance, cagr, max_drawdown, sharpe}。纯函数。"""
    if not rets:
        return None
    eq = 1.0
    for r in rets:
        eq *= (1 + r)
    total = eq - 1
    yrs = len(rets) / ppy
    cagr = eq ** (1 / yrs) - 1 if yrs > 0 else 0
    return {
        "total_return": total, "final_balance": 10000 * eq, "cagr": cagr,
        "max_drawdown": qm.max_drawdown(rets), "sharpe": qm.sharpe(rets, rf, ppy),
        "n_months": len(rets),
    }


# --------------------------------------------------------------------------
# 编排
# --------------------------------------------------------------------------
def _rets_from_prices(pts):
    pr = [p for _, p in pts]
    return [pr[i] / pr[i - 1] - 1 for i in range(1, len(pr))]


def month_range(start, end):
    """连续 YYYY-MM 列表 [start..end]。纯函数。"""
    y, m = int(start[:4]), int(start[5:7])
    y1, m1 = int(end[:4]), int(end[5:7])
    out = []
    while (y, m) <= (y1, m1):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def forward_fill(pairs, grid):
    """把 [(month,price)] 对齐到 grid，前向填充；首个观测前为 None。纯函数。"""
    d = dict(pairs)
    out, last = [], None
    for g in grid:
        if g in d:
            last = d[g]
        out.append(last)
    return out


def portfolio_returns(filled_by_sym, weights, eligible):
    """在对齐网格上算 eligible(权重重新归一) 组合月收益。纯函数。"""
    tot = sum(weights[s] for s in eligible) or 1.0
    w = {s: weights[s] / tot for s in eligible}
    n = len(next(iter(filled_by_sym.values()))) if filled_by_sym else 0
    rets = []
    for i in range(1, n):
        if all(filled_by_sym[s][i - 1] and filled_by_sym[s][i] for s in eligible):
            rets.append(sum(w[s] * (filled_by_sym[s][i] / filled_by_sym[s][i - 1] - 1) for s in eligible))
    return rets


def build(weights, benchmarks, rf=0.04):
    """月度网格 + 前向填充。长周期若年轻持仓无数据→剔除(权重归零)、其余重新归一，并记录剔除名单。
    组合 ≤10 年用 10y 周频重采样月度(密)；>10 年用 max 月度前向填充。指数同理。ppy=12。"""
    import datalayer as dl
    PPY = 12
    syms = list(weights)
    mo10, moMax = {}, {}
    for s in syms + benchmarks:
        try:
            mo10[s] = resample_monthly(dl.fetch_history(s, freq="weekly", period="10y")["points"])
        except Exception:  # noqa: BLE001
            pass
        try:
            moMax[s] = resample_monthly(dl.fetch_history(s, freq="weekly", period="max")["points"])
        except Exception:  # noqa: BLE001
            pass
    # 全局连续月度网格(长周期前向填充用)
    allm = sorted({m for s in moMax for m, _ in moMax[s]})
    grid = month_range(allm[0], allm[-1]) if allm else []
    filledMax = {s: forward_fill(moMax.get(s, []), grid) for s in syms + benchmarks}
    earliest = {s: (moMax[s][0][0] if moMax.get(s) else None) for s in syms + benchmarks}
    start = None

    def bench_rets(b, need, y):
        """基准在最近 need 月的收益(≤10 年用 mo10,>10 用 max 前向填充)。"""
        if y <= 10 and b in mo10 and len(mo10[b]) >= need:
            return _rets_from_prices(mo10[b][-need:])
        if b in filledMax:
            win = filledMax[b][-need:]
            if all(x for x in win):
                return [win[i] / win[i - 1] - 1 for i in range(1, len(win))]
        return []

    rows = []
    for y in HORIZONS:
        row = {"years": y}
        need = y * PPY
        if y <= 10:
            elig = [s for s in syms if s in mo10 and len(mo10[s]) >= need]
            dropped = [s for s in syms if s not in elig]
            prets = []
            if elig:
                common = sorted(set.intersection(*[set(m for m, _ in mo10[s]) for s in elig]))[-need:]
                pmap = {s: dict(mo10[s]) for s in elig}
                filt = {s: [pmap[s].get(m) for m in common] for s in elig}
                prets = portfolio_returns(filt, weights, elig)
                if y == max(h for h in HORIZONS if h <= 10) and common:
                    start = common[0]
        else:
            win = grid[-need:] if len(grid) >= need else grid
            wstart = win[0] if win else None
            elig = [s for s in syms if earliest.get(s) and wstart and earliest[s] <= wstart]
            dropped = [s for s in syms if s not in elig]
            idx0 = len(grid) - len(win)
            sub = {s: filledMax[s][idx0:] for s in elig}
            prets = portfolio_returns(sub, weights, elig) if elig else []
        row["dropped"] = dropped
        row["port"] = series_metrics(prets, rf, PPY) if len(prets) >= 6 else None
        # Alpha/Beta/IR vs 主基准
        if row["port"] and benchmarks:
            bsl = bench_rets(benchmarks[0], need, y)
            n = min(len(prets), len(bsl))
            if n >= 10:
                row["alpha"] = qm.alpha_annual(prets[-n:], bsl[-n:], rf, PPY)
                row["beta"] = qm.beta(prets[-n:], bsl[-n:])
                row["ir"] = qm.information_ratio(prets[-n:], bsl[-n:], PPY)
        row["bench"] = {}
        for b in benchmarks:
            br = bench_rets(b, need, y)
            row["bench"][b] = series_metrics(br, rf, PPY) if len(br) >= 6 else None
        rows.append(row)
    return {"rows": rows, "start_month": start, "n_months": len(grid),
            "benchmarks": benchmarks, "weights": weights}


# --------------------------------------------------------------------------
# 渲染
# --------------------------------------------------------------------------
def _pct(x):
    return "—" if x is None else f"{x:+.1%}"


def _num(x):
    return "—" if x is None else f"{x:.2f}"


_NAME = {"603986": "兆易"}


def dropped_notes(res):
    """→ [(years, [剔除标的显示名])]，仅列有剔除的周期。纯函数。"""
    out = []
    for r in res["rows"]:
        if r.get("dropped"):
            out.append((r["years"], [_NAME.get(s, s) for s in r["dropped"]]))
    return out


def render_text(res):
    print("=" * 92)
    print("多周期收益对比表 · 初始资金 $10,000 · 组合按当前权重月度再平衡回测"
          "(长周期剔除当时未上市持仓，见ⓘ)")
    print("=" * 92)
    print("\n① 组合多周期表现:")
    print(f"  {'周期':<8}{'总回报':>10}{'最终余额':>12}{'年化':>8}{'最大回撤':>9}{'Sharpe':>8}"
          f"{'Alpha':>8}{'Beta':>7}{'IR':>6}")
    for r in res["rows"]:
        p = r["port"]
        if not p:
            print(f"  {str(r['years'])+'年':<8}{'— 数据不足(组合最年轻持仓限制)':>40}")
            continue
        print(f"  {str(r['years'])+'年':<8}{_pct(p['total_return']):>10}"
              f"{'$'+format(int(p['final_balance']), ','):>12}{_pct(p['cagr']):>8}"
              f"{_pct(p['max_drawdown']):>9}{_num(p['sharpe']):>8}"
              f"{_pct(r.get('alpha')):>8}{_num(r.get('beta')):>7}{_num(r.get('ir')):>6}")
    dn = dropped_notes(res)
    if dn:
        print("  ⓘ 长周期剔除年轻持仓(权重归零、其余重新归一): "
              + " · ".join(f"{y}年→剔{','.join(names)}" for y, names in dn))

    print("\n② 年化收益 vs 主要指数:")
    bl = res["benchmarks"]
    print(f"  {'周期':<8}{'组合':>9}" + "".join(f"{BENCH_CN.get(b, b):>9}" for b in bl))
    for r in res["rows"]:
        pc = _pct(r["port"]["cagr"]) if r["port"] else "—"
        cells = "".join(f"{_pct(r['bench'][b]['cagr']) if r['bench'].get(b) else '—':>9}" for b in bl)
        print(f"  {str(r['years'])+'年':<8}{pc:>9}{cells}")

    print("\n③ 最大回撤 vs 主要指数:")
    print(f"  {'周期':<8}{'组合':>9}" + "".join(f"{BENCH_CN.get(b, b):>9}" for b in bl))
    for r in res["rows"]:
        pc = _pct(r["port"]["max_drawdown"]) if r["port"] else "—"
        cells = "".join(f"{_pct(r['bench'][b]['max_drawdown']) if r['bench'].get(b) else '—':>9}" for b in bl)
        print(f"  {str(r['years'])+'年':<8}{pc:>9}{cells}")

    print("\n⚠️ 诚实边界：")
    print("  1) 年轻持仓处理：长周期若某持仓当时未上市(如兆易2016)，将其权重设0、其余重新归一"
          "(见上'剔除'提示)——故长周期是'当时已存在的子集'的表现，非完整 v10。")
    print("  2) 时代错置/幸存者：用今天的持仓回测历史=假设当年就持有且都活到今天，系统性高估——"
          "这是'当前组合的历史特征画像'，非你当年真实收益。")
    print("  3) 月度重采样、长周期含前向填充、单一无风险利率；不含黑天鹅。")


def render_md(res):
    L = ["# 多周期收益对比表（初始资金 $10,000）", ""]
    L.append("> 组合按当前权重月度再平衡回测；长周期剔除当时未上市持仓(见'剔除'列)。月度对齐、含前向填充。")
    L.append("\n## ① 组合多周期表现")
    L.append("| 周期 | 总回报 | 最终余额 | 年化 | 最大回撤 | Sharpe | Alpha | Beta | IR | 剔除(年轻持仓) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in res["rows"]:
        p = r["port"]
        drp = "、".join(_NAME.get(s, s) for s in r.get("dropped", [])) or "—"
        if not p:
            L.append(f"| {r['years']}年 | — 数据不足 |  |  |  |  |  |  |  | {drp} |")
            continue
        L.append(f"| {r['years']}年 | {_pct(p['total_return'])} | ${int(p['final_balance']):,} | "
                 f"{_pct(p['cagr'])} | {_pct(p['max_drawdown'])} | {_num(p['sharpe'])} | "
                 f"{_pct(r.get('alpha'))} | {_num(r.get('beta'))} | {_num(r.get('ir'))} | {drp} |")
    bl = res["benchmarks"]
    L.append("\n## ② 年化收益 vs 主要指数")
    L.append("| 周期 | 组合 | " + " | ".join(BENCH_CN.get(b, b) for b in bl) + " |")
    L.append("|---|---|" + "---|" * len(bl))
    for r in res["rows"]:
        pc = _pct(r["port"]["cagr"]) if r["port"] else "—"
        cells = " | ".join(_pct(r["bench"][b]["cagr"]) if r["bench"].get(b) else "—" for b in bl)
        L.append(f"| {r['years']}年 | {pc} | {cells} |")
    L.append("\n## ③ 最大回撤 vs 主要指数")
    L.append("| 周期 | 组合 | " + " | ".join(BENCH_CN.get(b, b) for b in bl) + " |")
    L.append("|---|---|" + "---|" * len(bl))
    for r in res["rows"]:
        pc = _pct(r["port"]["max_drawdown"]) if r["port"] else "—"
        cells = " | ".join(_pct(r["bench"][b]["max_drawdown"]) if r["bench"].get(b) else "—" for b in bl)
        L.append(f"| {r['years']}年 | {pc} | {cells} |")
    L.append("\n**诚实边界**：① 年轻持仓处理——长周期若某持仓当时未上市(如兆易2016)，权重设0、"
             "其余重新归一(见'剔除'列)，故长周期是'当时子集'表现非完整v10；"
             "② 时代错置/幸存者——用今天持仓回测历史系统性高估,是'历史画像'非当年真实收益；"
             "③ 月度重采样、长周期含前向填充、单一rf、不含黑天鹅。")
    return "\n".join(L)


def _parse_weights(spec):
    w = {}
    for part in spec.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            w[k.strip()] = float(v)
    return w


def main():
    ap = argparse.ArgumentParser(description="多周期收益对比表(1/3/5/10/15/20年 × 多指数，零依赖)")
    ap.add_argument("--from-datalayer", required=True, help='"GOOGL=16,MTUM=14,..."')
    ap.add_argument("--benchmarks", default="QQQ,SPY,sh000300,2800.HK")
    ap.add_argument("--rf", type=float, default=0.04)
    ap.add_argument("--md", action="store_true", help="输出 Markdown")
    args = ap.parse_args()
    res = build(_parse_weights(args.from_datalayer),
                [b.strip() for b in args.benchmarks.split(",") if b.strip()], args.rf)
    if args.md:
        print(render_md(res))
    else:
        render_text(res)


if __name__ == "__main__":
    main()
