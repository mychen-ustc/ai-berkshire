#!/usr/bin/env python3
"""定期复盘编排器（零外部依赖，仅 stdlib）。P3 运营节奏"心跳"。

给一个账本，自动跑一轮复盘：刷新每只持仓的五面信号 → 检查红线/异动告警 →
汇总 watchlist 到期复审 + 临近催化剂 → 产出**行动清单**。设计为纯 Python（不需 LLM），
可挂 cron 定期运行（见 scripts/install-review-cron.sh）。

节奏：
  --daily     盘前轻量：告警 + 今日到期复审 + ≤7天催化剂
  --weekly    周巡检(默认)：+ 组合层因子/风险/情绪/宏观 + 本周到期复审
  --quarterly 季度复盘：+ 完整深度扫描提醒 + IPS/归因复审提醒

用法：
  python3 tools/review.py --from-ledger data/portfolio/transactions.csv --weekly
  python3 tools/review.py --from-ledger data/portfolio/transactions.csv --weekly --html
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portfolio_scan as psc  # noqa: E402
import watchlist as wl  # noqa: E402
import catalysts as cal  # noqa: E402
import datalayer as dl  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _today():
    return datetime.now().strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# 纯逻辑：单只持仓的信号告警
# --------------------------------------------------------------------------
def holding_flags(h):
    """由五面信号产出告警 [(级别, 说明)]。纯函数，可离线测试。"""
    flags = []
    tech = h.get("tech", "") or ""
    if any(k in tech for k in ("空头排列", "偏空", "下降", "深跌", "趋势未明")):
        flags.append(("🔴", f"技术转弱/无趋势：{tech}"))
    mf = h.get("main_flow", "") or ""
    if ("派发" in mf) or ("净流出" in mf):
        flags.append(("🔴", "主力资金派发/净流出"))
    con = h.get("consensus") or {}
    if con.get("revision") == "下修":
        flags.append(("🔴", "盈利预期下修"))
    senti = (h.get("senti") or {}).get("score")
    if senti is not None:
        if senti >= 75:
            flags.append(("🟡", f"情绪极度贪婪({senti})——警惕追高"))
        elif senti <= 25:
            flags.append(("🟢", f"情绪极度恐惧({senti})——留意机会"))
    return flags


def build_actions(holdings, due, imminent):
    """汇总行动清单。纯函数。"""
    acts = []
    for e in due:
        acts.append(f"📋 复审到期：{e['symbol']} {e.get('name') or ''}（{e.get('review_date')}）")
    for ev in imminent:
        acts.append(f"🔔 临近催化剂：{ev['date']} {ev['symbol']} {ev.get('detail', '')}")
    for h in holdings:
        reds = [msg for lv, msg in holding_flags(h) if lv == "🔴"]
        if reds:
            acts.append(f"⚠️ 红线关注：{h['symbol']} {h.get('name') or ''} — {'; '.join(reds)}")
    return acts


# --------------------------------------------------------------------------
# 复盘主流程
# --------------------------------------------------------------------------
def run(args):
    cadence = "quarterly" if args.quarterly else ("daily" if args.daily else "weekly")
    horizon = {"daily": 7, "weekly": 21, "quarterly": 90}[cadence]

    # 采集组合五面 + 组合层（复用 portfolio_scan）
    sargs = argparse.Namespace(from_ledger=args.from_ledger, symbols=None, weights=None,
                               fx=args.fx, deep=(cadence != "daily"), html=None, json=False)
    scan = psc.run(sargs)
    holdings = [h for h in scan["holdings"] if not h.get("error")]

    # watchlist 到期复审
    thesis = {e["symbol"].upper(): e for e in wl.load()["entries"]}
    due = [e for e in wl.load()["entries"] if wl.is_due(e.get("review_date"), _today())
           and e["state"] not in ("exiting", "archived")]

    # 催化剂（持仓 US 财报 + watchlist 手动催化剂）
    ev = []
    for h in holdings:
        if h.get("market") == "US":
            ev += cal.fetch_earnings(h["symbol"])
    try:
        ev += cal.from_watchlist_catalysts()
    except Exception:  # noqa: BLE001
        pass
    timeline = cal.build_timeline(ev, horizon, _today())
    imminent = [e for e in timeline if e.get("imminent")]

    actions = build_actions(holdings, due, imminent)
    return {"cadence": cadence, "date": _today(), "scan": scan, "due": due,
            "timeline": timeline, "imminent": imminent, "actions": actions, "thesis": thesis}


def render_text(r):
    scan, p = r["scan"], r["scan"]["portfolio"]
    L = ["=" * 70,
         f"投资组合定期复盘 · {r['cadence'].upper()} · {r['date']} · {scan['source']}",
         "=" * 70]
    # 行动清单置顶
    L.append("\n【行动清单】")
    if r["actions"]:
        for a in r["actions"]:
            L.append(f"  {a}")
    else:
        L.append("  ✅ 无紧急事项（无到期复审/临近催化剂/红线告警）")

    # 组合层
    if p.get("factor"):
        f = p["factor"]
        L.append(f"\n【组合层】有效独立因子 {f['n_eff']:.2f}/{f['n']} · PC1 {f['pc1_pct']:.1f}% · {f['verdict']}")
    if p.get("macro"):
        L.append(f"  宏观 {p['macro']['icon']} {p['macro']['regime']}")
    if p.get("market_sentiment"):
        L.append("  市场情绪 " + " · ".join(f"{k} {v['score']}({v['label'][:2]})" for k, v in p["market_sentiment"].items()))

    # 逐持仓信号 + 告警
    L.append("\n【持仓信号 + 红线检查】")
    for h in sorted(holdings_of(scan), key=lambda x: -x.get("weight", 0)):
        flags = holding_flags(h)
        tag = "  ".join(f"{lv}{msg}" for lv, msg in flags) if flags else "✓ 正常"
        L.append(f"  {(h.get('name') or h['symbol'])[:8]:<9}{h.get('weight', 0):>5}%  {tag}")
        th = r["thesis"].get(h["symbol"].upper())
        if th and th.get("red_lines") and any(lv == "🔴" for lv, _ in flags):
            L.append(f"           ↳ 红线: {th['red_lines']}")

    # 到期复审 & 催化剂
    L.append("\n【到期复审】" + (f"{len(r['due'])} 只" if r["due"] else "无"))
    for e in r["due"]:
        L.append(f"  {e['symbol']} {e.get('name') or ''} · 复审日 {e.get('review_date')} · 论点:{(e.get('thesis') or '')[:40]}")
    L.append("\n【临近催化剂(≤14天)】" + (f"{len(r['imminent'])} 项" if r["imminent"] else "无"))
    for ev in r["imminent"]:
        L.append(f"  {ev['date']} {ev['symbol']} {ev.get('detail', '')}")

    if r["cadence"] == "quarterly":
        L.append("\n【季度提醒】跑 performance/attribution 归因 + Brier 校准；复审 IPS(基准/风险预算/禁投)；用 portfolio_scan --deep 出完整体检。")
    L.append("\n  ⚠️ 复盘为工具信号聚合、非投资建议；红线是提示、须人工判断；五面皆叠加层不替代基本面。")
    return "\n".join(L)


def holdings_of(scan):
    return [h for h in scan["holdings"] if not h.get("error")]


def render_html(r):
    import html as _h
    scan, p = r["scan"], r["scan"]["portfolio"]
    acts = "".join(f"<li>{_h.escape(a)}</li>" for a in r["actions"]) or "<li>✅ 无紧急事项</li>"
    rows = ""
    for h in sorted(holdings_of(scan), key=lambda x: -x.get("weight", 0)):
        flags = holding_flags(h)
        tag = " ".join(f"{lv}{_h.escape(msg)}" for lv, msg in flags) if flags else "✓ 正常"
        rows += (f'<tr><td class="sym">{_h.escape(h.get("name") or h["symbol"])}<br><span class="mini">{h.get("weight",0)}%</span></td>'
                 f'<td>{_h.escape(h.get("tech","—"))}</td><td>{tag}</td></tr>')
    f = p.get("factor") or {}
    macro = p.get("macro") or {}
    ms = " · ".join(f"{k} {v['score']} {v['label']}" for k, v in (p.get("market_sentiment") or {}).items())
    due = "".join(f"<li>{_h.escape(e['symbol'])} {_h.escape(e.get('name') or '')} · {e.get('review_date')}</li>" for e in r["due"]) or "<li>无</li>"
    imm = "".join(f"<li>{ev['date']} {_h.escape(ev['symbol'])} {_h.escape(ev.get('detail',''))}</li>" for ev in r["imminent"]) or "<li>无</li>"
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>定期复盘 {r['date']}</title><style>
:root{{--bg:#f6f8fb;--card:#fff;--ink:#152030;--muted:#5b6472;--line:#e4e8ef;--head:#0b2942;--accent:#0e7490;--red:#dc2626;--amber:#d98a00;}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0e1116;--card:#161b22;--ink:#e6edf3;--muted:#9aa5b1;--line:#2a3139;--head:#cfe8f5;--accent:#22b8cf;--red:#f87171;--amber:#f5c542;}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}}
.wrap{{max-width:920px;margin:0 auto;padding:24px 18px 60px}}h1{{color:var(--head);font-size:1.35rem}}.sub{{color:var(--muted);font-size:.84rem}}
h2{{color:var(--head);font-size:1.1rem;border-left:5px solid var(--accent);padding-left:.5em;margin-top:1.4em}}
.act{{background:linear-gradient(90deg,#fef3c7,#fee2e2);border-radius:12px;padding:12px 18px}}
@media(prefers-color-scheme:dark){{.act{{background:linear-gradient(90deg,#33280a,#3a1414)}}}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:10px 0}}
table{{border-collapse:collapse;width:100%;font-size:.83rem}}th,td{{padding:7px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{background:var(--head);color:#fff}}.sym{{font-weight:700;color:var(--head);white-space:nowrap}}.mini{{font-size:.72rem;color:var(--muted)}}
ul{{margin:.3em 0;padding-left:1.3em}}li{{margin:.25em 0;font-size:.88rem}}
footer{{color:var(--muted);font-size:.78rem;margin-top:20px;border-top:1px solid var(--line);padding-top:10px}}</style></head><body><div class="wrap">
<h1>投资组合定期复盘 · {r['cadence'].upper()}</h1><div class="sub">{r['date']} · {_h.escape(scan['source'])} · 组合 {scan['n']} 只</div>
<h2>🎯 行动清单</h2><div class="act"><ul>{acts}</ul></div>
<h2>组合层</h2><div class="card">有效独立因子 <b>{round(f['n_eff'],2) if f.get('n_eff') else '—'}/{f.get('n','—')}</b> · PC1 {round(f['pc1_pct'],1) if f.get('pc1_pct') is not None else '—'}% · {_h.escape(f.get('verdict',''))}<br>宏观 {macro.get('icon','')} {macro.get('regime','—')} · 市场情绪 {_h.escape(ms)}</div>
<h2>持仓信号 + 红线检查</h2><div class="card" style="overflow-x:auto"><table><thead><tr><th>持仓</th><th>技术面</th><th>告警</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>到期复审</h2><div class="card"><ul>{due}</ul></div>
<h2>临近催化剂(≤14天)</h2><div class="card"><ul>{imm}</ul></div>
<footer>定期复盘工具(review.py)一键生成 · 复盘为信号聚合非投资建议 · 红线是提示须人工判断 · 五面皆叠加层 · 含真实持仓仅存本地。</footer>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="定期复盘编排器（P3 心跳，零依赖）")
    ap.add_argument("--from-ledger", default="data/portfolio/transactions.csv")
    ap.add_argument("--fx", default="USD=1,HKD=0.128,CNY=0.14")
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--weekly", action="store_true")
    ap.add_argument("--quarterly", action="store_true")
    ap.add_argument("--html", action="store_true", help="导出 HTML 到 reports/private/reviews/")
    args = ap.parse_args()
    r = run(args)
    print(render_text(r))
    if args.html:
        outdir = os.path.join(ROOT, "reports", "private", "reviews")
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, f"review-{r['cadence']}-{r['date']}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(render_html(r))
        print(f"\n[review] HTML 已导出 → {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
