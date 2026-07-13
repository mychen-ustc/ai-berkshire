#!/usr/bin/env python3
"""消息面引擎（零外部依赖，仅 stdlib）。

把"看公告/新闻"从手动升级为**结构化取数 + 事件分类 + 催化剂时间线**。它是叠加层——
帮助不漏重大事项、给出事件方向与催化剂节奏，**证据仍需回到原文核实，永不替代基本面**。

能力：
  ① A 股公告结构化取数（东财 anotice API）：日期/标题/官方分类/来源。
  ② 事件分类（关键词分类器，任何标题可用）：业绩/分红/回购/增减持/并购重组/再融资/
     监管处罚/诉讼/停复牌/管理层/合同订单/质押担保/关联交易；标记「重大事项」。
  ③ 情感方向（复用 sentiment 词典）：每条标题打分 利好/利空/中性。
  ④ 催化剂时间线：按时间归并，突出重大与近期催化剂。

诚实边界：分类基于标题关键词，可能误分/漏分，务必点原文核实；情感为词典粗筛、
不懂语境反讽；**美股/港股公告需 SEC EDGAR / 披露易等其他源，本版本仅接入 A 股东财**。

用法：
  python3 tools/news_engine.py announcements 600519 --limit 15
  python3 tools/news_engine.py classify "公司拟回购股份并披露业绩预增，但收到监管问询函"
  python3 tools/news_engine.py timeline 300750 --limit 30
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402  复用 _curl / detect
import sentiment as st  # noqa: E402  复用舆情情感词典

# 事件分类关键词（标题级）
EVENT_TAXONOMY = {
    "业绩": ["业绩预告", "业绩快报", "业绩预增", "业绩预减", "业绩预亏", "年度报告", "季度报告",
             "半年度报告", "年报", "季报", "经营数据", "主要经营"],
    "分红送转": ["权益分派", "利润分配", "分红", "派息", "送转", "现金分红", "分配方案"],
    "回购": ["回购"],
    "增减持": ["增持", "减持", "持股变动", "权益变动", "股份减持", "股份增持", "计划减持", "计划增持"],
    "并购重组": ["收购", "重组", "合并", "资产重组", "股权转让", "要约", "重大资产", "吸收合并"],
    "再融资": ["定增", "非公开发行", "可转债", "配股", "发行股份", "募集资金", "向特定对象发行"],
    "监管处罚": ["处罚", "警示函", "问询函", "关注函", "监管措施", "立案", "调查", "违规", "责令", "警示"],
    "诉讼仲裁": ["诉讼", "仲裁", "判决", "起诉"],
    "停复牌": ["停牌", "复牌"],
    "管理层": ["聘任", "辞职", "辞任", "任职", "选举董事", "董事会秘书", "董秘", "总经理", "高管"],
    "合同订单": ["中标", "签订", "合同", "订单", "签约", "框架协议", "战略合作"],
    "质押担保": ["质押", "解除质押", "对外担保", "担保"],
    "关联交易": ["关联交易"],
}
MATERIAL_EVENTS = {"并购重组", "监管处罚", "诉讼仲裁", "停复牌", "再融资"}   # 默认视为重大


# --------------------------------------------------------------------------
# 事件分类 + 情感方向
# --------------------------------------------------------------------------
def classify(title):
    """标题 → dict(tags, material, sentiment)。"""
    tags = []
    for evt, kws in EVENT_TAXONOMY.items():
        if any(k in title for k in kws):
            tags.append(evt)
    material = bool(set(tags) & MATERIAL_EVENTS)
    # 大额增减持也算重大（简单启发：标题含"减持"且含比例/大额语义时——此处保守只按分类）
    senti = st.text_sentiment(title)
    direction = "利好" if senti["score"] > 0.2 else ("利空" if senti["score"] < -0.2 else "中性")
    return {"tags": tags or ["其他"], "material": material,
            "direction": direction, "senti_score": senti["score"]}


# --------------------------------------------------------------------------
# A 股公告（东财 anotice API）
# --------------------------------------------------------------------------
def parse_em_announcements(text):
    d = json.loads(text)
    lst = (d.get("data") or {}).get("list") or []
    out = []
    for a in lst:
        cols = a.get("columns") or []
        out.append({
            "date": (a.get("notice_date") or "")[:10],
            "title": (a.get("title_ch") or a.get("title") or "").strip(),
            "official_type": cols[0]["column_name"] if cols else "",
            "art_code": a.get("art_code"),
        })
    return out


def fetch_announcements(symbol, limit=15):
    info = dl.detect(symbol)
    if info["market"] != "A":
        raise ValueError(f"公告结构化取数当前仅 A 股（东财 anotice），{info['symbol']} 为 "
                         f"{info['market']} 股；美股用 SEC EDGAR、港股用披露易（本版本未接入）")
    code = re.sub(r"\D", "", info["tencent"])[-6:]
    url = ("https://np-anotice-stock.eastmoney.com/api/security/ann?"
           f"sr=-1&page_size={int(limit)}&page_index=1&ann_type=A&client_source=web"
           f"&stock_list={code}&f_node=0&s_node=0")
    raw = dl._curl(url, headers=["Referer: https://data.eastmoney.com/"])
    anns = parse_em_announcements(raw)
    for a in anns:
        a.update(classify(a["title"]))
    return {"symbol": info["symbol"], "market": info["market"], "source": "eastmoney_anotice",
            "source_url": url, "fetched_at": dl.fetched_at_now(), "n": len(anns), "announcements": anns}


# --------------------------------------------------------------------------
# 汇总 / 展示
# --------------------------------------------------------------------------
def summarize(anns):
    tags_count, material, pos, neg = {}, 0, 0, 0
    for a in anns:
        for t in a["tags"]:
            tags_count[t] = tags_count.get(t, 0) + 1
        material += 1 if a["material"] else 0
        pos += 1 if a["direction"] == "利好" else 0
        neg += 1 if a["direction"] == "利空" else 0
    return {"n": len(anns), "material": material, "pos": pos, "neg": neg,
            "top_tags": sorted(tags_count.items(), key=lambda x: -x[1])[:6]}


def render(env, show_timeline=True):
    anns = env["announcements"]
    s = summarize(anns)
    L = ["=" * 70,
         f"消息面 · {env['symbol']} · {env['n']} 条公告（{env['source']}）",
         "=" * 70]
    L.append(f"  概览: 重大事项 {s['material']} 条 · 利好 {s['pos']} / 利空 {s['neg']}")
    L.append(f"  高频事件: {'、'.join(f'{t}×{c}' for t, c in s['top_tags']) or '—'}")
    if show_timeline:
        L.append("\n  催化剂时间线（新→旧）:")
        for a in anns:
            flag = "⚠️重大" if a["material"] else "  "
            dmark = {"利好": "🟢", "利空": "🔴", "中性": "⚪"}[a["direction"]]
            tags = "/".join(a["tags"])
            L.append(f"    {a['date']} {flag} {dmark}[{tags}] {a['title'][:44]}")
    L.append("\n  ⚠️ 分类基于标题关键词、可能误分；情感为词典粗筛。务必点原文核实，消息面永不替代基本面。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="消息面引擎（A股公告结构化 + 事件分类 + 催化剂时间线，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("announcements", help="A股公告结构化取数 + 分类")
    a.add_argument("symbol")
    a.add_argument("--limit", type=int, default=15)
    a.add_argument("--json", action="store_true")
    t = sub.add_parser("timeline", help="催化剂时间线（同 announcements，突出重大）")
    t.add_argument("symbol")
    t.add_argument("--limit", type=int, default=30)
    t.add_argument("--json", action="store_true")
    c = sub.add_parser("classify", help="对任意标题做事件分类 + 情感方向")
    c.add_argument("title")
    c.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.cmd in ("announcements", "timeline"):
        env = fetch_announcements(args.symbol, args.limit)
        if args.json:
            print(json.dumps(env, ensure_ascii=False, indent=2))
        else:
            print(render(env, show_timeline=True))
    elif args.cmd == "classify":
        r = classify(args.title)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            flag = "🔴重大事项" if r["material"] else "常规"
            print(f"事件分类: {'、'.join(r['tags'])}  [{flag}]  方向: {r['direction']}（情感 {r['senti_score']}）")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
