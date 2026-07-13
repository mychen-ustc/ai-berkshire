#!/usr/bin/env python3
"""持股与内部人变动跟踪（零外部依赖，仅 stdlib）。

补 moneyflow 的诚实缺口：主力资金流是逐笔单量的**估算**，而这里看**一手披露**——
谁真的在买卖、筹码在集中还是分散：
  ① 龙虎榜（东财）：机构/游资席位异动、成交额占比、当日涨跌——"聪明钱异动"的一手记录。
  ② 股东户数（东财）：户数环比变化——户数下降=筹码集中(常伴吸筹)、上升=筹码分散。
它是叠加层——验证资金面论点，**永不替代基本面**。

诚实边界：
  · 龙虎榜是「异动才上榜」的**样本**、非全量资金；游资上榜≠长期资金；只反映当日。
  · 股东户数为**季度披露、滞后**；集中度只是概率性信号，非因果。
  · **仅 A 股**（东财）；美股机构持仓需 SEC EDGAR 13F、内部人交易需 Form 4（本版本未接入，见路线图 P4-8）。

用法：
  python3 tools/holdings_tracker.py dragon 300750 --limit 8      # 龙虎榜上榜记录
  python3 tools/holdings_tracker.py holders 300750               # 股东户数变化
  python3 tools/holdings_tracker.py track 300750                 # 二者合一 + 综合姿态
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402

BASE = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def _acode(symbol):
    info = dl.detect(symbol)
    if info["market"] != "A":
        raise ValueError(f"持股/龙虎榜/户数当前仅 A 股（东财），{info['symbol']} 为 {info['market']} 股；"
                         "美股需 SEC EDGAR 13F/Form4（本版本未接入）")
    return re.sub(r"\D", "", info["tencent"])[-6:], info["symbol"]


def _get(report, code, sort, size, extra=""):
    url = (f"{BASE}?reportName={report}&columns=ALL"
           f"&filter=(SECURITY_CODE%3D%22{code}%22){extra}&pageSize={size}"
           f"&sortColumns={sort}&sortTypes=-1")
    d = json.loads(dl._curl(url, headers=["Referer: https://data.eastmoney.com/"]))
    return ((d.get("result") or {}).get("data")) or []


# --------------------------------------------------------------------------
# 龙虎榜
# --------------------------------------------------------------------------
def build_dragon(rows, sym):
    """纯函数：东财龙虎榜行 → 结构化 dict（可离线测试）。"""
    out = []
    for r in rows:
        out.append({
            "date": (r.get("TRADE_DATE") or "")[:10],
            "explain": r.get("EXPLAIN") or "",
            "deal_amt_yi": round((r.get("BILLBOARD_DEAL_AMT") or 0) / 1e8, 2),
            "deal_ratio_pct": round(r.get("DEAL_AMOUNT_RATIO"), 2) if isinstance(r.get("DEAL_AMOUNT_RATIO"), (int, float)) else None,
            "change_rate": r.get("CHANGE_RATE"),
            "close": r.get("CLOSE_PRICE"),
        })
    inst = sum(1 for x in out if "机构" in x["explain"])
    return {"symbol": sym, "n": len(out), "inst_appearances": inst, "records": out}


def dragon_tiger(symbol, limit=8):
    code, sym = _acode(symbol)
    rows = _get("RPT_DAILYBILLBOARD_DETAILSNEW", code, "TRADE_DATE", limit)
    return build_dragon(rows, sym)


# --------------------------------------------------------------------------
# 股东户数
# --------------------------------------------------------------------------
def build_holder(rows, sym):
    """纯函数：东财股东户数行 → 结构化 dict + 集中度信号（可离线测试）。"""
    if not rows:
        return {"symbol": sym, "available": False}
    r = rows[0]
    chg = r.get("HOLDER_NUM_CHANGE")
    ratio = r.get("HOLDER_NUM_RATIO")
    signal = "—"
    if isinstance(ratio, (int, float)):
        if ratio < -3:
            signal = "🟢 户数明显下降 → 筹码集中（常伴主力吸筹）"
        elif ratio > 3:
            signal = "🔴 户数明显上升 → 筹码分散（散户进场/主力派发）"
        else:
            signal = "⚪ 户数基本平稳"
    return {"symbol": sym, "available": True,
            "holder_num": r.get("HOLDER_NUM"), "pre_holder_num": r.get("PRE_HOLDER_NUM"),
            "change": chg, "change_pct": round(ratio, 2) if isinstance(ratio, (int, float)) else None,
            "end_date": (r.get("END_DATE") or "")[:10], "pre_end_date": (r.get("PRE_END_DATE") or "")[:10],
            "signal": signal}


def holder_num(symbol):
    code, sym = _acode(symbol)
    rows = _get("RPT_HOLDERNUMLATEST", code, "END_DATE", 1)
    return build_holder(rows, sym)


# --------------------------------------------------------------------------
# 展示
# --------------------------------------------------------------------------
def render_dragon(d):
    L = [f"龙虎榜 · {d['symbol']} · 近 {d['n']} 次上榜（其中 {d['inst_appearances']} 次有机构席位）"]
    for r in d["records"]:
        cr = f"{r['change_rate']:+.2f}%" if isinstance(r["change_rate"], (int, float)) else "—"
        L.append(f"  {r['date']}  当日{cr}  龙虎榜成交{r['deal_amt_yi']}亿(占{r['deal_ratio_pct']}%)")
        L.append(f"           {r['explain']}")
    return "\n".join(L)


def render_holders(h):
    if not h.get("available"):
        return f"股东户数 · {h['symbol']}：无数据"
    return (f"股东户数 · {h['symbol']} · 截至 {h['end_date']}\n"
            f"  最新 {h['holder_num']:,} 户（上期 {h['pre_holder_num']:,}，环比 {h['change']:+,}，{h['change_pct']:+.2f}%）\n"
            f"  {h['signal']}")


def track(symbol):
    d = dragon_tiger(symbol, 6)
    h = holder_num(symbol)
    print("=" * 62)
    print(f"持股/内部人跟踪 · {d['symbol']}")
    print("=" * 62)
    print(render_dragon(d))
    print()
    print(render_holders(h))
    # 综合姿态
    hint = []
    if d["inst_appearances"] >= 2:
        hint.append("机构频繁现身龙虎榜（异动活跃）")
    if h.get("change_pct") is not None and h["change_pct"] < -3:
        hint.append("户数下降=筹码集中")
    if h.get("change_pct") is not None and h["change_pct"] > 3:
        hint.append("户数上升=筹码分散")
    if hint:
        print(f"\n  综合: {'；'.join(hint)}")
    print("\n  ⚠️ 龙虎榜是异动样本非全量、游资≠长期资金；户数季度滞后。一手披露仅验证资金面，不替代基本面。")


def main():
    ap = argparse.ArgumentParser(description="持股/内部人跟踪（A股龙虎榜 + 股东户数，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    dg = sub.add_parser("dragon", help="龙虎榜上榜记录")
    dg.add_argument("symbol"); dg.add_argument("--limit", type=int, default=8); dg.add_argument("--json", action="store_true")
    ho = sub.add_parser("holders", help="股东户数变化")
    ho.add_argument("symbol"); ho.add_argument("--json", action="store_true")
    tr = sub.add_parser("track", help="龙虎榜 + 户数 + 综合姿态")
    tr.add_argument("symbol")
    args = ap.parse_args()

    if args.cmd == "dragon":
        d = dragon_tiger(args.symbol, args.limit)
        print(json.dumps(d, ensure_ascii=False, indent=2) if args.json else render_dragon(d))
    elif args.cmd == "holders":
        h = holder_num(args.symbol)
        print(json.dumps(h, ensure_ascii=False, indent=2) if args.json else render_holders(h))
    elif args.cmd == "track":
        track(args.symbol)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
