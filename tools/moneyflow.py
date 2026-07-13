#!/usr/bin/env python3
"""资金面分析（零外部依赖，仅 stdlib）。

价值投资里，资金面用来**验证或证伪**（不是产生）论点：谁在买？是吸筹还是派发？
量价是否背离？它是叠加层——先有基本面理由，再看资金面是否配合。

两类口径（诚实区分可得性）：
  ① 价量代理（全市场通用，从 OHLCV 计算）——
     MFI(14) 资金流量指标 · OBV 能量潮 · CMF(20) 蔡金资金流 · A/D 累积/派发线 ·
     量价背离检测（价创新高但 OBV 不创新高 = 派发预警）。
  ② A/H 主力资金流（东财按逐笔单量分类，单位元）——
     超大单/大单=主力，中单/小单=散户；主力近端净额、连续净流入天数、主力占比。
     ⚠️ 美股无「主力」逐笔口径，只能用①的价量代理。
  ③ 北向资金：沪深港通自 2024-08 起停止实时净流入披露，本工具不再拟合该口径
     （避免用失效数据误导），改以主力资金流 + 价量代理替代。

用法：
  python3 tools/moneyflow.py analyze 600519            # A股：价量代理 + 主力资金流
  python3 tools/moneyflow.py analyze AAPL              # 美股：仅价量代理
  python3 tools/moneyflow.py analyze 0700.HK --days 60
  python3 tools/moneyflow.py analyze --csv data/x.csv  # 离线价量代理(OHLCV)
"""
import argparse
import csv
import json
import os
import sys

YI = 1e8  # 亿


# --------------------------------------------------------------------------
# ① 价量代理指标（全市场通用，纯函数，可离线测试）
# --------------------------------------------------------------------------
def typical_price(b):
    return (b["high"] + b["low"] + b["close"]) / 3


def mfi(bars, n=14):
    """Money Flow Index：成交量加权的 RSI。>80 资金过热，<20 资金枯竭。"""
    tp = []
    for b in bars:
        if None in (b["high"], b["low"], b["close"]):
            tp.append(None)
        else:
            tp.append(typical_price(b))
    pos, neg = [], []
    for i in range(1, len(bars)):
        v = bars[i].get("volume")
        if tp[i] is None or tp[i - 1] is None or v is None:
            continue
        rmf = tp[i] * v
        if tp[i] > tp[i - 1]:
            pos.append(rmf); neg.append(0.0)
        elif tp[i] < tp[i - 1]:
            pos.append(0.0); neg.append(rmf)
        else:
            pos.append(0.0); neg.append(0.0)
    if len(pos) < n:
        return None
    p, q = sum(pos[-n:]), sum(neg[-n:])
    if q == 0:
        return 100.0
    return 100 - 100 / (1 + p / q)


def obv(bars):
    """On-Balance Volume 能量潮（累积）。"""
    o = [0.0]
    for i in range(1, len(bars)):
        v = bars[i].get("volume") or 0.0
        if bars[i]["close"] > bars[i - 1]["close"]:
            o.append(o[-1] + v)
        elif bars[i]["close"] < bars[i - 1]["close"]:
            o.append(o[-1] - v)
        else:
            o.append(o[-1])
    return o


def _mfv(b):
    """单根资金流量（Money Flow Volume，A/D 与 CMF 的基元）。"""
    h, l, c, v = b["high"], b["low"], b["close"], b.get("volume")
    if None in (h, l, c, v) or h == l:
        return 0.0
    return ((c - l) - (h - c)) / (h - l) * v


def cmf(bars, n=20):
    """Chaikin Money Flow：近 n 日资金流量 / 成交量。>0 净流入，<0 净流出。"""
    if len(bars) < n:
        return None
    w = bars[-n:]
    vol = sum((b.get("volume") or 0.0) for b in w)
    return sum(_mfv(b) for b in w) / vol if vol else None


def ad_line(bars):
    """Accumulation/Distribution 累积/派发线（累积）。"""
    ad = [0.0]
    for b in bars[1:]:
        ad.append(ad[-1] + _mfv(b))
    return ad


def divergence(bars, lookback=60):
    """量价背离：价新高但 OBV 未新高 = 派发预警；价新低但 OBV 未新低 = 吸筹迹象。"""
    if len(bars) < lookback + 1:
        lookback = len(bars) - 1
    w = bars[-lookback:]
    o = obv(bars)[-lookback:]
    closes = [b["close"] for b in w]
    price_hh = closes[-1] >= max(closes)
    price_ll = closes[-1] <= min(closes)
    obv_hh = o[-1] >= max(o)
    obv_ll = o[-1] <= min(o)
    if price_hh and not obv_hh:
        return "顶背离（价新高·量能未跟）→ 派发预警🔴"
    if price_ll and not obv_ll:
        return "底背离（价新低·量能未创新低）→ 吸筹迹象🟢"
    return "量价基本同步"


def compute_universal(bars):
    closes = [b["close"] for b in bars if b["close"] is not None]
    o = obv(bars)
    ad = ad_line(bars)
    r = {"n_bars": len(bars), "last": closes[-1],
         "mfi14": mfi(bars, 14), "cmf20": cmf(bars, 20),
         "divergence": divergence(bars, 60)}
    # OBV / A-D 近端方向（20 日）
    lb = min(20, len(o) - 1)
    r["obv_dir_20"] = "上升(净流入)" if o[-1] > o[-1 - lb] else ("下降(净流出)" if o[-1] < o[-1 - lb] else "走平")
    r["ad_dir_20"] = "上升(吸筹)" if ad[-1] > ad[-1 - lb] else ("下降(派发)" if ad[-1] < ad[-1 - lb] else "走平")
    r["posture"] = _universal_posture(r)
    return r


def _universal_posture(r):
    votes = 0
    if r["cmf20"] is not None:
        votes += 1 if r["cmf20"] > 0.05 else (-1 if r["cmf20"] < -0.05 else 0)
    votes += 1 if "净流入" in r["obv_dir_20"] else (-1 if "净流出" in r["obv_dir_20"] else 0)
    votes += 1 if "吸筹" in r["ad_dir_20"] else (-1 if "派发" in r["ad_dir_20"] else 0)
    if votes >= 2:
        return "价量代理：资金净流入（吸筹为主）"
    if votes <= -2:
        return "价量代理：资金净流出（派发为主）"
    return "价量代理：资金方向中性/分歧"


# --------------------------------------------------------------------------
# ② A/H 主力资金流（东财 fflow rows；纯函数）
# --------------------------------------------------------------------------
def analyze_main_flow(rows):
    """rows: 每日 dict(main/small/medium/large/xlarge/*_pct/close/change_pct)。单位元。"""
    if not rows:
        return None
    main = [r["main"] for r in rows]
    r = {"n_days": len(rows),
         "cum_main": sum(main),
         "main_1d": main[-1], "main_5d": sum(main[-5:]), "main_10d": sum(main[-10:]),
         "main_pct_last": rows[-1]["main_pct"],
         "xlarge_5d": sum(x["xlarge"] for x in rows[-5:]),
         "large_5d": sum(x["large"] for x in rows[-5:]),
         "retail_5d": sum(x["small"] + x["medium"] for x in rows[-5:])}
    # 连续净流入/流出天数
    streak, pos = 0, main[-1] > 0
    for x in reversed(main):
        if x == 0 or (x > 0) != pos:
            break
        streak += 1
    r["streak_days"] = streak
    r["streak_dir"] = "净流入" if pos else "净流出"
    r["posture"] = _main_posture(r)
    return r


def _main_posture(r):
    d5 = r["main_5d"]
    tag = "主力净流入" if d5 > 0 else ("主力净流出" if d5 < 0 else "主力持平")
    extra = ""
    if r["xlarge_5d"] > 0 and r["retail_5d"] < 0:
        extra = "（超大单进、散户出 → 典型吸筹结构）"
    elif r["xlarge_5d"] < 0 and r["retail_5d"] > 0:
        extra = "（超大单出、散户接 → 典型派发结构）"
    return f"{tag}·近5日 {d5 / YI:+.2f}亿 {extra}".strip()


# --------------------------------------------------------------------------
# 数据接入
# --------------------------------------------------------------------------
def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        bars = []
        for row in rd:
            g = {k.lower(): v for k, v in row.items()}
            bars.append({"date": g.get("date"), "open": _f(g.get("open")),
                         "high": _f(g.get("high")), "low": _f(g.get("low")),
                         "close": _f(g.get("close")), "volume": _f(g.get("volume"))})
    return bars


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _dl():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import datalayer as dl
    return dl


# --------------------------------------------------------------------------
# 展示
# --------------------------------------------------------------------------
def _fmt(x, p=2, suf=""):
    return f"{x:.{p}f}{suf}" if isinstance(x, (int, float)) else "—"


def render(uni, mainflow, name, symbol, market, unit):
    L = []
    L.append("=" * 66)
    L.append(f"资金面 · {name} [{symbol} · {market}]  现价 {_fmt(uni['last'])}")
    L.append("=" * 66)
    L.append(f"  ▶ {uni['posture']}")
    if mainflow:
        L.append(f"  ▶ {mainflow['posture']}")
    L.append("    （资金面用来验证/证伪论点，不产生买卖理由——先有基本面）")

    L.append("\n  ① 价量代理（全市场通用，由 OHLCV 计算）:")
    mf = uni["mfi14"]
    mfi_tag = "（>80 过热）" if mf and mf > 80 else ("（<20 枯竭）" if mf and mf < 20 else "")
    L.append(f"    MFI(14):       {_fmt(mf, 1)} {mfi_tag}")
    L.append(f"    CMF(20):       {_fmt(uni['cmf20'], 3)}（>0 净流入 / <0 净流出）")
    L.append(f"    OBV 20日:      {uni['obv_dir_20']}")
    L.append(f"    A/D 20日:      {uni['ad_dir_20']}")
    L.append(f"    量价背离:      {uni['divergence']}")

    if mainflow:
        m = mainflow
        L.append(f"\n  ② 主力资金流（东财逐笔单量分类，单位{unit}，{m['n_days']}日窗口）:")
        L.append(f"    昨日主力净额:  {m['main_1d'] / YI:+.2f}亿  (占成交 {_fmt(m['main_pct_last'], 1, '%')})")
        L.append(f"    近5/10日主力:  {m['main_5d'] / YI:+.2f}亿 / {m['main_10d'] / YI:+.2f}亿")
        L.append(f"    窗口累计主力:  {m['cum_main'] / YI:+.2f}亿")
        L.append(f"    近5日拆分:     超大单 {m['xlarge_5d'] / YI:+.2f}亿 · 大单 {m['large_5d'] / YI:+.2f}亿 · "
                 f"散户(中+小) {m['retail_5d'] / YI:+.2f}亿")
        L.append(f"    连续:          {m['streak_days']} 日{m['streak_dir']}")
    else:
        L.append("\n  ② 主力资金流：美股无逐笔「主力」口径，以上①价量代理即为资金方向判断。")

    L.append("\n  ⚠️ 北向资金实时净流入自 2024-08 停止披露，本工具不拟合该失效口径。")
    L.append("  ⚠️ 资金流有滞后与噪声，单日大额常受打新/指数调仓/大宗干扰；看趋势不看单日。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="资金面分析（零依赖·价值投资叠加层）")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("analyze", help="分析单只资金面")
    a.add_argument("symbol", nargs="?", help="标的（自动路由）；或 --csv 离线")
    a.add_argument("--csv", help="离线 OHLCV（仅算价量代理）: date,open,high,low,close,volume")
    a.add_argument("--days", type=int, default=60, help="主力资金流回看天数")
    a.add_argument("--period", default="1y", choices=["1y", "2y", "5y", "10y", "max"])
    a.add_argument("--no-mainflow", action="store_true", help="跳过主力资金流（仅价量代理）")
    a.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd != "analyze":
        ap.print_help()
        return

    unit = ""
    if args.csv:
        bars = load_csv(args.csv)
        name, symbol, market = os.path.basename(args.csv), os.path.basename(args.csv), "?"
        mainflow = None
    elif args.symbol:
        dl = _dl()
        env = dl.fetch_ohlcv(args.symbol, freq="daily", period=args.period)
        bars, name, market = env["bars"], env.get("name"), env["market"]
        symbol = args.symbol
        mainflow = None
        if not args.no_mainflow and market in ("A", "HK"):
            try:
                ff = dl.fetch_fund_flow(args.symbol, days=args.days)
                unit = ff["unit"]
                mainflow = analyze_main_flow(ff["rows"])
            except Exception as e:  # noqa: BLE001 主力资金流失败不阻断价量代理
                print(f"（主力资金流跳过：{e}）", file=sys.stderr)
    else:
        raise SystemExit("需给 symbol 或 --csv")
    if len(bars) < 25:
        raise SystemExit(f"K线过少（{len(bars)} 根），无法计算资金面指标")

    uni = compute_universal(bars)
    if args.json:
        print(json.dumps({"symbol": symbol, "name": name, "market": market,
                          "universal": uni, "main_flow": mainflow},
                         ensure_ascii=False, indent=2))
    else:
        print(render(uni, mainflow, name, symbol, market, unit))


if __name__ == "__main__":
    main()
