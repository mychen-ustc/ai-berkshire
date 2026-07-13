#!/usr/bin/env python3
"""组合全景体检编排器（零外部依赖，仅 stdlib）。

把此前反复手写的端到端驱动产品化：给一个账本/组合，一键串起
  五面（技术/资金/情绪 + A股公告催化剂）× 每个持仓
  组合层（风险 + 多因子 PCA + 市场情绪 + 宏观 regime）
→ 输出结构化 JSON + 可选综合 HTML 报告。

复用现有工具：datalayer / technicals / moneyflow / sentiment / factor_model /
portfolio_risk / macro_regime（--deep 再加 news_engine / us_consensus）。

用法：
  python3 tools/portfolio_scan.py --from-ledger reports/private/x.csv --fx "USD=1,HKD=0.128,CNY=0.14" --html out.html
  python3 tools/portfolio_scan.py --symbols "AAPL,GOOGL,600519,0700.HK" --weights "AAPL=30,GOOGL=30,600519=20,0700.HK=20"
  python3 tools/portfolio_scan.py --symbols "..." --deep     # 加公告催化剂/一致预期(慢)
"""
import argparse
import contextlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402
import technicals as ta  # noqa: E402
import moneyflow as mf  # noqa: E402
import sentiment as st  # noqa: E402
import factor_model as fm  # noqa: E402
import portfolio_risk as pr  # noqa: E402
import macro_regime as mac  # noqa: E402

BENCH = {"US": "SPY", "A": "sh000300", "HK": "2800.HK"}


# --------------------------------------------------------------------------
# 组合装载：账本 or 符号+权重
# --------------------------------------------------------------------------
def load_portfolio(args):
    if args.from_ledger:
        import ledger
        fx = pr._parse_fx(args.fx)
        pos, cash, _, _ = ledger.rebuild(ledger.load_ledger(args.from_ledger))
        held = {s: p for s, p in pos.items() if p.qty > 0}
        vals = {}
        for s, p in held.items():
            try:
                q = dl.fetch_quote(s, cross=False)
                cur = q.get("currency") or dl.detect(s)["currency"]
                vals[s] = float(p.qty) * (q["price"] or 0) * fx.get(cur, 1.0)
            except Exception:  # noqa: BLE001
                vals[s] = 0.0
        tot = sum(vals.values()) or 1.0
        return {s: round(v / tot * 100, 2) for s, v in vals.items()}, f"账本 {os.path.basename(args.from_ledger)}"
    syms = [s.strip() for s in (args.symbols or "").split(",") if s.strip()]
    if not syms:
        raise SystemExit("需 --from-ledger 或 --symbols")
    if args.weights:
        w = pr.parse_weights(args.weights, syms)
        return {s: round(w.get(s, 0) * 100, 2) for s in syms}, "自定义权重"
    return {s: round(100 / len(syms), 2) for s in syms}, "等权"


# --------------------------------------------------------------------------
# 逐持仓五面（共享一次 OHLCV）
# --------------------------------------------------------------------------
def scan_holding(sym, bench_cache, deep=False):
    r = {"symbol": sym}
    env = dl.fetch_ohlcv(sym, freq="daily", period="2y")
    bars = env["bars"]
    r["name"], r["market"] = env.get("name"), env["market"]
    t = ta.compute(bars, bench_cache.get(env["market"]))
    r["tech"] = t["posture"]["one_line"]
    rs = t.get("relative_strength")
    r["rs_pct"] = round(rs["outperform_since_start_pct"], 1) if rs else None
    u = mf.compute_universal(bars)
    r["flow"] = u["posture"]
    r["divergence"] = u["divergence"]
    comp, _ = st._components_from_bars(bars)
    sc = st._composite(comp)
    r["senti"] = {"score": round(sc, 1) if sc is not None else None,
                  "label": st._label(sc) if sc is not None else "—"}
    if env["market"] in ("A", "HK"):
        try:
            ff = dl.fetch_fund_flow(sym, days=60)
            m = mf.analyze_main_flow(ff["rows"])
            r["main_flow"] = m["posture"]
        except Exception:  # noqa: BLE001
            pass
    if deep and env["market"] == "A":
        try:
            import news_engine as ne
            nenv = ne.fetch_announcements(sym, 15)
            s = ne.summarize(nenv["announcements"])
            r["news"] = {"material": s["material"], "top": s["top_tags"][:2]}
        except Exception:  # noqa: BLE001
            pass
    if deep and env["market"] == "US":
        try:
            import us_consensus as uc
            c = uc.analyze(sym)
            r["consensus"] = {"stance": (c.get("rating") or {}).get("stance"),
                              "revision": (c.get("revision") or {}).get("momentum"),
                              "peg": c.get("peg")}
        except Exception:  # noqa: BLE001
            pass
    return r


# --------------------------------------------------------------------------
# 组合层
# --------------------------------------------------------------------------
def scan_portfolio(weights):
    syms = list(weights)
    wspec = ",".join(f"{s}={w}" for s, w in weights.items())
    out = {}
    # 因子模型
    fargs = argparse.Namespace(prices=None, from_datalayer=",".join(syms), from_ledger=None,
                               fx=None, period="2y", freq="weekly", weights=wspec,
                               benchmark=None, json=False)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            out["factor"] = fm.analyze(fargs)
    except Exception as e:  # noqa: BLE001
        out["factor_err"] = str(e)
    # 市场情绪（组合涉及的市场）
    markets = sorted({dl.detect(s)["market"] for s in syms})
    out["market_sentiment"] = {}
    for mkt in markets:
        try:
            d = st.market_sentiment(mkt)
            out["market_sentiment"][mkt] = {"score": d["score"], "label": d["label"]}
        except Exception:  # noqa: BLE001
            pass
    # 宏观
    try:
        m = mac.now()
        out["macro"] = {"regime": m["regime"], "quadrant": m["quadrant"], "icon": m["icon"]}
    except Exception:  # noqa: BLE001
        pass
    return out


def run(args):
    weights, src = load_portfolio(args)
    syms = list(weights)
    print(f"[scan] 组合来源: {src} · {len(syms)} 只 · 逐持仓五面 + 组合层…", file=sys.stderr)
    bench_cache = {}
    for mkt, b in BENCH.items():
        try:
            bench_cache[mkt] = dl.fetch_ohlcv(b, freq="daily", period="2y")["bars"]
        except Exception:  # noqa: BLE001
            bench_cache[mkt] = None
    holdings = []
    for s in syms:
        try:
            h = scan_holding(s, bench_cache, deep=args.deep)
            h["weight"] = weights[s]
            holdings.append(h)
            print(f"  ✓ {s}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            holdings.append({"symbol": s, "weight": weights[s], "error": str(e)})
            print(f"  ✗ {s}: {e}", file=sys.stderr)
    port = scan_portfolio(weights)
    return {"source": src, "n": len(syms), "holdings": holdings, "portfolio": port}


# --------------------------------------------------------------------------
# 展示：文本 + HTML
# --------------------------------------------------------------------------
def render_text(d):
    L = ["=" * 70, f"组合全景体检 · {d['source']} · {d['n']} 只", "=" * 70]
    p = d["portfolio"]
    if p.get("factor"):
        f = p["factor"]
        L.append(f"  因子: 有效独立因子 {f['n_eff']:.2f}/{f['n']} · PC1 {f['pc1_pct']:.1f}% · {f['verdict']}")
    if p.get("macro"):
        L.append(f"  宏观: {p['macro']['icon']} {p['macro']['regime']}（{p['macro']['quadrant']}）")
    if p.get("market_sentiment"):
        ms = " · ".join(f"{k} {v['score']}({v['label'][:2]})" for k, v in p["market_sentiment"].items())
        L.append(f"  市场情绪: {ms}")
    L.append("\n  逐持仓五面:")
    for h in sorted(d["holdings"], key=lambda x: -x.get("weight", 0)):
        if h.get("error"):
            L.append(f"    {h['symbol']:<9} {h['weight']}%  ✗ {h['error'][:40]}")
            continue
        senti = h["senti"]["label"][:4] if h.get("senti") else "—"
        line = f"    {(h.get('name') or h['symbol'])[:8]:<9}{h['weight']:>5}%  技:{h['tech'][:16]:<16} 情:{senti}"
        if h.get("main_flow"):
            line += f" 资:{h['main_flow'][:14]}"
        elif h.get("consensus"):
            c = h["consensus"]
            line += f" 预期:{c.get('stance') or '—'}/{c.get('revision') or '—'}"
        L.append(line)
    L.append("\n  ⚠️ 全景体检为多工具聚合、五面皆叠加层；不构成投资建议，投前逐只核实。")
    return "\n".join(L)


def render_html(d):
    import html as _h
    rows = ""
    for h in sorted(d["holdings"], key=lambda x: -x.get("weight", 0)):
        if h.get("error"):
            rows += f'<tr><td>{_h.escape(h["symbol"])}</td><td>{h["weight"]}%</td><td colspan="4" class="err">✗ {_h.escape(h["error"][:60])}</td></tr>'
            continue
        senti = h.get("senti") or {}
        extra = h.get("main_flow") or (f"预期 {h.get('consensus',{}).get('stance','—')}/{h.get('consensus',{}).get('revision','—')}" if h.get("consensus") else "—")
        rows += (f'<tr><td class="sym">{_h.escape(h.get("name") or h["symbol"])}<br><span class="mini">{_h.escape(h["symbol"])} · {h["weight"]}%</span></td>'
                 f'<td>{_h.escape(h.get("tech","—"))}<br><span class="mini">RS {h.get("rs_pct")}%</span></td>'
                 f'<td>{_h.escape(h.get("flow","—"))}<br><span class="mini">{_h.escape(h.get("divergence",""))}</span></td>'
                 f'<td>{senti.get("score","—")} {_h.escape(senti.get("label","—"))}</td>'
                 f'<td>{_h.escape(str(extra))}</td></tr>')
    p = d["portfolio"]
    f = p.get("factor") or {}
    macro = p.get("macro") or {}
    ms = " · ".join(f"{k} {v['score']} {v['label']}" for k, v in (p.get("market_sentiment") or {}).items())
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>组合全景体检</title><style>
:root{{--bg:#f6f8fb;--card:#fff;--ink:#152030;--muted:#5b6472;--line:#e4e8ef;--head:#0b2942;--accent:#0e7490;--red:#dc2626;}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0e1116;--card:#161b22;--ink:#e6edf3;--muted:#9aa5b1;--line:#2a3139;--head:#cfe8f5;--accent:#22b8cf;--red:#f87171;}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}}
.wrap{{max-width:1000px;margin:0 auto;padding:26px 18px 60px}}h1{{color:var(--head);font-size:1.4rem}}
.sub{{color:var(--muted);font-size:.85rem}}.kpi{{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;flex:1;min-width:180px}}
.box .l{{font-size:.76rem;color:var(--muted)}}.box .v{{font-size:1.05rem;font-weight:700;color:var(--head)}}
table{{border-collapse:collapse;width:100%;font-size:.82rem;margin-top:8px}}
th,td{{padding:7px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{background:var(--head);color:#fff}}.sym{{font-weight:700;color:var(--head);white-space:nowrap}}
.mini{{font-size:.72rem;color:var(--muted)}}.err{{color:var(--red)}}.scroll{{overflow-x:auto}}
.warn{{background:#fee2e2;border-radius:10px;padding:12px 16px;margin-top:16px;font-size:.85rem;color:#7f1d1d}}
@media(prefers-color-scheme:dark){{.warn{{background:#3a1414;color:#fca5a5}}}}</style></head><body><div class="wrap">
<h1>组合全景体检</h1><div class="sub">{_h.escape(d['source'])} · {d['n']} 只 · 五面 × 持仓 + 组合层(因子/风险/情绪/宏观) · 一键聚合</div>
<div class="kpi">
<div class="box"><div class="l">有效独立因子 / 名义</div><div class="v">{f.get('n_eff','—') if not isinstance(f.get('n_eff'),float) else round(f['n_eff'],2)} / {f.get('n','—')}</div></div>
<div class="box"><div class="l">PC1 主导度</div><div class="v">{round(f['pc1_pct'],1) if f.get('pc1_pct') is not None else '—'}%</div></div>
<div class="box"><div class="l">宏观 regime</div><div class="v">{macro.get('icon','')} {macro.get('regime','—')}</div></div>
<div class="box"><div class="l">市场情绪</div><div class="v" style="font-size:.85rem">{_h.escape(ms) or '—'}</div></div>
</div>
<div class="scroll"><table><thead><tr><th>持仓(权重)</th><th>技术面</th><th>资金面</th><th>情绪面</th><th>主力/预期</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<div class="warn">⚠️ 全景体检为 datalayer/technicals/moneyflow/sentiment/factor_model/portfolio_risk/macro_regime 多工具一键聚合；五面皆叠加层、永不替代基本面；不构成投资建议，投前逐只核实。{f.get('verdict','')}</div>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="组合全景体检编排器（一键五面+组合+因子+宏观，零依赖）")
    ap.add_argument("--from-ledger", help="交易账本 CSV")
    ap.add_argument("--symbols", help='符号列表 "AAPL,600519,0700.HK"')
    ap.add_argument("--weights", help='如 "AAPL=30,..."；缺省等权')
    ap.add_argument("--fx", default="USD=1,HKD=0.128,CNY=0.14", help="账本市值换算(--from-ledger)")
    ap.add_argument("--deep", action="store_true", help="加公告催化剂(A)/一致预期(US)，较慢")
    ap.add_argument("--html", help="导出 HTML 报告到指定路径")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    d = run(args)
    if args.html:
        os.makedirs(os.path.dirname(args.html) or ".", exist_ok=True)
        with open(args.html, "w", encoding="utf-8") as f:
            f.write(render_html(d))
        print(f"[scan] HTML 已导出 → {args.html}", file=sys.stderr)
    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_text(d))


if __name__ == "__main__":
    main()
