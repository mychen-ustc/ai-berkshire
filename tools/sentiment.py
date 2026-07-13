#!/usr/bin/env python3
"""情绪面分析（零外部依赖，仅 stdlib）。

情绪是**反向指标的原料**：极度贪婪时警惕、极度恐惧时留意机会。它是叠加层——
辅助判断"市场情绪是否走到极端、你的认知与共识差多少"，**永不替代基本面与估值**。

三个口径（诚实区分可得性）：
  ① 个股情绪（OHLCV 可算）：RSI + 距 52 周高 + 近端动量 合成 0–100 恐惧贪婪分。
  ② 市场情绪（指数技术面 + VIX）：大盘指数的 RSI/位置/动量 + VIX 风险计 合成大盘恐惧贪婪。
     A→沪深300 / US→SPY / HK→盈富2800；VIX 为全球风险计（低=自满、高=恐慌）。
  ③ 舆情情感（内置中文金融情感词典）：对新闻标题/文本打分 −1..+1（可喂 news_engine 输出）。

诚实边界：情绪指标**噪声大、易反复**；恐惧贪婪分是启发式合成、非市场共识度量；
词典法情感无法理解语境/反讽，只作粗筛。A/H 无公开 VIX，市场情绪以指数技术面为主。

用法：
  python3 tools/sentiment.py stock 600519            # 个股情绪
  python3 tools/sentiment.py market --market US       # 大盘情绪(指数+VIX)
  python3 tools/sentiment.py text "公司回购增持，业绩超预期，但面临诉讼风险"   # 舆情情感
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402
import technicals as ta  # noqa: E402

MARKET_INDEX = {"A": "sh000300", "US": "SPY", "HK": "2800.HK"}

# 中文金融情感词典（精简，可扩充）
POS_WORDS = ["增长", "超预期", "利好", "回购", "增持", "创新高", "新高", "盈利", "扭亏", "突破",
             "中标", "提价", "涨价", "扩产", "满产", "订单", "龙头", "复苏", "反弹", "强劲",
             "受益", "提升", "分红", "领先", "放量", "涨停", "高增", "翻倍", "达产", "获批",
             "签约", "合作", "增资", "定增", "回暖", "改善", "创纪录", "超市场预期", "上调"]
NEG_WORDS = ["下滑", "不及预期", "低于预期", "利空", "减持", "亏损", "预亏", "暴跌", "跌停", "退市",
             "违规", "处罚", "罚款", "诉讼", "商誉减值", "减值", "爆雷", "暴雷", "债务", "违约",
             "风险", "下调", "停产", "质押", "套现", "解禁", "警示", "问询", "立案", "调查",
             "裁员", "降价", "承压", "疲软", "萎缩", "下修", "腰斩", "亏", "跌", "利润下降"]
NEGATORS = ["不", "未", "没有", "无", "非", "难以", "尚未"]


# --------------------------------------------------------------------------
# 合成分工具（各分量归一到 0–100，越高越贪婪）
# --------------------------------------------------------------------------
def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _label(score):
    if score >= 75:
        return "极度贪婪 🤑（警惕）"
    if score >= 60:
        return "贪婪"
    if score > 40:
        return "中性"
    if score > 25:
        return "恐惧"
    return "极度恐惧 😱（留意机会）"


def _components_from_bars(bars):
    """由 OHLCV 算恐惧贪婪三分量（0–100）。"""
    closes = [b["close"] for b in bars if b["close"] is not None]
    rsi = ta.rsi(closes, 14)
    hl = ta.high_low_distance(closes, 250)
    roc = ta.roc(closes, 63)   # 近 3 月动量
    comp = {}
    comp["rsi"] = clamp(rsi) if rsi is not None else None            # RSI 本身即 0–100
    comp["position"] = clamp(100 + hl["from_high_pct"] * 2.5) if hl["from_high_pct"] is not None else None  # 距高-40%→0
    comp["momentum"] = clamp(50 + roc * (50 / 30)) if roc is not None else None                            # ±30%→0/100
    return comp, {"rsi14": rsi, "from_high_pct": hl["from_high_pct"], "roc_3m": roc}


def _composite(comp_dict):
    vals = [v for v in comp_dict.values() if v is not None]
    return sum(vals) / len(vals) if vals else None


# --------------------------------------------------------------------------
# ① 个股情绪
# --------------------------------------------------------------------------
def stock_sentiment(symbol, period="2y"):
    env = dl.fetch_ohlcv(symbol, freq="daily", period=period)
    bars = env["bars"]
    if len(bars) < 30:
        raise SystemExit(f"K线过少（{len(bars)}），无法评估情绪")
    comp, raw = _components_from_bars(bars)
    score = _composite(comp)
    return {"symbol": symbol, "name": env.get("name"), "market": env["market"],
            "score": round(score, 1) if score is not None else None,
            "label": _label(score) if score is not None else "数据不足",
            "components": {k: (round(v, 1) if v is not None else None) for k, v in comp.items()},
            "raw": {k: (round(v, 2) if v is not None else None) for k, v in raw.items()}}


# --------------------------------------------------------------------------
# ② 市场情绪（指数技术面 + VIX）
# --------------------------------------------------------------------------
def fetch_vix():
    """Yahoo ^VIX 现值（URL 编码 ^）。失败返回 None。"""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=5d"
        return dl.parse_yahoo(dl._curl(url)).get("price")
    except Exception:  # noqa: BLE001
        return None


def market_sentiment(market="US", period="2y"):
    idx = MARKET_INDEX.get(market)
    if not idx:
        raise SystemExit(f"未知市场 {market}（A/US/HK）")
    env = dl.fetch_ohlcv(idx, freq="daily", period=period)
    comp, raw = _components_from_bars(env["bars"])
    vix = fetch_vix()
    if vix is not None:
        comp["vix"] = clamp((40 - vix) / 30 * 100)   # VIX 10→贪婪100 / 40→恐惧0
        raw["vix"] = round(vix, 2)
    if market == "A":                                # A 股加市场宽度（涨停/跌停家数）
        try:
            b = fetch_breadth()
            if b["score"] is not None:
                comp["breadth"] = b["score"]
                raw["limit_up_down"] = f"涨停{b['limit_up']}/跌停{b['limit_down']}"
        except Exception:  # noqa: BLE001
            pass
    score = _composite(comp)
    return {"market": market, "index": idx, "index_name": env.get("name"),
            "score": round(score, 1) if score is not None else None,
            "label": _label(score) if score is not None else "数据不足",
            "components": {k: (round(v, 1) if v is not None else None) for k, v in comp.items()},
            "raw": raw}


# --------------------------------------------------------------------------
# ③ 舆情情感（词典法）
# --------------------------------------------------------------------------
def text_sentiment(text):
    """返回 score(−1..1)、pos/neg 命中、label。含简单否定翻转。"""
    pos, neg, hits = 0, 0, []
    for w in POS_WORDS:
        i = text.find(w)
        while i != -1:
            neg_ctx = any(text[max(0, i - 3):i].find(ng) != -1 for ng in NEGATORS)
            if neg_ctx:
                neg += 1; hits.append(f"-{w}(否定)")
            else:
                pos += 1; hits.append(f"+{w}")
            i = text.find(w, i + len(w))
    for w in NEG_WORDS:
        i = text.find(w)
        while i != -1:
            neg_ctx = any(text[max(0, i - 3):i].find(ng) != -1 for ng in NEGATORS)
            if neg_ctx:                       # 如"未减持""无风险""不亏损" → 翻为正面
                pos += 1; hits.append(f"+{w}(否定)")
            else:
                neg += 1; hits.append(f"-{w}")
            i = text.find(w, i + len(w))
    total = pos + neg
    score = (pos - neg) / total if total else 0.0
    lab = ("正面" if score > 0.2 else ("负面" if score < -0.2 else "中性")) if total else "无情感词"
    return {"score": round(score, 3), "pos": pos, "neg": neg, "label": lab,
            "hits": hits[:20], "n_words": total}


# --------------------------------------------------------------------------
# ④ 市场宽度（A 股涨停/跌停家数——极端情绪计）
# --------------------------------------------------------------------------
def _pool_tc(kind, date):
    """东财涨停(ZT)/跌停(DT)池 → (家数 tc, 实际交易日 qdate)。"""
    url = (f"https://push2ex.eastmoney.com/getTopic{kind}Pool?ut=7eea3edcaed734bea9cbfc24409ed989"
           f"&dpt=wz.ztzt&Pageindex=0&pagesize=1&sort=fund%3Aasc&date={date}")
    d = (json.loads(dl._curl(url)).get("data")) or {}
    return d.get("tc"), d.get("qdate")


def breadth_score(zt, dt):
    """涨停/跌停家数 → 0–100 情绪分（涨停多=贪婪、跌停多=恐惧）。"""
    if zt is None or dt is None:
        return None
    # 净涨停占比映射：净=zt-dt，除以总数平滑到 0–100
    tot = zt + dt
    net_ratio = (zt - dt) / tot if tot else 0.0     # -1..1
    return clamp(50 + net_ratio * 50)


def fetch_breadth():
    """A 股市场宽度：涨停/跌停家数 + 极端情绪读数。"""
    date = datetime.now().strftime("%Y%m%d")
    zt, qd = _pool_tc("ZT", date)
    dt, _ = _pool_tc("DT", date)
    score = breadth_score(zt, dt)
    if score is None:
        lab = "数据不足"
    elif score >= 70:
        lab = "情绪偏热（涨停远多于跌停）"
    elif score <= 30:
        lab = "情绪偏冷（跌停占优/恐慌）"
    else:
        lab = "情绪中性"
    return {"qdate": qd, "limit_up": zt, "limit_down": dt,
            "score": round(score, 1) if score is not None else None, "label": lab}


# --------------------------------------------------------------------------
# 展示
# --------------------------------------------------------------------------
def _bar(score):
    if score is None:
        return "—"
    n = int(score / 5)
    return "█" * n + "░" * (20 - n)


def render_score(d, title):
    L = ["=" * 60, title, "=" * 60]
    L.append(f"  恐惧贪婪分: {d['score']}/100  [{_bar(d['score'])}]  {d['label']}")
    L.append("  分量（0=极度恐惧 100=极度贪婪）:")
    names = {"rsi": "RSI 强弱", "position": "距52周高位置", "momentum": "近3月动量",
             "vix": "VIX 风险计", "breadth": "涨跌停宽度"}
    for k, v in d["components"].items():
        L.append(f"    {names.get(k, k):<14}{v if v is not None else '—'}")
    L.append(f"  原始: {d['raw']}")
    L.append("  ⚠️ 情绪是反向指标原料、噪声大：极端值才有参考价值，且永不替代基本面。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="情绪面分析（个股/市场恐惧贪婪 + 舆情情感，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("stock", help="个股情绪（OHLCV 合成恐惧贪婪）")
    s.add_argument("symbol")
    s.add_argument("--period", default="2y", choices=["1y", "2y", "5y", "10y", "max"])
    s.add_argument("--json", action="store_true")
    m = sub.add_parser("market", help="市场情绪（指数技术面 + VIX）")
    m.add_argument("--market", default="US", choices=["A", "US", "HK"])
    m.add_argument("--period", default="2y", choices=["1y", "2y", "5y", "10y", "max"])
    m.add_argument("--json", action="store_true")
    t = sub.add_parser("text", help="舆情情感（中文金融词典）")
    t.add_argument("text")
    t.add_argument("--json", action="store_true")
    b = sub.add_parser("breadth", help="A股市场宽度（涨停/跌停家数极端情绪）")
    b.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.cmd == "stock":
        d = stock_sentiment(args.symbol, args.period)
        print(json.dumps(d, ensure_ascii=False, indent=2) if args.json
              else render_score(d, f"个股情绪 · {d['name']} [{d['symbol']} · {d['market']}]"))
    elif args.cmd == "market":
        d = market_sentiment(args.market, args.period)
        print(json.dumps(d, ensure_ascii=False, indent=2) if args.json
              else render_score(d, f"市场情绪 · {args.market} 大盘 [{d['index_name']}]"))
    elif args.cmd == "text":
        d = text_sentiment(args.text)
        if args.json:
            print(json.dumps(d, ensure_ascii=False, indent=2))
        else:
            print(f"舆情情感: {d['label']}  score={d['score']}  (正{d['pos']}/负{d['neg']})")
            print(f"  命中: {'、'.join(d['hits']) or '无'}")
    elif args.cmd == "breadth":
        d = fetch_breadth()
        if args.json:
            print(json.dumps(d, ensure_ascii=False, indent=2))
        else:
            print(f"A股市场宽度 · {d['qdate']}：涨停 {d['limit_up']} / 跌停 {d['limit_down']} 家  "
                  f"→ 情绪分 {d['score']}/100  {d['label']}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
