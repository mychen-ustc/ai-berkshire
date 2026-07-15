#!/usr/bin/env python3
"""多周期收益对比表（零外部依赖）。

按 1/3/5/10/15/20 年多个尺度，把组合核心指标(总回报/最终余额/年化/最大回撤/夏普
/Alpha/Beta/信息比率)列表，并与美股(QQQ/SPY)、A股(沪深300)、港股(恒生)主要指数对比。

统一按**月度**重采样(多年回测标准粒度)。组合按当前权重、月度再平衡回测。

★两条诚实边界(必须随表呈现)：
  1) 数据边界：组合回测受**最年轻持仓**限制——当前 v10 因兆易(2016上市)只有 ~10 年
     共同历史，故 15/20 年组合列为"数据不足"。指数有 20 年+，仍照常对比。
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


def build(weights, benchmarks, rf=0.04):
    """全程月度(YYYY-MM)对齐(跨市场周频星期锚不同，月度键才能对齐)。
    组合 + 指数 ≤10 年用 10y 周频重采样月度；指数 15/20 年用 max 月度。ppy=12。"""
    import datalayer as dl
    PPY = 12
    # 组合成分 + 基准：10y 周频 → 月度
    mo10 = {}
    for s in list(weights) + benchmarks:
        try:
            mo10[s] = resample_monthly(dl.fetch_history(s, freq="weekly", period="10y")["points"])
        except Exception:  # noqa: BLE001
            pass
    months, port_mo, start = align_weekly(mo10, weights)   # 按月键对齐(泛用)
    bench_mo10 = {b: _rets_from_prices(mo10[b]) for b in benchmarks if b in mo10 and len(mo10[b]) > 4}

    # 指数：max → 月度(供 15/20 年)
    bench_moMax = {}
    for b in benchmarks:
        try:
            bench_moMax[b] = _rets_from_prices(resample_monthly(
                dl.fetch_history(b, freq="weekly", period="max")["points"]))
        except Exception:  # noqa: BLE001
            pass

    rows = []
    for y in HORIZONS:
        row = {"years": y}
        ps = horizon_slice(port_mo, y, PPY) if port_mo else None
        row["port"] = series_metrics(ps, rf, PPY) if ps else None
        if ps and benchmarks and benchmarks[0] in bench_mo10:
            bsl = bench_mo10[benchmarks[0]][-len(ps):]
            n = min(len(ps), len(bsl))
            if n >= 12:
                row["alpha"] = qm.alpha_annual(ps[-n:], bsl[-n:], rf, PPY)
                row["beta"] = qm.beta(ps[-n:], bsl[-n:])
                row["ir"] = qm.information_ratio(ps[-n:], bsl[-n:], PPY)
        row["bench"] = {}
        for b in benchmarks:
            src = bench_mo10 if y <= 10 else bench_moMax   # ≤10 年用近端月度, >10 用 max
            bs = horizon_slice(src.get(b, []), y, PPY)
            row["bench"][b] = series_metrics(bs, rf, PPY) if bs else None
        rows.append(row)
    return {"rows": rows, "start_month": start, "n_months": len(port_mo) if port_mo else 0,
            "benchmarks": benchmarks, "weights": weights}


# --------------------------------------------------------------------------
# 渲染
# --------------------------------------------------------------------------
def _pct(x):
    return "—" if x is None else f"{x:+.1%}"


def _num(x):
    return "—" if x is None else f"{x:.2f}"


def render_text(res):
    print("=" * 92)
    print(f"多周期收益对比表 · 初始资金 $10,000 · 组合共同起点 {res['start_month'] or '—'}"
          f"（{res['n_months']} 个月，2016起，月度对齐）")
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
    print("  1) 数据边界：组合回测受最年轻持仓限制(v10 因兆易 2016 上市，仅 ~10 年共同历史)，"
          "15/20 年组合无数据；指数有 20 年+仍对比。")
    print("  2) 时代错置/幸存者：用今天的持仓回测历史=假设当年就持有且都活到今天，系统性高估——"
          "这是'当前组合的历史特征画像'，非你当年真实收益。")
    print("  3) 月度重采样、单一无风险利率；不含黑天鹅。")


def render_md(res):
    L = ["# 多周期收益对比表（初始资金 $10,000）", ""]
    L.append(f"> 组合共同起点 {res['start_month'] or '—'}（{res['n_months']} 个月，月度对齐；15/20年指数用max月频）")
    L.append("\n## ① 组合多周期表现")
    L.append("| 周期 | 总回报 | 最终余额 | 年化 | 最大回撤 | Sharpe | Alpha(vs主基准) | Beta | IR |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in res["rows"]:
        p = r["port"]
        if not p:
            L.append(f"| {r['years']}年 | — 数据不足(组合最年轻持仓限制) |  |  |  |  |  |  |  |")
            continue
        L.append(f"| {r['years']}年 | {_pct(p['total_return'])} | ${int(p['final_balance']):,} | "
                 f"{_pct(p['cagr'])} | {_pct(p['max_drawdown'])} | {_num(p['sharpe'])} | "
                 f"{_pct(r.get('alpha'))} | {_num(r.get('beta'))} | {_num(r.get('ir'))} |")
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
    L.append("\n**诚实边界**：① 组合受最年轻持仓限制(v10 兆易 2016→仅~10年共同史,15/20年无数据)；"
             "② 时代错置/幸存者——用今天持仓回测历史系统性高估,是'当前组合历史画像'非当年真实收益；"
             "③ 月度重采样、单一rf、不含黑天鹅。")
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
