#!/usr/bin/env python3
"""市场机会雷达（零外部依赖，仅 stdlib）。P2 机会发现。

扫描持仓/watchlist **之外**的市场动向，主动挖掘值得纳入观察的线索：
  · 龙虎榜机构买入（"聪明钱"一手席位）——最强线索。
  · 涨停/连板池（题材/情绪异动 + 所属板块）——较弱线索(动量,须警惕)。
  · 热门板块（由涨停池板块聚合）——资金关注方向。
  · 政策/宏观要闻（新浪7×24，政策关键词标记）。
自动去重你的持仓与 watchlist，只呈现**新线索**。

⚠️ 价值投资定位（关键）：雷达产出的是**"值得研究的线索池"，不是买入信号**。
龙虎榜/涨停是资金异动，须经 /investment-research 八模块基本面研究 + 估值 + forensic 验伤，
方可纳入观察名单；直接追涨龙虎榜/连板是投机，与本体系相悖。仅 A 股（东财数据）。

用法：
  python3 tools/radar.py scan                    # 全市场机会雷达(机构+连板+板块+政策)
  python3 tools/radar.py candidates --exclude "600519,603986"   # 新标的线索(去重)
  python3 tools/radar.py sectors                 # 热门板块
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402

DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def _today_compact():
    return datetime.now().strftime("%Y%m%d")


def _norm_code(sym):
    """标的 → 6 位 A 股代码（用于与龙虎榜/涨停去重）；非 A 股返回原串大写。"""
    m = re.match(r"^(?:SH|SZ|BJ)?(\d{6})", sym.strip().upper())
    return m.group(1) if m else sym.strip().upper()


# --------------------------------------------------------------------------
# 数据源
# --------------------------------------------------------------------------
def dragon_leads(limit=15):
    """最新交易日龙虎榜「机构买入」个股（强线索）。"""
    url = (f"{DC}?reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL&pageSize=60"
           "&sortColumns=TRADE_DATE,BILLBOARD_DEAL_AMT&sortTypes=-1,-1")
    d = json.loads(dl._curl(url, headers=["Referer: https://data.eastmoney.com/"]))
    rows = ((d.get("result") or {}).get("data")) or []
    if not rows:
        return {"date": None, "leads": []}
    latest = (rows[0].get("TRADE_DATE") or "")[:10]
    out, seen = [], set()
    for r in rows:
        if (r.get("TRADE_DATE") or "")[:10] != latest:
            break
        exp = r.get("EXPLAIN") or ""
        code = r.get("SECURITY_CODE")
        if "机构买入" in exp and code and code not in seen:
            seen.add(code)
            out.append({"code": code, "name": r.get("SECURITY_NAME_ABBR"),
                        "change": r.get("CHANGE_RATE"),
                        "deal_yi": round((r.get("BILLBOARD_DEAL_AMT") or 0) / 1e8, 2),
                        "explain": exp})
    return {"date": latest, "leads": out[:limit]}


def limitup_leads(limit=20, date=None):
    """涨停池（题材/连板异动 + 板块）。"""
    date = date or _today_compact()
    url = ("https://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989"
           f"&dpt=wz.ztzt&Pageindex=0&pagesize={limit}&sort=zdp%3Adesc&date={date}")
    d = (json.loads(dl._curl(url)).get("data")) or {}
    pool = d.get("pool") or []
    out = []
    for x in pool:
        out.append({"code": x.get("c"), "name": x.get("n"), "zdp": round(x.get("zdp", 0), 1),
                    "lbc": (x.get("zttj") or {}).get("days"), "sector": x.get("hybk"),
                    "turnover": round(x.get("hs", 0), 1)})
    return {"date": str(d.get("qdate") or date), "total": d.get("tc"), "pool": out}


def hot_sectors(date=None, top=6):
    """由涨停池板块聚合出热门板块（资金/情绪关注方向）。"""
    lu = limitup_leads(60, date)
    cnt = {}
    for x in lu["pool"]:
        s = x.get("sector")
        if s:
            cnt[s] = cnt.get(s, 0) + 1
    ranked = sorted(cnt.items(), key=lambda kv: -kv[1])[:top]
    return {"date": lu["date"], "sectors": [{"sector": s, "limit_up_count": c} for s, c in ranked]}


def policy_news(limit=6):
    """政策/宏观要闻（复用 news_engine 市场消息面，政策优先）。"""
    import news_engine as ne
    nw = ne.fetch_market_news(limit=10)
    pol = [c for c in nw.get("cn", []) if c.get("is_policy")]
    return {"policy": pol[:limit], "cn_tone": nw.get("cn_tone"), "us": nw.get("us", [])[:3]}


# --------------------------------------------------------------------------
# 新标的候选（去重持仓/watchlist）
# --------------------------------------------------------------------------
def merge_leads(dragon_list, limitup_pool, exclude, limit=12):
    """纯函数：龙虎榜机构买入(强) + 高连板(弱)，去重(exclude 已规范化的代码集)。可离线测试。"""
    ex = set(exclude or [])
    lu_by_code = {x["code"]: x for x in limitup_pool}
    leads = []
    for r in dragon_list:                                   # 龙虎榜机构买入（强，strength 3）
        if r["code"] in ex:
            continue
        sec = (lu_by_code.get(r["code"]) or {}).get("sector")
        leads.append({"code": r["code"], "name": r["name"], "signal": "🏛️机构龙虎榜买入",
                      "strength": 3, "detail": (r.get("explain") or "")[:26], "change": r.get("change"), "sector": sec})
    seen = {x["code"] for x in leads}
    for x in limitup_pool:                                  # 高连板（题材，弱，strength 1；≥2连板）
        if x["code"] in ex or x["code"] in seen:
            continue
        if (x.get("lbc") or 0) >= 2:
            leads.append({"code": x["code"], "name": x["name"], "signal": f"🔥{x['lbc']}连板(题材)",
                          "strength": 1, "detail": f"{x.get('sector') or ''} 换手{x.get('turnover')}%",
                          "change": x.get("zdp"), "sector": x.get("sector")})
    leads.sort(key=lambda l: -l["strength"])
    return leads[:limit]


def candidates(exclude=None, limit=12):
    """合并龙虎榜机构买入 + 高连板，去重后作为"待研究线索"。"""
    ex = {_norm_code(s) for s in (exclude or [])}
    dl_ = dragon_leads(20)
    lu = limitup_leads(40)
    return {"date": dl_["date"], "candidates": merge_leads(dl_["leads"], lu["pool"], ex, limit)}


# --------------------------------------------------------------------------
# 展示
# --------------------------------------------------------------------------
def render_scan(exclude=None):
    c = candidates(exclude, 12)
    hs = hot_sectors()
    pol = policy_news(6)
    L = ["=" * 66, f"市场机会雷达 · {c['date'] or ''}（持仓/watchlist 之外的新线索）", "=" * 66]
    L.append("\n【新标的候选线索】（须基本面研究后方可纳入观察，非买入信号）")
    if c["candidates"]:
        for x in c["candidates"]:
            ch = f"{x['change']:+.1f}%" if isinstance(x["change"], (int, float)) else "—"
            L.append(f"  {x['signal']:<16} {x['name']}({x['code']}) {ch}  {x['detail']}")
    else:
        L.append("  （无新线索）")
    L.append("\n【热门板块】（涨停家数聚合，资金/情绪关注方向）")
    L.append("  " + " · ".join(f"{s['sector']}({s['limit_up_count']})" for s in hs["sectors"]) if hs["sectors"] else "  —")
    L.append("\n【政策/宏观要闻】" + (f"（要闻情绪 {pol['cn_tone']}）" if pol["cn_tone"] is not None else ""))
    for p in pol["policy"]:
        dot = {"利好": "🟢", "利空": "🔴", "中性": "⚪"}[p["direction"]]
        L.append(f"  🏛️{dot} {p['text'][:56]}")
    for u in pol["us"][:2]:
        L.append(f"  🌐 [{u['source']}] {u['headline'][:52]}")
    L.append("\n  ⚠️ 雷达是「值得研究的线索池」、非买入信号；龙虎榜/涨停是资金异动，"
             "须经 /investment-research 基本面+估值+验伤，方可纳入观察。仅 A 股。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="市场机会雷达（龙虎榜/涨停/板块/政策，去重持仓，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("scan", help="全市场机会雷达")
    s.add_argument("--exclude", help="逗号分隔的已持有/已观察标的(去重)")
    s.add_argument("--json", action="store_true")
    c = sub.add_parser("candidates", help="新标的候选线索")
    c.add_argument("--exclude"); c.add_argument("--limit", type=int, default=12); c.add_argument("--json", action="store_true")
    sub.add_parser("sectors", help="热门板块")
    args = ap.parse_args()
    ex = [x.strip() for x in (getattr(args, "exclude", None) or "").split(",") if x.strip()]

    if args.cmd == "scan":
        if args.json:
            print(json.dumps({"candidates": candidates(ex), "sectors": hot_sectors(), "policy": policy_news()},
                             ensure_ascii=False, indent=2))
        else:
            print(render_scan(ex))
    elif args.cmd == "candidates":
        d = candidates(ex, args.limit)
        print(json.dumps(d, ensure_ascii=False, indent=2) if args.json
              else "\n".join(f"{x['signal']} {x['name']}({x['code']}) {x['detail']}" for x in d["candidates"]))
    elif args.cmd == "sectors":
        print(json.dumps(hot_sectors(), ensure_ascii=False, indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
