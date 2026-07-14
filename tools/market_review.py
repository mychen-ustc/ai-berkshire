#!/usr/bin/env python3
"""每日市场全景盘点（零外部依赖，仅 stdlib）。P3 运营节奏 · 市场级（区别于组合级 review.py）。

对上一交易日**整个市场**做全面综述——不局限于你的持仓：
  ① 大盘概览：A股(上证/深证/创业板/沪深300) · 港股(恒生) · 美股(标普/纳指) 涨跌。
  ② 市场广度与情绪：A股涨跌停家数 · 三市场恐惧贪婪 + VIX。
  ③ 资金与异动：龙虎榜机构买入 · 高连板题材。
  ④ 热门板块：涨停家数聚合。
  ⑤ 宏观与政策要闻：美林 regime + 新浪7×24 政策头条。
  ⑥ 市场综述：普涨/普跌/分化 + 广度 + 情绪 + 主线 + 关注点。

配套组合级 review.py：本工具看"整个市场发生了什么"，review 看"我的组合/watchlist 该怎么办"。

用法：
  python3 tools/market_review.py                 # 文本
  python3 tools/market_review.py --md --html      # 导出到 reports/private/market/
诚实边界：综述为信号聚合、非预测；龙虎榜/涨停/词典情感为粗筛线索，须人工研判。仅覆盖免费源。
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402
import sentiment as st  # noqa: E402
import macro_regime as mac  # noqa: E402
import radar as rad  # noqa: E402
import news_engine as ne  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDICES = [("A股", "上证指数", "sh000001"), ("A股", "深证成指", "sz399001"),
           ("A股", "创业板指", "sz399006"), ("A股", "沪深300", "sh000300"),
           ("港股", "恒生(盈富)", "2800.HK"),
           ("美股", "标普500(SPY)", "SPY"), ("美股", "纳指100(QQQ)", "QQQ")]


def _today():
    return datetime.now().strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# 纯逻辑：市场综述
# --------------------------------------------------------------------------
def _breadth_word(idx):
    """一组涨跌幅 → 普涨/普跌/分化。纯函数。"""
    ch = [x["chg"] for x in idx if isinstance(x.get("chg"), (int, float))]
    if not ch:
        return "—"
    up = sum(1 for c in ch if c > 0)
    dn = sum(1 for c in ch if c < 0)
    if up == len(ch):
        return "普涨"
    if dn == len(ch):
        return "普跌"
    return "涨跌分化"


def synthesize(out):
    bits = []
    a = [x for x in out["indices"] if x["market"] == "A股"]
    us = [x for x in out["indices"] if x["market"] == "美股"]
    if a:
        bits.append(f"A股{_breadth_word(a)}")
    if us:
        bits.append(f"美股{_breadth_word(us)}")
    b = out.get("breadth")
    if b and b.get("limit_up") is not None:
        bits.append(f"A股涨停{b['limit_up']}/跌停{b['limit_down']}({b.get('label', '')[:4]})")
    se = out.get("sentiment", {})
    greedy = [k for k, v in se.items() if v and (v.get("score") or 0) >= 70]
    if greedy:
        bits.append("情绪偏热(" + "/".join(greedy) + ")")
    reg = (out.get("macro") or {}).get("regime")
    if reg:
        bits.append(f"宏观{reg}")
    sec = (out.get("sectors") or {}).get("sectors", [])
    if sec:
        bits.append("主线:" + "/".join(s["sector"] for s in sec[:2]))
    return " · ".join(bits) or "市场信号中性"


# --------------------------------------------------------------------------
# 采集
# --------------------------------------------------------------------------
def run():
    out = {"date": _today(), "indices": []}
    for mkt, name, sym in INDICES:
        try:
            q = dl.fetch_quote(sym, cross=False)
            out["indices"].append({"market": mkt, "name": name, "sym": sym,
                                   "price": q.get("price"), "chg": q.get("change_pct")})
        except Exception:  # noqa: BLE001
            pass
    try:
        out["breadth"] = st.fetch_breadth()
    except Exception:  # noqa: BLE001
        out["breadth"] = None
    out["sentiment"] = {}
    for m in ("A", "US", "HK"):
        try:
            d = st.market_sentiment(m)
            out["sentiment"][m] = {"score": d["score"], "label": d["label"], "raw": d.get("raw", {})}
        except Exception:  # noqa: BLE001
            pass
    try:
        out["macro"] = mac.now()
    except Exception:  # noqa: BLE001
        out["macro"] = None
    try:
        out["dragon"] = rad.dragon_leads(12)
    except Exception:  # noqa: BLE001
        out["dragon"] = {"date": None, "leads": []}
    try:
        lu = rad.limitup_leads(40)
        lu["pool"].sort(key=lambda x: -(x.get("lbc") or 0))
        out["limitup"] = lu
    except Exception:  # noqa: BLE001
        out["limitup"] = {"pool": [], "total": None}
    try:
        out["sectors"] = rad.hot_sectors()
    except Exception:  # noqa: BLE001
        out["sectors"] = {"sectors": []}
    try:
        out["news"] = ne.fetch_market_news(8)
    except Exception:  # noqa: BLE001
        out["news"] = {}
    out["trade_date"] = (out["dragon"].get("date") or str((out.get("breadth") or {}).get("qdate") or ""))
    out["summary"] = synthesize(out)
    return out


# --------------------------------------------------------------------------
# 展示：文本 / markdown / html
# --------------------------------------------------------------------------
def _chg(c):
    return f"{c:+.2f}%" if isinstance(c, (int, float)) else "—"


def render_text(o):
    L = ["=" * 70, f"每日市场全景盘点 · {o['date']}（交易日 {o['trade_date']}）", "=" * 70]
    L.append(f"\n【市场综述】{o['summary']}")
    L.append("\n【一、大盘概览】")
    cur = None
    for x in o["indices"]:
        if x["market"] != cur:
            cur = x["market"]
            L.append(f"  {cur}:")
        L.append(f"    {x['name']:<14}{x['price']}　{_chg(x['chg'])}")
    L.append("\n【二、市场广度与情绪】")
    b = o.get("breadth") or {}
    L.append(f"  A股广度: 涨停 {b.get('limit_up', '—')}/跌停 {b.get('limit_down', '—')}（{b.get('label', '—')}）")
    se = o.get("sentiment", {})
    L.append("  恐惧贪婪: " + " · ".join(f"{k} {v['score']}({v['label'][:4]})" for k, v in se.items()))
    vix = (se.get("US", {}).get("raw") or {}).get("vix")
    if vix:
        L.append(f"  VIX: {vix}")
    L.append("\n【三、资金与异动】")
    dl_ = o.get("dragon", {})
    L.append(f"  龙虎榜机构买入（{len(dl_.get('leads', []))}只）:")
    for r in dl_.get("leads", [])[:8]:
        L.append(f"    {r['name']}({r['code']}) {_chg(r['change'])} · {r['explain'][:24]}")
    lb = [x for x in o.get("limitup", {}).get("pool", []) if (x.get("lbc") or 0) >= 2][:6]
    if lb:
        L.append("  高连板题材: " + " · ".join(f"{x['name']}({x['lbc']}板/{x['sector']})" for x in lb))
    L.append("\n【四、热门板块】(涨停家数聚合)")
    L.append("  " + " · ".join(f"{s['sector']}({s['limit_up_count']})" for s in o.get("sectors", {}).get("sectors", [])) or "  —")
    L.append("\n【五、宏观与政策要闻】")
    md_ = o.get("macro") or {}
    if md_:
        L.append(f"  宏观: {md_.get('icon', '')}{md_.get('regime', '—')}（PMI {(md_.get('pmi') or {}).get('make', '—')} · CPI {(md_.get('cpi') or {}).get('yoy', '—')}% · 10Y {md_.get('y10y', '—')}%）")
    nw = o.get("news") or {}
    for c in [x for x in nw.get("cn", []) if x.get("is_policy")][:3]:
        dot = {"利好": "🟢", "利空": "🔴", "中性": "⚪"}[c["direction"]]
        L.append(f"  🏛️{dot} {c['text'][:54]}")
    for x in nw.get("us", [])[:2]:
        L.append(f"  🌐 [{x['source']}] {x['headline'][:50]}")
    L.append("\n  ⚠️ 综述为信号聚合、非预测；龙虎榜/涨停/词典情感为粗筛线索，须人工研判。")
    return "\n".join(L)


def render_md(o):
    L = [f"# 每日市场全景盘点 · {o['date']}（交易日 {o['trade_date']}）", "",
         f"> **市场综述**：{o['summary']}", "", "## 一、大盘概览", "", "| 市场 | 指数 | 收盘 | 涨跌 |", "|---|---|---|---|"]
    for x in o["indices"]:
        L.append(f"| {x['market']} | {x['name']} | {x['price']} | {_chg(x['chg'])} |")
    b = o.get("breadth") or {}
    se = o.get("sentiment", {})
    L.append("\n## 二、市场广度与情绪")
    L.append(f"- **A股广度**：涨停 {b.get('limit_up', '—')}/跌停 {b.get('limit_down', '—')}（{b.get('label', '—')}）")
    L.append("- **恐惧贪婪**：" + " · ".join(f"{k} {v['score']}({v['label'][:4]})" for k, v in se.items()))
    L.append("\n## 三、资金与异动")
    L.append(f"**龙虎榜机构买入**（{len(o.get('dragon', {}).get('leads', []))} 只）：")
    for r in o.get("dragon", {}).get("leads", [])[:10]:
        L.append(f"- {r['name']}（{r['code']}）{_chg(r['change'])} · {r['explain'][:26]}")
    lb = [x for x in o.get("limitup", {}).get("pool", []) if (x.get("lbc") or 0) >= 2][:8]
    if lb:
        L.append("\n**高连板题材**：" + " · ".join(f"{x['name']}({x['lbc']}板/{x['sector']})" for x in lb))
    L.append("\n## 四、热门板块（涨停家数聚合）")
    L.append("- " + " · ".join(f"{s['sector']}({s['limit_up_count']})" for s in o.get("sectors", {}).get("sectors", [])))
    L.append("\n## 五、宏观与政策要闻")
    md_ = o.get("macro") or {}
    if md_:
        L.append(f"- **宏观**：{md_.get('icon', '')}{md_.get('regime', '—')}（PMI {(md_.get('pmi') or {}).get('make', '—')} · CPI {(md_.get('cpi') or {}).get('yoy', '—')}% · M2 {(md_.get('m2') or {}).get('m2_yoy', '—')}% · 10Y {md_.get('y10y', '—')}%）")
    nw = o.get("news") or {}
    for c in [x for x in nw.get("cn", []) if x.get("is_policy")][:4]:
        dot = {"利好": "🟢", "利空": "🔴", "中性": "⚪"}[c["direction"]]
        L.append(f"- 🏛️{dot} {c['text'][:60]}")
    for x in nw.get("us", [])[:3]:
        L.append(f"- 🌐 [{x['source']}] {x['headline'][:56]}")
    L.append("\n---\n*数据源：东财(指数/龙虎榜/涨停/宏观) · Yahoo(美股/VIX) · 新浪7×24(要闻)。综述为信号聚合、非预测；须人工研判。*")
    return "\n".join(L)


def render_html(o):
    import html as _h
    rows = "".join(f'<tr><td>{x["market"]}</td><td>{_h.escape(x["name"])}</td><td>{x["price"]}</td>'
                   f'<td class="{("up" if (x.get("chg") or 0)>0 else "dn")}">{_chg(x["chg"])}</td></tr>' for x in o["indices"])
    b = o.get("breadth") or {}
    se = o.get("sentiment", {})
    dragon = "".join(f'<li><b>{_h.escape(r["name"])}</b>（{r["code"]}）{_chg(r["change"])} · {_h.escape(r["explain"][:28])}</li>'
                     for r in o.get("dragon", {}).get("leads", [])[:10]) or "<li>无</li>"
    sect = " · ".join(f'{_h.escape(s["sector"])}({s["limit_up_count"]})' for s in o.get("sectors", {}).get("sectors", [])) or "—"
    nw = o.get("news") or {}
    news = ""
    for c in [x for x in nw.get("cn", []) if x.get("is_policy")][:4]:
        dot = {"利好": "🟢", "利空": "🔴", "中性": "⚪"}[c["direction"]]
        news += f'<li>🏛️{dot} {_h.escape(c["text"][:64])}</li>'
    for x in nw.get("us", [])[:3]:
        news += f'<li>🌐 [{_h.escape(x["source"])}] {_h.escape(x["headline"][:58])}</li>'
    md_ = o.get("macro") or {}
    senti_line = " · ".join(f'{k} {v["score"]}({_h.escape(v["label"][:4])})' for k, v in se.items())
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>每日市场盘点 {o['date']}</title><style>
:root{{--bg:#f6f8fb;--card:#fff;--ink:#152030;--muted:#5b6472;--line:#e4e8ef;--head:#0b2942;--accent:#0e7490;--green:#16a34a;--red:#dc2626;}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0e1116;--card:#161b22;--ink:#e6edf3;--muted:#9aa5b1;--line:#2a3139;--head:#cfe8f5;--accent:#22b8cf;--green:#34d399;--red:#f87171;}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}}
.wrap{{max-width:900px;margin:0 auto;padding:24px 18px 60px}}h1{{color:var(--head);font-size:1.35rem}}.sub{{color:var(--muted);font-size:.84rem}}
.sum{{background:linear-gradient(90deg,#dbeafe,#dcfce7);border-radius:12px;padding:12px 18px;margin:12px 0;font-size:.95rem}}
@media(prefers-color-scheme:dark){{.sum{{background:linear-gradient(90deg,#0f2038,#0f2e1e)}}}}
h2{{color:var(--head);font-size:1.08rem;border-left:5px solid var(--accent);padding-left:.5em;margin-top:1.4em}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:8px 0;font-size:.88rem}}
table{{border-collapse:collapse;width:100%;font-size:.85rem}}th,td{{padding:6px 9px;border-bottom:1px solid var(--line);text-align:left}}th{{background:var(--head);color:#fff}}
.up{{color:var(--green);font-weight:700}}.dn{{color:var(--red);font-weight:700}}
ul{{margin:.3em 0;padding-left:1.3em}}li{{margin:.25em 0;font-size:.87rem}}
footer{{color:var(--muted);font-size:.78rem;margin-top:20px;border-top:1px solid var(--line);padding-top:10px}}</style></head><body><div class="wrap">
<h1>每日市场全景盘点</h1><div class="sub">{o['date']} · 交易日 {o['trade_date']}</div>
<div class="sum"><b>市场综述：</b>{_h.escape(o['summary'])}</div>
<h2>一、大盘概览</h2><div class="card" style="overflow-x:auto"><table><thead><tr><th>市场</th><th>指数</th><th>收盘</th><th>涨跌</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>二、市场广度与情绪</h2><div class="card">A股广度：涨停 {b.get('limit_up','—')}/跌停 {b.get('limit_down','—')}（{_h.escape(b.get('label','—'))}）<br>恐惧贪婪：{senti_line}</div>
<h2>三、资金与异动</h2><div class="card">龙虎榜机构买入：<ul>{dragon}</ul></div>
<h2>四、热门板块（涨停家数聚合）</h2><div class="card">{sect}</div>
<h2>五、宏观与政策要闻</h2><div class="card">宏观：{md_.get('icon','')}{_h.escape(md_.get('regime','—'))}（PMI {(md_.get('pmi') or {}).get('make','—')} · CPI {(md_.get('cpi') or {}).get('yoy','—')}% · 10Y {md_.get('y10y','—')}%）<ul>{news}</ul></div>
<footer>每日市场盘点(market_review.py)一键生成 · 综述为信号聚合、非预测；龙虎榜/涨停/词典情感为粗筛线索，须人工研判。数据源：东财/Yahoo/新浪7×24。</footer>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="每日市场全景盘点（市场级，零依赖）")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--html", action="store_true")
    args = ap.parse_args()
    o = run()
    print(render_text(o))
    outdir = os.path.join(ROOT, "reports", "private", "market")
    if args.md:
        os.makedirs(outdir, exist_ok=True)
        p = os.path.join(outdir, f"market-{o['date']}.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(render_md(o))
        print(f"\n[market] Markdown → {p}", file=sys.stderr)
    if args.html:
        os.makedirs(outdir, exist_ok=True)
        p = os.path.join(outdir, f"market-{o['date']}.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(render_html(o))
        print(f"[market] HTML → {p}", file=sys.stderr)


if __name__ == "__main__":
    main()
