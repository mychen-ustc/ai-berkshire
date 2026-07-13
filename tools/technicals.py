#!/usr/bin/env python3
"""技术面分析（零外部依赖，仅 stdlib）。

价值投资里，技术面**不产生"买什么"的结论，只辅助"是否/何时"**——它是择时、
量价确认与风控的叠加层，不是选股逻辑。本工具据此定位：给出趋势/动量/波动/
量能/相对强弱的客观读数与关键价位，并明确标注"这是叠加层，非投资理由"。

指标（float 统计，非货币精度）：
  均线 SMA/EMA · MACD(12,26,9) · RSI(14, Wilder) · 布林带(20,2σ) ·
  ATR(14) 波动 · 动量 ROC(1/3/6/12月) · 52周高低距离 · 量比/量价配合 ·
  相对强弱 RS(对基准) · 均线多空排列/金叉死叉 · 近端支撑阻力。

数据来自统一数据层（A/H 东财前复权、US Yahoo）：
  python3 tools/technicals.py analyze 600519
  python3 tools/technicals.py analyze AAPL --benchmark SPY --json
  python3 tools/technicals.py analyze 0700.HK --period 2y
  python3 tools/technicals.py analyze --csv data/xxx.csv   # 离线(date,open,high,low,close,volume)
"""
import argparse
import csv
import json
import os
import statistics
import sys

# 默认基准：可被数据层直接取到（A→沪深300指数, HK→盈富2800, US→SPY）
DEFAULT_BENCH = {"A": "sh000300", "HK": "2800.HK", "US": "SPY"}


# --------------------------------------------------------------------------
# 纯指标函数（对 float 序列/OHLCV bars 运算，可离线测试）
# --------------------------------------------------------------------------
def sma_last(series, n):
    return sum(series[-n:]) / n if len(series) >= n else None


def ema(series, n):
    if not series:
        return []
    k = 2.0 / (n + 1)
    out = [float(series[0])]
    for x in series[1:]:
        out.append(x * k + out[-1] * (1 - k))
    return out


def rsi(closes, n=14):
    """Wilder RSI。返回 0~100 或 None（数据不足）。"""
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    avg_g = sum(gains[:n]) / n
    avg_l = sum(losses[:n]) / n
    for i in range(n, len(gains)):
        avg_g = (avg_g * (n - 1) + gains[i]) / n
        avg_l = (avg_l * (n - 1) + losses[i]) / n
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - 100 / (1 + rs)


def macd(closes, fast=12, slow=26, signal=9):
    """返回末值 dict(macd, signal, hist) 或 None。"""
    if len(closes) < slow + signal:
        return None
    ef, es = ema(closes, fast), ema(closes, slow)
    line = [a - b for a, b in zip(ef, es)]
    sig = ema(line, signal)
    hist = [m - s for m, s in zip(line, sig)]
    return {"macd": line[-1], "signal": sig[-1], "hist": hist[-1],
            "hist_prev": hist[-2] if len(hist) > 1 else None}


def bollinger(closes, n=20, k=2.0):
    if len(closes) < n:
        return None
    w = closes[-n:]
    mid = sum(w) / n
    sd = statistics.pstdev(w)
    upper, lower = mid + k * sd, mid - k * sd
    last = closes[-1]
    return {"mid": mid, "upper": upper, "lower": lower,
            "pctB": (last - lower) / (upper - lower) if upper != lower else 0.5,
            "bandwidth": (upper - lower) / mid if mid else 0.0}


def true_ranges(bars):
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        if None in (h, l, pc):
            continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return trs


def atr(bars, n=14):
    trs = true_ranges(bars)
    if len(trs) < n:
        return None
    a = sum(trs[:n]) / n
    for tr in trs[n:]:
        a = (a * (n - 1) + tr) / n
    return a


def roc(closes, n):
    if len(closes) <= n or closes[-1 - n] == 0:
        return None
    return (closes[-1] / closes[-1 - n] - 1) * 100


def high_low_distance(closes, lookback=250):
    w = closes[-lookback:]
    hi, lo, last = max(w), min(w), closes[-1]
    return {"high": hi, "low": lo, "n": len(w),
            "from_high_pct": (last / hi - 1) * 100 if hi else None,
            "from_low_pct": (last / lo - 1) * 100 if lo else None}


def swing_levels(bars, lookback=60, k=3):
    """近端支撑/阻力：窗口内的局部低点(支撑)/高点(阻力)，按距现价排序取最近几个。"""
    w = bars[-lookback:]
    if len(w) < 2 * k + 1:
        w = bars
    highs, lows = [], []
    for i in range(k, len(w) - k):
        seg = w[i - k:i + k + 1]
        hi = [b["high"] for b in seg if b["high"] is not None]
        lo = [b["low"] for b in seg if b["low"] is not None]
        if w[i]["high"] is not None and hi and w[i]["high"] == max(hi):
            highs.append(w[i]["high"])
        if w[i]["low"] is not None and lo and w[i]["low"] == min(lo):
            lows.append(w[i]["low"])
    last = bars[-1]["close"]
    res = sorted({round(h, 4) for h in highs if h > last})[:3]
    sup = sorted({round(x, 4) for x in lows if x < last}, reverse=True)[:3]
    return {"support": sup, "resistance": res}


def relative_strength(stock_bars, bench_bars, lookbacks=(20, 60, 120)):
    """RS 线 = (个股归一) / (基准归一)；>1 跑赢起点。返回近端 RS 变化。"""
    sb = {b["date"]: b["close"] for b in stock_bars}
    bb = {b["date"]: b["close"] for b in bench_bars}
    common = sorted(set(sb) & set(bb))
    if len(common) < 2:
        return None
    s = [sb[d] for d in common]
    m = [bb[d] for d in common]
    if s[0] == 0 or m[0] == 0:
        return None
    rs = [(s[i] / s[0]) / (m[i] / m[0]) for i in range(len(common))]
    out = {"n": len(common), "rs_now": rs[-1],
           "outperform_since_start_pct": (rs[-1] - 1) * 100}
    for lb in lookbacks:
        if len(rs) > lb and rs[-1 - lb] != 0:
            out[f"rs_chg_{lb}_pct"] = (rs[-1] / rs[-1 - lb] - 1) * 100
    return out


def ma_alignment(closes):
    """均线多空排列 + 金叉/死叉（50 vs 200）。"""
    last = closes[-1]
    s20, s50, s200 = sma_last(closes, 20), sma_last(closes, 50), sma_last(closes, 200)
    align, trend = "数据不足", "unknown"
    if None not in (s20, s50, s200):
        if last > s20 > s50 > s200:
            align, trend = "多头排列（价>20>50>200）", "up"
        elif last < s20 < s50 < s200:
            align, trend = "空头排列（价<20<50<200）", "down"
        elif last > s200 and s50 > s200:
            align, trend = "偏多（站上年线）", "up-weak"
        elif last < s200 and s50 < s200:
            align, trend = "偏空（跌破年线）", "down-weak"
        else:
            align, trend = "均线纠缠（震荡/无趋势）", "range"
    cross = None
    if len(closes) >= 202:
        s50p, s200p = sma_last(closes[:-5], 50), sma_last(closes[:-5], 200)
        if None not in (s50, s200, s50p, s200p):
            if s50p <= s200p and s50 > s200:
                cross = "近期金叉（50上穿200）🟢"
            elif s50p >= s200p and s50 < s200:
                cross = "近期死叉（50下穿200）🔴"
    return {"sma20": s20, "sma50": s50, "sma200": s200,
            "alignment": align, "trend": trend, "cross": cross}


# --------------------------------------------------------------------------
# 组装技术姿态（客观读数 + 启发式标签，非预测）
# --------------------------------------------------------------------------
def compute(bars, bench_bars=None):
    closes = [b["close"] for b in bars if b["close"] is not None]
    vols = [b["volume"] for b in bars if b.get("volume") is not None]
    last = closes[-1]
    r = {"last": last, "n_bars": len(bars),
         "date_first": bars[0]["date"], "date_last": bars[-1]["date"]}

    r["ma"] = ma_alignment(closes)
    r["rsi14"] = rsi(closes, 14)
    r["macd"] = macd(closes)
    r["bollinger"] = bollinger(closes)
    a = atr(bars, 14)
    r["atr14"] = a
    r["atr_pct"] = (a / last * 100) if a and last else None
    r["momentum"] = {"roc_1m": roc(closes, 21), "roc_3m": roc(closes, 63),
                     "roc_6m": roc(closes, 126), "roc_12m": roc(closes, 252)}
    r["range52w"] = high_low_distance(closes, 250)
    r["levels"] = swing_levels(bars, 60, 3)

    # 量能：量比（近5日均量 / 近60日均量）+ 突破日量价配合
    if len(vols) >= 60:
        v5 = sum(vols[-5:]) / 5
        v60 = sum(vols[-60:]) / 60
        r["volume"] = {"vol_ratio_5v60": v5 / v60 if v60 else None,
                       "last_vs_avg60": vols[-1] / v60 if v60 else None,
                       "trend": "放量" if v60 and v5 / v60 > 1.15 else
                                ("缩量" if v60 and v5 / v60 < 0.85 else "均量")}
    else:
        r["volume"] = None

    if bench_bars:
        r["relative_strength"] = relative_strength(bars, bench_bars)

    r["posture"] = _posture(r)
    return r


def _posture(r):
    """三轴启发式标签：趋势 / 动能 / 位置。明确是读数解读，非买卖建议。"""
    trend = r["ma"]["trend"]
    trend_lbl = {"up": "上升趋势", "up-weak": "偏多", "down": "下降趋势",
                 "down-weak": "偏空", "range": "震荡", "unknown": "趋势未明"}.get(trend, "趋势未明")

    rsi_v = r["rsi14"]
    macd_v = r["macd"]
    mom = []
    if rsi_v is not None:
        if rsi_v >= 70:
            mom.append("RSI超买")
        elif rsi_v <= 30:
            mom.append("RSI超卖")
    if macd_v:
        if macd_v["hist"] > 0 and (macd_v["hist_prev"] or 0) <= 0:
            mom.append("MACD金叉")
        elif macd_v["hist"] < 0 and (macd_v["hist_prev"] or 0) >= 0:
            mom.append("MACD死叉")
        elif macd_v["hist"] > 0:
            mom.append("MACD多头")
        else:
            mom.append("MACD空头")
    mom_lbl = "、".join(mom) if mom else "动能中性"

    fh = r["range52w"].get("from_high_pct")
    pos_lbl = "位置未知"
    if fh is not None:
        if fh >= -5:
            pos_lbl = "逼近52周高位"
        elif fh <= -50:
            pos_lbl = "深跌（距高点腰斩以上）"
        elif fh <= -25:
            pos_lbl = "中低位（距高点-25%以上）"
        else:
            pos_lbl = "中位"

    return {"trend": trend_lbl, "momentum": mom_lbl, "position": pos_lbl,
            "one_line": f"{trend_lbl} · {mom_lbl} · {pos_lbl}"}


# --------------------------------------------------------------------------
# 数据接入
# --------------------------------------------------------------------------
def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        bars = []
        for row in rd:
            g = {k.lower(): v for k, v in row.items()}
            bars.append({"date": g.get("date"),
                         "open": _f(g.get("open")), "high": _f(g.get("high")),
                         "low": _f(g.get("low")), "close": _f(g.get("close")),
                         "volume": _f(g.get("volume"))})
    return bars


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fetch(symbol, period):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import datalayer as dl
    env = dl.fetch_ohlcv(symbol, freq="daily", period=period)
    return env["bars"], env.get("name"), env["market"]


# --------------------------------------------------------------------------
# 展示
# --------------------------------------------------------------------------
def _fmt(x, p=2, suf=""):
    return f"{x:.{p}f}{suf}" if isinstance(x, (int, float)) else "—"


def render(r, name, symbol, market):
    L = []
    L.append("=" * 66)
    L.append(f"技术面 · {name} [{symbol} · {market}]  现价 {_fmt(r['last'])}")
    L.append(f"  {r['n_bars']} 根K线  {r['date_first']} ~ {r['date_last']}（日线）")
    L.append("=" * 66)
    p = r["posture"]
    L.append(f"  ▶ 技术姿态：{p['one_line']}")
    L.append("    （技术面是择时/确认/风控的叠加层，不构成买卖理由——先看基本面）")

    ma = r["ma"]
    L.append("\n  趋势（均线）:")
    L.append(f"    SMA20/50/200:  {_fmt(ma['sma20'])} / {_fmt(ma['sma50'])} / {_fmt(ma['sma200'])}")
    L.append(f"    排列:          {ma['alignment']}")
    if ma["cross"]:
        L.append(f"    交叉:          {ma['cross']}")

    L.append("\n  动量:")
    rv = r["rsi14"]
    rsi_tag = "（超买≥70）" if rv and rv >= 70 else ("（超卖≤30）" if rv and rv <= 30 else "")
    L.append(f"    RSI(14):       {_fmt(rv, 1)} {rsi_tag}")
    m = r["macd"]
    if m:
        L.append(f"    MACD:          柱 {_fmt(m['hist'], 3)}  (macd {_fmt(m['macd'], 3)} / signal {_fmt(m['signal'], 3)})")
    mo = r["momentum"]
    L.append(f"    动量 ROC:      1月 {_fmt(mo['roc_1m'], 1, '%')} · 3月 {_fmt(mo['roc_3m'], 1, '%')} · "
             f"6月 {_fmt(mo['roc_6m'], 1, '%')} · 12月 {_fmt(mo['roc_12m'], 1, '%')}")

    L.append("\n  波动:")
    L.append(f"    ATR(14):       {_fmt(r['atr14'])}  ({_fmt(r['atr_pct'], 2, '%')} 现价)")
    bb = r["bollinger"]
    if bb:
        L.append(f"    布林(20,2σ):   下 {_fmt(bb['lower'])} · 中 {_fmt(bb['mid'])} · 上 {_fmt(bb['upper'])}")
        L.append(f"                   %B {_fmt(bb['pctB'], 2)}（>1 破上轨/<0 破下轨） · 带宽 {_fmt(bb['bandwidth'] * 100, 1, '%')}")

    if r.get("volume"):
        v = r["volume"]
        L.append("\n  量能:")
        L.append(f"    量比(5/60):    {_fmt(v['vol_ratio_5v60'], 2)}  →  {v['trend']}")
        L.append(f"    昨量/60均量:   {_fmt(v['last_vs_avg60'], 2)}")

    rg = r["range52w"]
    L.append("\n  位置 & 关键价位:")
    L.append(f"    52周高/低:     {_fmt(rg['high'])} / {_fmt(rg['low'])}  "
             f"(距高 {_fmt(rg['from_high_pct'], 1, '%')} · 距低 {_fmt(rg['from_low_pct'], 1, '%')})")
    lv = r["levels"]
    L.append(f"    近端阻力:      {', '.join(_fmt(x) for x in lv['resistance']) or '—'}")
    L.append(f"    近端支撑:      {', '.join(_fmt(x) for x in lv['support']) or '—'}")

    if r.get("relative_strength"):
        rs = r["relative_strength"]
        L.append("\n  相对强弱（对基准）:")
        L.append(f"    起点至今:      {_fmt(rs['outperform_since_start_pct'], 1, '%')}（>0 跑赢）")
        segs = [f"{k.split('_')[2]}日 {_fmt(v, 1, '%')}" for k, v in rs.items() if k.startswith("rs_chg_")]
        if segs:
            L.append(f"    近端RS变化:    {' · '.join(segs)}")

    L.append("\n  ⚠️ 技术指标基于历史价量、有滞后与假信号；仅辅助择时与风控，不改变基本面结论。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="技术面分析（零依赖·价值投资叠加层）")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("analyze", help="分析单只技术面")
    a.add_argument("symbol", nargs="?", help="标的（自动路由市场）；或用 --csv 离线")
    a.add_argument("--csv", help="离线 OHLCV: date,open,high,low,close,volume")
    a.add_argument("--period", default="2y", choices=["1y", "2y", "5y", "10y", "max"])
    a.add_argument("--benchmark", help="相对强弱基准（缺省按市场：A沪深300/HK盈富/US SPY）")
    a.add_argument("--no-rs", action="store_true", help="跳过相对强弱")
    a.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd != "analyze":
        ap.print_help()
        return

    if args.csv:
        bars, name, market = load_csv(args.csv), os.path.basename(args.csv), "?"
        symbol = name
    elif args.symbol:
        bars, name, market = fetch(args.symbol, args.period)
        symbol = args.symbol
    else:
        raise SystemExit("需给 symbol 或 --csv")
    if len(bars) < 30:
        raise SystemExit(f"K线过少（{len(bars)} 根），无法计算技术指标（至少约 30 根）")

    bench_bars = None
    if not args.no_rs and not args.csv:
        bench = args.benchmark or DEFAULT_BENCH.get(market)
        if bench:
            try:
                bench_bars, _, _ = fetch(bench, args.period)
            except Exception as e:  # noqa: BLE001 基准取数失败不阻断主分析
                print(f"（相对强弱跳过：基准 {bench} 取数失败：{e}）", file=sys.stderr)

    r = compute(bars, bench_bars)
    if args.json:
        print(json.dumps({"symbol": symbol, "name": name, "market": market, **r},
                         ensure_ascii=False, indent=2))
    else:
        print(render(r, name, symbol, market))


if __name__ == "__main__":
    main()
