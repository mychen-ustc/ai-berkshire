#!/usr/bin/env python3
"""美股一致预期跟踪（零外部依赖，仅 stdlib）。consensus.py 的美股版。

回答：机构评级偏乐观还是谨慎、前瞻 EPS 增速多快、**盈利预期在往上调还是往下调**、
历史 beat/miss 如何。它是叠加层——量化"你的判断 vs 市场共识"，**永不替代自己估值**。

数据（免费）：
  · 评级趋势 + EPS beat/miss 历史 + 估值 metric：Finnhub（免费 key，读环境变量/本地 secrets）。
  · 前瞻一致 EPS（高/中/低）+ 估计家数 + 近4周修正上调/下调：Nasdaq API（无 key）。

诚实边界：
  · 卖方一致预期**系统性偏乐观**；EPS 为预测非事实。
  · Finnhub 免费档：评级/EPS惊喜/metric 可用，**目标价/深度预期为付费**（自动跳过）。
  · Nasdaq 为**非官方后端接口**，免费但可能变动/加反爬（已 try/except 优雅降级）。
  · 仅美股。**盈利修正动量**这次接上了（Nasdaq 近4周 up/down 家数）。

用法：
  python3 tools/us_consensus.py analyze AAPL
  python3 tools/us_consensus.py analyze NVDA --json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402
import keys  # noqa: E402


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _json(url, headers=None):
    return json.loads(dl._curl(url, headers=headers))


# --------------------------------------------------------------------------
# 数据源
# --------------------------------------------------------------------------
def fetch_nasdaq_forecast(symbol):
    """Nasdaq 年度前瞻一致 EPS + 修正家数。无 key。"""
    url = f"https://api.nasdaq.com/api/analyst/{symbol.upper()}/earnings-forecast"
    d = (_json(url, headers=["Accept: application/json"]).get("data")) or {}
    rows = ((d.get("yearlyForecast") or {}).get("rows")) or []
    out = []
    for r in rows:
        out.append({"fy": r.get("fiscalEnd"), "eps": _f(r.get("consensusEPSForecast")),
                    "high": _f(r.get("highEPSForecast")), "low": _f(r.get("lowEPSForecast")),
                    "n": r.get("noOfEstimates"), "up": _f(r.get("up")) or 0, "down": _f(r.get("down")) or 0})
    return out


def rating_stance(cur):
    """纯函数：Finnhub 评级计数 → 看多占比 + 倾向（可离线测试）。"""
    bull = cur.get("strongBuy", 0) + cur.get("buy", 0)
    tot = bull + cur.get("hold", 0) + cur.get("sell", 0) + cur.get("strongSell", 0)
    pct = round(bull / tot * 100, 1) if tot else None
    stance = "乐观" if (tot and bull / tot >= 0.6) else ("谨慎" if (tot and bull / tot < 0.4) else "中性")
    return {"period": cur.get("period"), "strongBuy": cur.get("strongBuy"), "buy": cur.get("buy"),
            "hold": cur.get("hold"), "sell": cur.get("sell"), "strongSell": cur.get("strongSell"),
            "bullish_pct": pct, "stance": stance}


def fetch_finnhub_reco(symbol, key):
    arr = _json(f"https://finnhub.io/api/v1/stock/recommendation?symbol={symbol}&token={key}")
    if not isinstance(arr, list) or not arr:
        return None, None
    return arr[0], (arr[1] if len(arr) > 1 else None)


def fetch_finnhub_earnings(symbol, key):
    arr = _json(f"https://finnhub.io/api/v1/stock/earnings?symbol={symbol}&token={key}")
    return arr[:8] if isinstance(arr, list) else []


# --------------------------------------------------------------------------
# 组装
# --------------------------------------------------------------------------
def analyze(symbol):
    key = keys.get_key("FINNHUB_API_KEY")
    out = {"symbol": symbol.upper(), "finnhub": bool(key)}

    # 评级
    if key:
        try:
            cur, prev = fetch_finnhub_reco(symbol, key)
            if cur:
                out["rating"] = rating_stance(cur)
        except Exception as e:  # noqa: BLE001
            out["rating_err"] = str(e)
        # EPS beat/miss
        try:
            e = fetch_finnhub_earnings(symbol, key)
            beats = [1 for q in e if q.get("actual") is not None and q.get("estimate") is not None and q["actual"] >= q["estimate"]]
            out["earnings"] = {"n": len(e), "beat_rate": round(len(beats) / len(e) * 100, 0) if e else None,
                               "recent": [{"period": q.get("period"), "est": q.get("estimate"),
                                           "act": q.get("actual"), "surp_pct": q.get("surprisePercent")} for q in e[:4]]}
        except Exception as e:  # noqa: BLE001
            out["earnings_err"] = str(e)

    # 前瞻 EPS + 修正动量（Nasdaq）
    try:
        yf = fetch_nasdaq_forecast(symbol)
        out["forecast"] = yf
        eps_vals = [r["eps"] for r in yf if r["eps"] is not None]
        if len(eps_vals) >= 2 and eps_vals[0] and eps_vals[0] > 0 and eps_vals[-1] > 0:
            yrs = len(eps_vals) - 1
            out["eps_cagr_pct"] = round(((eps_vals[-1] / eps_vals[0]) ** (1 / yrs) - 1) * 100, 1)
        up = sum(r["up"] for r in yf)
        down = sum(r["down"] for r in yf)
        out["revision"] = {"up": up, "down": down,
                           "momentum": "上修" if up > down else ("下修" if down > up else "持平")}
        # 前瞻 PE
        try:
            price = dl.fetch_quote(symbol, cross=False).get("price")
            nxt = eps_vals[0] if eps_vals else None
            out["price"] = price
            out["fwd_pe"] = round(price / nxt, 1) if (price and nxt) else None
            if out.get("fwd_pe") and out.get("eps_cagr_pct") and out["eps_cagr_pct"] > 0:
                out["peg"] = round(out["fwd_pe"] / out["eps_cagr_pct"], 2)
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        out["forecast_err"] = str(e)
    return out


def render(d):
    L = ["=" * 62, f"美股一致预期 · {d['symbol']}"
         + ("" if d["finnhub"] else "（无 Finnhub key：仅 Nasdaq 前瞻）"), "=" * 62]
    r = d.get("rating")
    if r:
        L.append(f"  机构评级({r['period']}): {r['stance']}"
                 + (f"（看多 {r['bullish_pct']}%）" if r["bullish_pct"] is not None else ""))
        L.append(f"    强买 {r['strongBuy']} · 买入 {r['buy']} · 持有 {r['hold']} · 卖出 {r['sell']} · 强卖 {r['strongSell']}")
    e = d.get("earnings")
    if e and e.get("beat_rate") is not None:
        L.append(f"  EPS beat/miss: 近 {e['n']} 季 beat 率 {e['beat_rate']:.0f}%")
        for q in e["recent"]:
            sp = f"{q['surp_pct']:+.1f}%" if isinstance(q["surp_pct"], (int, float)) else "—"
            L.append(f"    {q['period']}: 预期 {q['est']} / 实际 {q['act']}（超预期 {sp}）")
    if d.get("forecast"):
        L.append("  前瞻一致 EPS（Nasdaq）:")
        for r2 in d["forecast"][:4]:
            disp = f"（{r2['low']}~{r2['high']}, {r2['n']}家）" if r2.get("high") else ""
            L.append(f"    {r2['fy']}: {r2['eps']} {disp}")
        if d.get("eps_cagr_pct") is not None:
            L.append(f"    预期 EPS CAGR: {d['eps_cagr_pct']:+.1f}%")
        rev = d.get("revision")
        if rev:
            L.append(f"  盈利修正动量(近4周): 上调 {rev['up']:.0f} / 下调 {rev['down']:.0f} 家 → {rev['momentum']}")
    if d.get("fwd_pe"):
        L.append(f"  现价 {d.get('price')} · 前瞻 PE {d['fwd_pe']}" + (f" · PEG {d['peg']}" if d.get("peg") else ""))
    # 反向解读
    hint = []
    if r and (r.get("bullish_pct") or 0) >= 90:
        hint.append("评级高度一致乐观→预期或已充分定价")
    if d.get("revision", {}).get("momentum") == "下修":
        hint.append("盈利预期在下修→留意基本面转弱")
    if d.get("revision", {}).get("momentum") == "上修":
        hint.append("盈利预期在上修→动能偏正")
    if hint:
        L.append("  解读: " + "；".join(hint))
    L.append("\n  ⚠️ 卖方偏乐观、EPS 为预测；Nasdaq 为非官方接口；仅辅助看认知差，不替代自己估值。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="美股一致预期（Finnhub 评级/EPS惊喜 + Nasdaq 前瞻/修正动量，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("analyze", help="拉取并分析美股一致预期")
    a.add_argument("symbol")
    a.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd != "analyze":
        ap.print_help()
        return
    d = analyze(args.symbol)
    print(json.dumps(d, ensure_ascii=False, indent=2) if args.json else render(d))


if __name__ == "__main__":
    main()
