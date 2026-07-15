#!/usr/bin/env python3
"""定期复盘编排器（零外部依赖，仅 stdlib）。P3 运营节奏"心跳"。

三层五面全面诊断，供人工校验与确认是否更新组合/观察名单：
  ① 市场层五面：宏观 regime(基本面) · 大盘指数趋势(技术面) · 涨跌停广度/北向(资金面) ·
     三市场恐惧贪婪+VIX(情绪面) · 财报季/重大事项密度(消息面) → 市场结论(是否调整敞口)。
  ② 组合层：风险/因子/集中度 + 组合五面倾斜。
  ③ 逐标的五面：每只持仓 + 每个 watchlist 标的，摘出基本/技术/资金/情绪/消息 + 综合告警。
最后给「组合 & Watchlist 更新建议」（自动汇总，须人工拍板）。

纯 Python、可挂 cron（见 scripts/install-review-cron.sh）。节奏 --daily/--weekly/--quarterly。

用法：
  python3 tools/review.py --from-ledger data/portfolio/transactions.csv --weekly [--html]
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portfolio_scan as psc  # noqa: E402
import watchlist as wl  # noqa: E402
import catalysts as cal  # noqa: E402
import technicals as ta  # noqa: E402
import sentiment as st  # noqa: E402
import macro_regime as mac  # noqa: E402
import news_engine as ne  # noqa: E402
import radar as rad  # noqa: E402
import quant_metrics as qm  # noqa: E402
import horizon_compare as hcmp  # noqa: E402
import pipeline as pl  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MKT_CN = {"A": "A股", "US": "美股", "HK": "港股"}


def _today():
    return datetime.now().strftime("%Y-%m-%d")


# ==========================================================================
# 纯逻辑：告警 / 行动 / 建议
# ==========================================================================
def holding_flags(h):
    """由五面信号产出告警 [(级别, 说明)]。纯函数。"""
    flags = []
    tech = h.get("tech", "") or ""
    if any(k in tech for k in ("空头排列", "偏空", "下降", "深跌", "趋势未明")):
        flags.append(("🔴", f"技术转弱/无趋势：{tech}"))
    mf = h.get("main_flow", "") or ""
    if ("派发" in mf) or ("净流出" in mf):
        flags.append(("🔴", "主力资金派发/净流出"))
    if (h.get("consensus") or {}).get("revision") == "下修":
        flags.append(("🔴", "盈利预期下修"))
    senti = (h.get("senti") or {}).get("score")
    if senti is not None:
        if senti >= 75:
            flags.append(("🟡", f"情绪极度贪婪({senti})——警惕追高"))
        elif senti <= 25:
            flags.append(("🟢", f"情绪极度恐惧({senti})——留意机会"))
    return flags


def reversal_signal(h):
    """watchlist 退出标的的反转迹象：极度恐惧 + 主力吸筹/净流入。纯函数。"""
    senti = (h.get("senti") or {}).get("score")
    mf = h.get("main_flow", "") or ""
    tech = h.get("tech", "") or ""
    fear = senti is not None and senti <= 30
    accum = ("净流入" in mf) or ("吸筹" in mf)
    # 趋势转多须看"趋势"(上升/偏多)，而非"MACD多头"(短期动量)；仍偏空/深跌则未企稳
    trend_up = ("上升趋势" in tech or "偏多" in tech) and not any(
        k in tech for k in ("偏空", "空头排列", "深跌", "趋势未明"))
    if fear and accum and not trend_up:
        return "🟢 反转候选：极度恐惧+主力吸筹，但趋势未企稳——待趋势转多再评估"
    if fear and accum and trend_up:
        return "🟢🟢 反转确认：恐惧+吸筹+趋势转多——可评估小仓再入(设止损)"
    return None


def build_actions(holdings, watch_extras, due, imminent, market_verdict):
    """汇总行动清单。纯函数。"""
    acts = []
    if market_verdict.get("caution"):
        acts.append(f"🌡️ 市场：{market_verdict['caution']}")
    for e in due:
        acts.append(f"📋 复审到期：{e['symbol']} {e.get('name') or ''}（{e.get('review_date')}）")
    for ev in imminent:
        acts.append(f"🔔 临近催化剂：{ev['date']} {ev['symbol']} {ev.get('detail', '')}")
    for h in holdings:
        reds = [msg for lv, msg in holding_flags(h) if lv == "🔴"]
        if reds:
            acts.append(f"⚠️ 红线关注：{h['symbol']} {h.get('name') or ''} — {'; '.join(reds)}")
    for h in watch_extras:
        rs = reversal_signal(h)
        if rs:
            acts.append(f"🔍 观察反转：{h['symbol']} {h.get('name') or ''} — {rs}")
    return acts


def market_verdict_of(mkt):
    """由市场五面合成结论。纯函数（输入已抓好的 dict）。"""
    senti = mkt.get("sentiment", {})
    scores = [v["score"] for v in senti.values() if v.get("score") is not None]
    greedy = [k for k, v in senti.items() if (v.get("score") or 0) >= 70]
    regime = (mkt.get("macro") or {}).get("regime")
    bits = []
    caution = None
    if regime:
        fav = {"复苏": "利好股票、顺周期成长可积极", "过热": "商品/周期占优、股票转谨慎、缩久期",
               "滞胀": "防御/现金、避高估值", "衰退": "债券/防御、等政策转向"}.get(regime, "")
        bits.append(f"宏观{regime}({fav})")
    if len(greedy) >= 2 or (scores and max(scores) >= 75):
        caution = "情绪偏热→保持现金缓冲、不追高、审视最贵持仓"
        bits.append("多市场贪婪(反向警惕)")
    b = mkt.get("breadth")
    if b and b.get("score") is not None and b["score"] <= 30:
        bits.append(f"A股广度弱(涨停{b['limit_up']}/跌停{b['limit_down']}，内部分化)")
        caution = (caution or "") + " 回避高位小盘、看广度是否恶化"
    nw = mkt.get("news") or {}
    if nw.get("policy_count"):
        bits.append(f"政策要闻{nw['policy_count']}条")
    tone = nw.get("cn_tone")
    if tone is not None and tone <= -0.25:
        bits.append(f"要闻情绪偏负({tone})")
        caution = (caution or "") + " 留意政策/宏观利空发酵"
    return {"summary": " · ".join(bits) or "市场信号中性", "caution": (caution or "").strip()}


# ==========================================================================
# 采集：市场层五面 + 逐标的五面
# ==========================================================================
def market_five_faces(bench_cache, markets):
    out = {"markets": markets}
    try:
        out["macro"] = mac.now()
    except Exception:  # noqa: BLE001
        out["macro"] = None
    out["index_tech"] = {}
    for m in markets:
        b = bench_cache.get(m)
        if b:
            try:
                out["index_tech"][m] = ta.compute(b)["posture"]["one_line"]
            except Exception:  # noqa: BLE001
                pass
    out["sentiment"] = {}
    for m in markets:
        try:
            d = st.market_sentiment(m)
            out["sentiment"][m] = {"score": d["score"], "label": d["label"], "raw": d.get("raw", {})}
        except Exception:  # noqa: BLE001
            pass
    if "A" in markets:
        try:
            out["breadth"] = st.fetch_breadth()
        except Exception:  # noqa: BLE001
            out["breadth"] = None
    try:
        out["news"] = ne.fetch_market_news(limit=7)     # 市场消息面：宏观/政策要闻 + 美股
    except Exception:  # noqa: BLE001
        out["news"] = None
    out["verdict"] = market_verdict_of(out)
    return out


def augment_fundamental(h):
    """补基本面(五面之一)：US 用 scan 的 consensus；A 用东财一致预期；HK 暂无。"""
    c = h.get("consensus")
    if c:  # US 已由 scan --deep 提供
        h["fundamental"] = f"评级{c.get('stance') or '—'}·{c.get('revision') or '—'}·PEG{c.get('peg') or '—'}"
        return
    if h.get("market") == "A":
        try:
            import consensus as cs
            cc = cs.fetch_consensus(h["symbol"])
            h["fundamental"] = (f"{cc['stance']}({cc['org_num']}家)·EPS CAGR{cc.get('eps_cagr_pct')}%"
                                f"·PEG{cc.get('peg') or '—'}")
        except Exception:  # noqa: BLE001
            h["fundamental"] = "—"
    else:
        h["fundamental"] = "—(未盈利/无覆盖)"


def us_next_earnings(symbols):
    m = {}
    for s in symbols:
        try:
            ev = cal.fetch_earnings(s)
            if ev:
                m[s] = ev[0]
        except Exception:  # noqa: BLE001
            pass
    return m


# ==========================================================================
# 主流程
# ==========================================================================
def run(args):
    cadence = "quarterly" if args.quarterly else ("daily" if args.daily else "weekly")
    horizon = {"daily": 7, "weekly": 21, "quarterly": 90}[cadence]

    sargs = argparse.Namespace(from_ledger=args.from_ledger, symbols=None, weights=None, fx=args.fx)
    weights, src = psc.load_portfolio(sargs)
    port_syms = list(weights)

    bench_cache = {}
    for m, b in psc.BENCH.items():
        try:
            bench_cache[m] = psc.dl.fetch_ohlcv(b, freq="daily", period="2y")["bars"]
        except Exception:  # noqa: BLE001
            bench_cache[m] = None
    markets = sorted({psc.dl.detect(s)["market"] for s in port_syms})

    # ① 市场层
    market = market_five_faces(bench_cache, markets)

    # ③ 逐持仓五面
    deep = cadence != "daily"
    holdings = []
    for s in port_syms:
        try:
            h = psc.scan_holding(s, bench_cache, deep=deep)
            h["weight"] = weights[s]
            augment_fundamental(h)
            holdings.append(h)
        except Exception as e:  # noqa: BLE001
            holdings.append({"symbol": s, "weight": weights[s], "error": str(e)})

    # ② 组合层
    port = psc.scan_portfolio(weights)

    # 量化五指标(Alpha/Beta/夏普/最大回撤/信息比率) vs 基准 SPY
    metrics = None
    try:
        metrics = qm.evaluate_from_datalayer(weights, "SPY", period="2y", freq="weekly", rf=0.04)
        metrics["rf"] = 0.04
    except Exception:  # noqa: BLE001
        metrics = None

    # 多周期收益对比表(1/3/5/10/15/20年 × 美/A/港指数)——仅周/季(取数较重,日频跳过)
    # 注意:不用 `horizon` 名(与催化剂时间窗 int 冲突)
    hz_tbl = None
    if cadence != "daily":
        try:
            hz_tbl = hcmp.build(weights, ["QQQ", "SPY", "sh000300", "2800.HK"], rf=0.04)
        except Exception:  # noqa: BLE001
            hz_tbl = None

    # watchlist 诊断（非持仓标的：候选/退出——是否反转/再入）
    entries = wl.load()["entries"]
    thesis = {e["symbol"].upper(): e for e in entries}
    extra_syms = [e["symbol"] for e in entries if e["symbol"] not in weights
                  and e["state"] not in ("archived",)]
    watch_extras = []
    for s in extra_syms:
        try:
            h = psc.scan_holding(s, bench_cache, deep=deep)
            h["state"] = thesis.get(s.upper(), {}).get("state")
            augment_fundamental(h)
            watch_extras.append(h)
        except Exception as e:  # noqa: BLE001
            watch_extras.append({"symbol": s, "error": str(e), "state": thesis.get(s.upper(), {}).get("state")})

    # 到期复审 + 催化剂
    due = [e for e in entries if wl.is_due(e.get("review_date"), _today())
           and e["state"] not in ("exiting", "archived")]
    ev = []
    us_syms = [h["symbol"] for h in holdings if h.get("market") == "US"]
    us_earn = us_next_earnings(us_syms)
    ev += list(us_earn.values())
    try:
        ev += cal.from_watchlist_catalysts()
    except Exception:  # noqa: BLE001
        pass
    timeline = cal.build_timeline(ev, horizon, _today())
    imminent = [e for e in timeline if e.get("imminent")]

    # 市场机会雷达（持仓/watchlist 之外的新线索；仅周/季，日频跳过以省时）
    radar_out = None
    if cadence != "daily":
        try:
            ex = list(weights) + [e["symbol"] for e in entries]
            radar_out = {"candidates": rad.candidates(ex, 10), "sectors": rad.hot_sectors()}
        except Exception:  # noqa: BLE001
            radar_out = None

    # 三级流水线：雷达线索(A股龙虎榜 + 美股13F + 港股南向)自动落入 T1 + 三层回顾
    # 复用 pipeline 的统一 lead 函数(与 capture-radar 一致，避免重复捕获/口径不一)
    tiers = None
    if cadence != "daily":
        try:
            for market, fn in (("A", pl._a_leads), ("US", pl.us_leads), ("HK", pl.hk_leads)):
                try:
                    for c in fn():
                        pl.pool_add(c["symbol"], c.get("name", ""), market,
                                    f"雷达-{c.get('signal', '')}", c.get("reason", ""),
                                    c.get("strength", 1))
                except Exception:  # noqa: BLE001
                    pass
            tiers = pl.tier_view(pl.pool_load(), wl.load()["entries"], set(weights))
        except Exception:  # noqa: BLE001
            tiers = None

    actions = build_actions([h for h in holdings if not h.get("error")], watch_extras, due, imminent, market["verdict"])
    updates = synthesize_updates(holdings, watch_extras, port, market, radar_out)
    return {"cadence": cadence, "date": _today(), "source": src, "market": market,
            "port": port, "metrics": metrics, "horizon": hz_tbl, "tiers": tiers, "holdings": holdings,
            "watch_extras": watch_extras, "due": due, "timeline": timeline, "imminent": imminent,
            "radar": radar_out, "actions": actions, "updates": updates, "thesis": thesis, "us_earn": us_earn}


def synthesize_updates(holdings, watch_extras, port, market, radar_out=None):
    """组合 & watchlist 更新建议（自动汇总，须人工拍板）。"""
    ups = []
    if market["verdict"].get("caution"):
        ups.append(f"敞口：{market['verdict']['caution']}")
    for h in holdings:
        if h.get("error"):
            continue
        reds = [msg for lv, msg in holding_flags(h) if lv == "🔴"]
        if reds:
            ups.append(f"减仓候选：{h['symbol']} {h.get('name') or ''}（{'; '.join(reds)}）→ 按卖出纪律评估")
    for h in watch_extras:
        rs = reversal_signal(h)
        if rs:
            ups.append(f"再入候选：{h['symbol']} {h.get('name') or ''} → {rs}")
    f = port.get("factor") or {}
    if f.get("pc1_pct", 0) >= 40:
        ups.append(f"集中度：PC1 {f['pc1_pct']:.0f}% 偏高，避免再加与核心高相关的持仓")
    if radar_out and radar_out.get("candidates", {}).get("candidates"):
        insts = [c for c in radar_out["candidates"]["candidates"] if c["strength"] >= 3][:4]
        if insts:
            names = "、".join(f"{c['name']}({c['code']})" for c in insts)
            ups.append(f"新标的线索：机构龙虎榜买入 {names} → 对感兴趣者跑 /investment-research 基本面研究再定是否纳入观察（非买入信号）")
    if not ups:
        ups.append("维持当前组合与观察名单，按红线/催化剂被动响应，不主动追高")
    return ups


# ==========================================================================
# 展示
# ==========================================================================
def _faces_lines(h, us_earn, thesis):
    L = []
    L.append(f"    基本面 {h.get('fundamental', '—')}")
    # 技术面：姿态 + RS + 距52周高 + RSI + 量比
    det = []
    if h.get("rs_pct") is not None:
        det.append(f"RS{h['rs_pct']:+.0f}%")
    if h.get("from_high") is not None:
        det.append(f"距高{h['from_high']:+.0f}%")
    if h.get("rsi14") is not None:
        det.append(f"RSI{h['rsi14']:.0f}")
    if h.get("vol_ratio") is not None:
        det.append(f"量比{h['vol_ratio']:.1f}")
    L.append(f"    技术面 {h.get('tech', '—')}" + (f"（{' · '.join(det)}）" if det else ""))
    # 资金面：A/H 主力近5/20日 + 价量代理/背离；US CMF
    if h.get("main_flow"):
        extra = ""
        if h.get("main_5d_yi") is not None:
            extra = f"（近5日 {h['main_5d_yi']:+.1f}亿 / 20日 {h.get('main_20d_yi', 0):+.1f}亿）"
        L.append(f"    资金面 {h['main_flow']}{extra}")
    else:
        cmf = f"（CMF {h['cmf']:+.2f}）" if h.get("cmf") is not None else ""
        L.append(f"    资金面 {h.get('flow', '—')}{cmf} · {h.get('divergence', '')}")
    s = h.get("senti") or {}
    L.append(f"    情绪面 {s.get('label', '—')}({s.get('score', '—')})")
    # 消息面
    if h.get("news"):
        n = h["news"]
        tags = "、".join(f"{k}×{v}" for k, v in (n.get("top") or [])[:2])
        news = f"重大{n.get('material', 0)}条·{tags}" if tags else f"重大{n.get('material', 0)}条"
    elif h["symbol"] in us_earn:
        e = us_earn[h["symbol"]]
        news = f"下次财报 {e['date']}（{e.get('detail', '')[:20]}）"
    else:
        news = "—"
    L.append(f"    消息面 {news}")
    return L


def render_text(r):
    m, p = r["market"], r["port"]
    L = ["=" * 72,
         f"投资组合定期复盘（三层五面）· {r['cadence'].upper()} · {r['date']} · {r['source']}",
         "=" * 72]

    # 执行摘要
    L.append("\n【执行摘要】")
    L.append(f"  市场：{m['verdict']['summary']}")
    f = p.get("factor") or {}
    L.append(f"  组合：{len([h for h in r['holdings'] if not h.get('error')])} 只 · 有效因子 "
             f"{f.get('n_eff', 0):.1f}/{f.get('n', 0)} · PC1 {f.get('pc1_pct', 0):.0f}%")

    # 行动清单
    L.append("\n【行动清单】")
    for a in r["actions"]:
        L.append(f"  {a}")
    if not r["actions"]:
        L.append("  ✅ 无紧急事项")

    # ① 市场五面
    L.append("\n" + "─" * 72 + "\n【一、市场五面摘要】（→ 是否调整敞口）")
    mac_d = m.get("macro") or {}
    if mac_d:
        pm = mac_d.get("pmi") or {}
        cp = mac_d.get("cpi") or {}
        m2 = mac_d.get("m2") or {}
        L.append(f"  基本面(宏观): {mac_d.get('icon', '')}{mac_d.get('regime', '—')}"
                 f"（PMI {pm.get('make', '—')} · CPI {cp.get('yoy', '—')}% · M2 {m2.get('m2_yoy', '—')}% · 10Y {mac_d.get('y10y', '—')}%）")
    it = m.get("index_tech", {})
    L.append("  技术面(大盘): " + " · ".join(f"{MKT_CN.get(k, k)} {v}" for k, v in it.items()) if it else "  技术面(大盘): —")
    b = m.get("breadth")
    if b:
        L.append(f"  资金面(市场): A股涨停 {b['limit_up']}/跌停 {b['limit_down']}（{b['label']}） · 北向:2024-08起停披露")
    else:
        L.append("  资金面(市场): —")
    se = m.get("sentiment", {})
    L.append("  情绪面(市场): " + " · ".join(f"{MKT_CN.get(k, k)} {v['score']}({v['label'][:4]})" for k, v in se.items()))
    nw = m.get("news") or {}
    ncat = len(r["imminent"])
    tone = nw.get("cn_tone")
    L.append(f"  消息面(市场): 政策要闻 {nw.get('policy_count', 0)} 条 · 要闻情绪 {tone if tone is not None else '—'} · 未来窗口 {ncat} 项催化剂")
    for c in [x for x in nw.get("cn", []) if x.get("is_policy")][:3]:
        dot = {"利好": "🟢", "利空": "🔴", "中性": "⚪"}[c["direction"]]
        L.append(f"      🏛️{dot} {c['text'][:52]}")
    for x in nw.get("us", [])[:2]:
        L.append(f"      🌐 [{x['source']}] {x['headline'][:52]}")
    L.append(f"  ▶ 市场结论: {m['verdict']['summary']}"
             + (f"；{m['verdict']['caution']}" if m['verdict'].get('caution') else ""))

    # ② 组合层
    L.append("\n" + "─" * 72 + "\n【二、组合层】")
    if f:
        L.append(f"  风险/因子: 有效独立因子 {f.get('n_eff', 0):.2f}/{f.get('n', 0)} · PC1 {f.get('pc1_pct', 0):.1f}% · {f.get('verdict', '')}")
        L.append(f"  因子倾斜: 动量 {f.get('port_momentum_z', 0):+.2f} · 波动 {f.get('port_vol_z', 0):+.2f}")
    m = r.get("metrics")
    if m:
        v = m["verdicts"]
        def _f(x, pct=False):
            return "—" if x is None else (f"{x:+.1%}" if pct else f"{x:+.2f}")
        L.append(f"  量化五指标(vs {m['benchmark']} · {m['n_periods']}期):")
        L.append(f"    β {_f(m['beta'])} {v['beta']}  ·  α年化 {_f(m['alpha_annual'], True)} {v['alpha']}")
        L.append(f"    夏普 {_f(m['sharpe'])} {v['sharpe']}  ·  最大回撤 {_f(m['max_drawdown'], True)} {v['max_drawdown']}")
        L.append(f"    信息比率 {_f(m['information_ratio'])} {v['information_ratio']}")

    t = r.get("tiers")
    if t:
        L.append("  三级流水线: "
                 f"T3持仓{len(t['T3'])} · T2观察{len(t['T2'])} · T1候选{len(t['T1'])}"
                 + (f" · ⚠️{len(t['issues'])}处一致性待查" if t["issues"] else ""))

    # ③ 逐持仓五面
    L.append("\n" + "─" * 72 + "\n【三、逐持仓五面诊断】")
    for h in sorted([x for x in r["holdings"] if not x.get("error")], key=lambda x: -x.get("weight", 0)):
        flags = holding_flags(h)
        tag = "  ".join(f"{lv}{msg}" for lv, msg in flags) if flags else "✓ 正常"
        L.append(f"\n  ● {(h.get('name') or h['symbol'])} [{h['symbol']} · 持有{h.get('weight', 0):.0f}%]  ▶ {tag}")
        L += _faces_lines(h, r["us_earn"], r["thesis"])
        th = r["thesis"].get(h["symbol"].upper())
        if th and th.get("red_lines") and any(lv == "🔴" for lv, _ in flags):
            L.append(f"    ↳ 红线: {th['red_lines']}")

    # ④ watchlist 诊断
    if r["watch_extras"]:
        L.append("\n" + "─" * 72 + "\n【四、Watchlist 诊断（非持仓/观察）】")
        for h in r["watch_extras"]:
            state = h.get("state", "?")
            if h.get("error"):
                L.append(f"\n  ● {h['symbol']} [{state}]  取数失败: {h['error'][:40]}")
                continue
            rs = reversal_signal(h)
            L.append(f"\n  ● {(h.get('name') or h['symbol'])} [{h['symbol']} · {wl.STATE_CN.get(state, state)}]"
                     + (f"  ▶ {rs}" if rs else ""))
            L += _faces_lines(h, r["us_earn"], r["thesis"])

    # ⑤ 到期/催化剂
    L.append("\n" + "─" * 72 + f"\n【五、到期复审】{len(r['due'])} 只 · 【临近催化剂】{len(r['imminent'])} 项")
    for e in r["due"]:
        L.append(f"  📋 {e['symbol']} {e.get('name') or ''} · 复审日 {e.get('review_date')}")
    for ev in r["imminent"]:
        L.append(f"  🔔 {ev['date']} {ev['symbol']} {ev.get('detail', '')}")

    # ⑦ 市场机会雷达（持仓/watchlist 之外）
    rd = r.get("radar")
    if rd:
        L.append("\n" + "─" * 72 + "\n【六、市场机会雷达（持仓/watchlist 之外的新线索）】")
        hs = rd.get("sectors", {}).get("sectors", [])
        if hs:
            L.append("  热门板块(涨停聚合): " + " · ".join(f"{s['sector']}({s['limit_up_count']})" for s in hs))
        cands = rd.get("candidates", {}).get("candidates", [])
        if cands:
            L.append("  新标的候选线索（须基本面研究后方可纳入观察，非买入信号）:")
            for c in cands[:8]:
                ch = f"{c['change']:+.1f}%" if isinstance(c["change"], (int, float)) else "—"
                L.append(f"    {c['signal']} {c['name']}({c['code']}) {ch} · {c['detail']}")
        else:
            L.append("  （无新线索）")

    # ⑥ 更新建议
    L.append("\n" + "─" * 72 + "\n【七、组合 & Watchlist 更新建议（须人工确认）】")
    for u in r["updates"]:
        L.append(f"  • {u}")
    if r["cadence"] == "quarterly":
        L.append("  • 季度：跑 performance/attribution 归因 + Brier 校准；复审 IPS(基准/风险预算/禁投)")

    L.append("\n  ⚠️ 复盘为工具信号聚合、非投资建议；红线/建议是提示、须人工拍板；五面皆叠加层不替代基本面。")
    return "\n".join(L)


def _metrics_html(m):
    """量化五指标 HTML 卡片。"""
    if not m:
        return ""
    v = m["verdicts"]
    def _f(x, pct=False):
        return "—" if x is None else (f"{x:+.1%}" if pct else f"{x:+.2f}")
    cells = [
        ("Beta β", _f(m["beta"]), v["beta"]),
        ("Alpha 年化", _f(m["alpha_annual"], True), v["alpha"]),
        ("夏普比率", _f(m["sharpe"]), v["sharpe"]),
        ("最大回撤", _f(m["max_drawdown"], True), v["max_drawdown"]),
        ("信息比率 IR", _f(m["information_ratio"]), v["information_ratio"]),
    ]
    rows = "".join(
        f'<tr><td>{name}</td><td style="text-align:right;font-weight:700">{val}</td>'
        f'<td style="color:#9aa5b1">{verd}</td></tr>' for name, val, verd in cells)
    return (f'<div class="card">量化五指标 · vs {m["benchmark"]} · {m["n_periods"]}期'
            f'<table style="width:100%;border-collapse:collapse;margin-top:6px;font-size:13px">{rows}</table></div>')


def _horizon_html(hz):
    """多周期收益对比表 HTML(三张表:组合表现 / 年化vs指数 / 回撤vs指数)。"""
    if not hz:
        return ""
    def _p(x):
        return "—" if x is None else f"{x:+.1%}"
    def _n(x):
        return "—" if x is None else f"{x:.2f}"
    bl = hz["benchmarks"]
    from horizon_compare import BENCH_CN as _BCN, _NAME as _HNM
    def _drp(row):
        return "、".join(_HNM.get(s, s) for s in row.get("dropped", [])) or "—"
    # 表1:组合多周期(含"剔除"列)
    r1 = "".join(
        (f'<tr><td>{row["years"]}年</td><td colspan="8" style="color:var(--muted)">— 数据不足</td><td>{_drp(row)}</td></tr>'
         if not row["port"] else
         f'<tr><td>{row["years"]}年</td><td>{_p(row["port"]["total_return"])}</td>'
         f'<td>${int(row["port"]["final_balance"]):,}</td><td>{_p(row["port"]["cagr"])}</td>'
         f'<td>{_p(row["port"]["max_drawdown"])}</td><td>{_n(row["port"]["sharpe"])}</td>'
         f'<td>{_p(row.get("alpha"))}</td><td>{_n(row.get("beta"))}</td><td>{_n(row.get("ir"))}</td>'
         f'<td style="color:var(--muted)">{_drp(row)}</td></tr>')
        for row in hz["rows"])
    # 表2/3:年化 / 回撤 vs 指数
    def cmp_rows(key):
        out = []
        for row in hz["rows"]:
            pc = _p(row["port"][key]) if row["port"] else "—"
            cells = "".join(f'<td>{_p(row["bench"][b][key]) if row["bench"].get(b) else "—"}</td>' for b in bl)
            out.append(f'<tr><td>{row["years"]}年</td><td><b>{pc}</b></td>{cells}</tr>')
        return "".join(out)
    bh = "".join(f"<th>{_BCN.get(b, b)}</th>" for b in bl)
    return (
        f'<h2>八、多周期收益对比表（初始资金 $10,000）</h2>'
        f'<div class="card" style="font-size:.82rem;color:var(--muted)">月度对齐 · ⚠️ 长周期若持仓当时未上市'
        f'(如兆易2016)则权重设0、其余重新归一(见"剔除"列)，故长周期是"当时子集"表现非完整 v10；'
        f'用今日持仓回测历史有时代错置/幸存者偏差，是"历史画像"非当年真实收益。</div>'
        f'<div style="overflow-x:auto"><table><tr><th>周期</th><th>总回报</th><th>最终余额</th><th>年化</th>'
        f'<th>最大回撤</th><th>Sharpe</th><th>Alpha</th><th>Beta</th><th>IR</th><th>剔除</th></tr>{r1}</table></div>'
        f'<div style="margin-top:10px;font-size:.9rem;font-weight:600">年化收益 vs 主要指数</div>'
        f'<div style="overflow-x:auto"><table><tr><th>周期</th><th>组合</th>{bh}</tr>{cmp_rows("cagr")}</table></div>'
        f'<div style="margin-top:10px;font-size:.9rem;font-weight:600">最大回撤 vs 主要指数</div>'
        f'<div style="overflow-x:auto"><table><tr><th>周期</th><th>组合</th>{bh}</tr>{cmp_rows("max_drawdown")}</table></div>')


def _tiers_html(t):
    """三级流水线回顾 HTML。"""
    if not t:
        return ""
    def row(label, syms, color):
        chips = "".join(f'<span style="display:inline-block;background:{color};border-radius:10px;'
                        f'padding:1px 8px;margin:2px;font-size:.8rem">{s}</span>' for s in syms) or "—"
        return f'<div style="margin:4px 0"><b>{label}</b>（{len(syms)}）：{chips}</div>'
    issues = ""
    if t["issues"]:
        issues = '<div style="color:#b45309;font-size:.82rem;margin-top:6px">⚠️ 一致性：' + \
                 "；".join(_h_escape(i) for i in t["issues"]) + "</div>"
    recs = t.get("T1_recs", [])
    t1_tbl = ""
    if recs:
        rows = []
        for mk, cn in (("A", "A股·龙虎榜"), ("US", "美股·13F新建"), ("HK", "港股·南向净买")):
            items = [r for r in recs if r.get("market") == mk]
            for i, r in enumerate(items[:6]):
                st = "★" * min(int(r.get("strength", 1)), 5)
                mkcell = f'<td rowspan="{min(len(items),6)}">{cn}</td>' if i == 0 else ""
                rows.append(f'<tr>{mkcell}<td>{st}</td><td>{_h_escape(r["symbol"])}</td>'
                            f'<td>{_h_escape((r.get("name") or "")[:14])}</td>'
                            f'<td style="text-align:left">{_h_escape(r.get("reason", "")[:60])}</td></tr>')
        t1_tbl = ('<div style="overflow-x:auto"><table><tr><th>市场</th><th>印证</th><th>标的</th>'
                  '<th>名称</th><th>提示线索(印证纳入T1的理由)</th></tr>' + "".join(rows) + "</table></div>")
    return (
        '<h2>九、三级机会流水线回顾</h2><div class="card">'
        + row("T3 持仓组合", t["T3"], "rgba(63,185,80,.15)")
        + row("T2 观察名单", t["T2"], "rgba(88,166,255,.15)")
        + f'<div style="margin:4px 0"><b>T1 候选观察</b>（{len(t["T1"])}）——三市场全覆盖·★=印证强度(多源自动升级)：</div>'
        + t1_tbl
        + issues
        + '<div style="font-size:.8rem;color:var(--muted);margin-top:6px">流转：T1→(研究)→T2→(买入)→T3；'
          '降级 T3→T2、T2→T1(级联)。★≥3=多源印证(强)优先研究。A股龙虎榜+美股13F+港股南向自动落入 T1。</div></div>')


def _h_escape(s):
    import html as _h
    return _h.escape(str(s))


def render_html(r):
    import html as _h
    m, p = r["market"], r["port"]
    f = p.get("factor") or {}

    def faces_html(h):
        s = h.get("senti") or {}
        news = "—"
        if h.get("news"):
            n = h["news"]; news = f"重大{n.get('material',0)}条 " + "、".join(f"{k}×{v}" for k, v in (n.get("top") or [])[:2])
        elif h["symbol"] in r["us_earn"]:
            news = f"下次财报 {r['us_earn'][h['symbol']]['date']}"
        rs = f" (RS{h['rs_pct']:+.0f}%)" if h.get("rs_pct") is not None else ""
        return (f'<div class="f"><b>基</b> {_h.escape(str(h.get("fundamental","—")))}</div>'
                f'<div class="f"><b>技</b> {_h.escape(str(h.get("tech","—")))}{rs}</div>'
                f'<div class="f"><b>资</b> {_h.escape(str(h.get("main_flow") or h.get("flow","—")))}</div>'
                f'<div class="f"><b>情</b> {_h.escape(str(s.get("label","—")))}({s.get("score","—")})</div>'
                f'<div class="f"><b>讯</b> {_h.escape(str(news))}</div>')

    def card(h, label):
        flags = holding_flags(h)
        tag = " ".join(f"{lv}{_h.escape(msg)}" for lv, msg in flags) if flags else "✓ 正常"
        rs = reversal_signal(h)
        if rs and not flags:
            tag = _h.escape(rs)
        return (f'<div class="hcard"><div class="ht"><b>{_h.escape(h.get("name") or h["symbol"])}</b>'
                f'<span class="mini">{_h.escape(h["symbol"])} · {label}</span><span class="flag">{tag}</span></div>'
                f'<div class="faces">{faces_html(h)}</div></div>')

    holds = "".join(card(h, f"持有{h.get('weight',0):.0f}%") for h in sorted(
        [x for x in r["holdings"] if not x.get("error")], key=lambda x: -x.get("weight", 0)))
    watch = "".join(card(h, wl.STATE_CN.get(h.get("state", ""), h.get("state", ""))) for h in r["watch_extras"] if not h.get("error"))
    acts = "".join(f"<li>{_h.escape(a)}</li>" for a in r["actions"]) or "<li>✅ 无紧急事项</li>"
    ups = "".join(f"<li>{_h.escape(u)}</li>" for u in r["updates"])
    it = " · ".join(f"{MKT_CN.get(k,k)} {_h.escape(v)}" for k, v in m.get("index_tech", {}).items())
    se = " · ".join(f"{MKT_CN.get(k,k)} {v['score']}({_h.escape(v['label'][:4])})" for k, v in m.get("sentiment", {}).items())
    mac_d = m.get("macro") or {}
    b = m.get("breadth") or {}
    nw = m.get("news") or {}
    news_items = ""
    for c in [x for x in nw.get("cn", []) if x.get("is_policy")][:3]:
        dot = {"利好": "🟢", "利空": "🔴", "中性": "⚪"}[c["direction"]]
        news_items += f'<div class="ni">🏛️{dot} {_h.escape(c["text"][:60])}</div>'
    for x in nw.get("us", [])[:2]:
        news_items += f'<div class="ni">🌐 [{_h.escape(x["source"])}] {_h.escape(x["headline"][:60])}</div>'
    due = "".join(f"<li>📋 {_h.escape(e['symbol'])} {_h.escape(e.get('name') or '')} · {e.get('review_date')}</li>" for e in r["due"]) or "<li>无</li>"
    imm = "".join(f"<li>🔔 {ev['date']} {_h.escape(ev['symbol'])} {_h.escape(ev.get('detail',''))}</li>" for ev in r["imminent"]) or "<li>无</li>"
    rd = r.get("radar") or {}
    hs = (rd.get("sectors") or {}).get("sectors", [])
    cands = (rd.get("candidates") or {}).get("candidates", [])
    sect_html = " · ".join(f"{_h.escape(s['sector'])}({s['limit_up_count']})" for s in hs) or "—"
    cand_html = "".join(
        f'<li>{_h.escape(c["signal"])} <b>{_h.escape(c["name"])}</b>({c["code"]}) '
        f'{("%+.1f%%" % c["change"]) if isinstance(c["change"],(int,float)) else "—"} · {_h.escape(c["detail"])}</li>'
        for c in cands[:8]) or "<li>无新线索</li>"
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>定期复盘 {r['date']}</title><style>
:root{{--bg:#f6f8fb;--card:#fff;--ink:#152030;--muted:#5b6472;--line:#e4e8ef;--head:#0b2942;--accent:#0e7490;--red:#dc2626;--amber:#d98a00;--green:#16a34a;}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0e1116;--card:#161b22;--ink:#e6edf3;--muted:#9aa5b1;--line:#2a3139;--head:#cfe8f5;--accent:#22b8cf;--red:#f87171;--amber:#f5c542;--green:#34d399;}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.55}}
.wrap{{max-width:1000px;margin:0 auto;padding:24px 18px 60px}}h1{{color:var(--head);font-size:1.35rem}}.sub{{color:var(--muted);font-size:.84rem}}
h2{{color:var(--head);font-size:1.08rem;border-left:5px solid var(--accent);padding-left:.5em;margin-top:1.5em}}
.act,.upd{{border-radius:12px;padding:12px 18px}}.act{{background:linear-gradient(90deg,#fef3c7,#fee2e2)}}.upd{{background:linear-gradient(90deg,#dcfce7,#dbeafe)}}
@media(prefers-color-scheme:dark){{.act{{background:linear-gradient(90deg,#33280a,#3a1414)}}.upd{{background:linear-gradient(90deg,#0f2e1e,#0f2038)}}}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:10px 0;font-size:.87rem}}
.hcard{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 13px;margin:8px 0}}
.ht{{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:5px;margin-bottom:6px}}
.ht b{{color:var(--head)}}.mini{{font-size:.72rem;color:var(--muted)}}.flag{{margin-left:auto;font-size:.8rem}}
.faces{{display:grid;grid-template-columns:1fr 1fr;gap:3px 14px}}.f{{font-size:.82rem}}.f b{{color:var(--accent);margin-right:4px}}
@media(max-width:620px){{.faces{{grid-template-columns:1fr}}}}
ul{{margin:.3em 0;padding-left:1.3em}}li{{margin:.25em 0;font-size:.87rem}}
.mrow{{font-size:.86rem;margin:3px 0}}.mrow b{{color:var(--accent);display:inline-block;min-width:6.5em}}
.ni{{font-size:.8rem;color:var(--muted);margin:2px 0 2px 6.5em}}
table{{border-collapse:collapse;width:100%;margin:6px 0;font-size:.82rem}}
th,td{{border:1px solid var(--line);padding:6px 9px;text-align:right;white-space:nowrap}}
th{{background:var(--card);color:var(--head);font-weight:600}}
td:first-child,th:first-child{{text-align:left}}
tr:nth-child(even) td{{background:rgba(127,127,127,.05)}}
footer{{color:var(--muted);font-size:.78rem;margin-top:20px;border-top:1px solid var(--line);padding-top:10px}}</style></head><body><div class="wrap">
<h1>投资组合定期复盘（三层五面）· {r['cadence'].upper()}</h1><div class="sub">{r['date']} · {_h.escape(r['source'])}</div>
<h2>🎯 行动清单</h2><div class="act"><ul>{acts}</ul></div>
<h2>一、市场五面摘要（→ 是否调整敞口）</h2><div class="card">
<div class="mrow"><b>基本面</b>{mac_d.get('icon','')}{_h.escape(mac_d.get('regime','—'))}（PMI {(mac_d.get('pmi') or {}).get('make','—')} · CPI {(mac_d.get('cpi') or {}).get('yoy','—')}% · M2 {(mac_d.get('m2') or {}).get('m2_yoy','—')}% · 10Y {mac_d.get('y10y','—')}%）</div>
<div class="mrow"><b>技术面</b>{it or '—'}</div>
<div class="mrow"><b>资金面</b>A股涨停 {b.get('limit_up','—')}/跌停 {b.get('limit_down','—')}（{_h.escape(b.get('label','—'))}）· 北向2024-08停披露</div>
<div class="mrow"><b>情绪面</b>{se or '—'}</div>
<div class="mrow"><b>消息面</b>政策要闻 {nw.get('policy_count',0)} 条 · 要闻情绪 {nw.get('cn_tone') if nw.get('cn_tone') is not None else '—'} · 未来窗口 {len(r['imminent'])} 项催化剂</div>
{news_items}
<div class="mrow" style="margin-top:6px"><b>▶ 结论</b>{_h.escape(m['verdict']['summary'])}{('；'+_h.escape(m['verdict']['caution'])) if m['verdict'].get('caution') else ''}</div></div>
<h2>二、组合层</h2><div class="card">有效独立因子 <b>{f.get('n_eff',0):.2f}/{f.get('n',0)}</b> · PC1 {f.get('pc1_pct',0):.1f}% · {_h.escape(f.get('verdict',''))}<br>因子倾斜 动量 {f.get('port_momentum_z',0):+.2f} · 波动 {f.get('port_vol_z',0):+.2f}</div>
{_metrics_html(r.get('metrics'))}
<h2>三、逐持仓五面诊断</h2>{holds}
<h2>四、Watchlist 诊断（非持仓/观察）</h2>{watch or '<div class="card">无</div>'}
<h2>五、到期复审 / 临近催化剂</h2><div class="card"><ul>{due}{imm}</ul></div>
<h2>六、市场机会雷达（持仓/watchlist 之外的新线索）</h2><div class="card"><div class="mrow"><b>热门板块</b>{sect_html}</div>
<div style="margin-top:6px;font-size:.84rem;color:var(--muted)">新标的候选线索（须基本面研究后方可纳入观察，<b>非买入信号</b>）：</div><ul>{cand_html}</ul></div>
<h2>七、组合 & Watchlist 更新建议（须人工确认）</h2><div class="upd"><ul>{ups}</ul></div>
{_horizon_html(r.get('horizon'))}
{_tiers_html(r.get('tiers'))}
<footer>三层五面定期复盘(review.py)一键生成 · 复盘为信号聚合非投资建议 · 红线/建议须人工拍板 · 五面皆叠加层 · 含真实持仓仅存本地。</footer>
</div></body></html>"""


def _faces_md(h, us_earn):
    """五面 → markdown 无序列表（复用 _faces_lines 的文本，转 md 粗体项）。"""
    out = []
    for ln in _faces_lines(h, us_earn, None):
        t = ln.strip()
        for face in ("基本面", "技术面", "资金面", "情绪面", "消息面"):
            if t.startswith(face):
                out.append(f"  - **{face}** {t[len(face):].strip()}")
                break
    return out


def render_md(r):
    m, p = r["market"], r["port"]
    f = p.get("factor") or {}
    L = [f"# 投资组合定期复盘（三层五面）· {r['cadence'].upper()} · {r['date']}",
         "",
         f"> 账本：{r['source']} · 由全套工具链一键聚合 · 复盘为信号聚合、非投资建议；红线/建议须人工拍板；五面皆叠加层不替代基本面。",
         ""]
    # 执行摘要 + 行动清单
    L.append("## 执行摘要")
    L.append(f"- **市场**：{m['verdict']['summary']}")
    L.append(f"- **组合**：{len([h for h in r['holdings'] if not h.get('error')])} 只 · 有效因子 {f.get('n_eff', 0):.1f}/{f.get('n', 0)} · PC1 {f.get('pc1_pct', 0):.0f}%")
    L.append("\n## 🎯 行动清单")
    L += [f"- {a}" for a in r["actions"]] or ["- ✅ 无紧急事项"]
    if not r["actions"]:
        L.append("- ✅ 无紧急事项")

    # 一、市场五面
    mac_d = m.get("macro") or {}
    b = m.get("breadth") or {}
    nw = m.get("news") or {}
    L.append("\n## 一、市场五面摘要（→ 是否调整敞口）")
    L.append("| 面 | 读数 |")
    L.append("|---|---|")
    L.append(f"| 基本面(宏观) | {mac_d.get('icon', '')}{mac_d.get('regime', '—')}（PMI {(mac_d.get('pmi') or {}).get('make', '—')} · CPI {(mac_d.get('cpi') or {}).get('yoy', '—')}% · M2 {(mac_d.get('m2') or {}).get('m2_yoy', '—')}% · 10Y {mac_d.get('y10y', '—')}%） |")
    L.append("| 技术面(大盘) | " + (" · ".join(f"{MKT_CN.get(k, k)} {v}" for k, v in m.get("index_tech", {}).items()) or "—") + " |")
    L.append(f"| 资金面(市场) | A股涨停 {b.get('limit_up', '—')}/跌停 {b.get('limit_down', '—')}（{b.get('label', '—')}）· 北向2024-08停披露 |")
    L.append("| 情绪面(市场) | " + (" · ".join(f"{MKT_CN.get(k, k)} {v['score']}({v['label'][:4]})" for k, v in m.get("sentiment", {}).items()) or "—") + " |")
    L.append(f"| 消息面(市场) | 政策要闻 {nw.get('policy_count', 0)} 条 · 要闻情绪 {nw.get('cn_tone', '—')} · 未来窗口 {len(r['imminent'])} 项催化剂 |")
    for c in [x for x in nw.get("cn", []) if x.get("is_policy")][:3]:
        dot = {"利好": "🟢", "利空": "🔴", "中性": "⚪"}[c["direction"]]
        L.append(f"  - 🏛️{dot} {c['text'][:60]}")
    L.append(f"\n**▶ 市场结论**：{m['verdict']['summary']}" + (f"；{m['verdict']['caution']}" if m['verdict'].get('caution') else ""))

    # 二、组合层
    L.append("\n## 二、组合层")
    L.append(f"- 有效独立因子 **{f.get('n_eff', 0):.2f}/{f.get('n', 0)}** · PC1 {f.get('pc1_pct', 0):.1f}% · {f.get('verdict', '')}")
    L.append(f"- 因子倾斜：动量 {f.get('port_momentum_z', 0):+.2f} · 波动 {f.get('port_vol_z', 0):+.2f}")
    m = r.get("metrics")
    if m:
        v = m["verdicts"]
        def _fm(x, pct=False):
            return "—" if x is None else (f"{x:+.1%}" if pct else f"{x:+.2f}")
        L.append(f"- **量化五指标**（vs {m['benchmark']} · {m['n_periods']}期）：")
        L.append(f"  - Beta β **{_fm(m['beta'])}** {v['beta']}")
        L.append(f"  - Alpha 年化 **{_fm(m['alpha_annual'], True)}** {v['alpha']}")
        L.append(f"  - 夏普比率 **{_fm(m['sharpe'])}** {v['sharpe']}")
        L.append(f"  - 最大回撤 **{_fm(m['max_drawdown'], True)}** {v['max_drawdown']}")
        L.append(f"  - 信息比率 IR **{_fm(m['information_ratio'])}** {v['information_ratio']}")

    # 三、逐持仓五面
    L.append("\n## 三、逐持仓五面诊断")
    for h in sorted([x for x in r["holdings"] if not x.get("error")], key=lambda x: -x.get("weight", 0)):
        flags = holding_flags(h)
        tag = "  ".join(f"{lv}{msg}" for lv, msg in flags) if flags else "✓ 正常"
        L.append(f"\n### {(h.get('name') or h['symbol'])} `{h['symbol']}` · 持有{h.get('weight', 0):.0f}%　▶ {tag}")
        L += _faces_md(h, r["us_earn"])
        th = r["thesis"].get(h["symbol"].upper())
        if th and th.get("red_lines") and any(lv == "🔴" for lv, _ in flags):
            L.append(f"  - ⚠️ **红线**：{th['red_lines']}")

    # 四、watchlist
    if r["watch_extras"]:
        L.append("\n## 四、Watchlist 诊断（非持仓/观察）")
        for h in r["watch_extras"]:
            if h.get("error"):
                continue
            rs = reversal_signal(h)
            L.append(f"\n### {(h.get('name') or h['symbol'])} `{h['symbol']}` · {wl.STATE_CN.get(h.get('state', ''), h.get('state', ''))}" + (f"　▶ {rs}" if rs else ""))
            L += _faces_md(h, r["us_earn"])

    # 五、到期/催化剂
    L.append(f"\n## 五、到期复审（{len(r['due'])}）/ 临近催化剂（{len(r['imminent'])}）")
    for e in r["due"]:
        L.append(f"- 📋 {e['symbol']} {e.get('name') or ''} · 复审日 {e.get('review_date')}")
    for ev in r["imminent"]:
        L.append(f"- 🔔 {ev['date']} {ev['symbol']} {ev.get('detail', '')}")
    if not r["due"] and not r["imminent"]:
        L.append("- 无")

    # 六、机会雷达
    rd = r.get("radar")
    if rd:
        L.append("\n## 六、市场机会雷达（持仓/watchlist 之外的新线索）")
        hs = rd.get("sectors", {}).get("sectors", [])
        if hs:
            L.append("- **热门板块**(涨停聚合)：" + " · ".join(f"{s['sector']}({s['limit_up_count']})" for s in hs))
        L.append("- **新标的候选线索**（须基本面研究后方可纳入观察，**非买入信号**）：")
        for c in rd.get("candidates", {}).get("candidates", [])[:8]:
            ch = f"{c['change']:+.1f}%" if isinstance(c["change"], (int, float)) else "—"
            L.append(f"  - {c['signal']} {c['name']}（{c['code']}）{ch} · {c['detail']}")

    # 七、更新建议
    L.append("\n## 七、组合 & Watchlist 更新建议（须人工确认）")
    L += [f"- {u}" for u in r["updates"]]
    # 八、多周期收益对比表(1/3/5/10/15/20年 × 美/A/港指数)
    if r.get("horizon"):
        hmd = hcmp.render_md(r["horizon"])
        hmd = hmd.replace("# 多周期收益对比表（初始资金 $10,000）", "## 八、多周期收益对比表（初始资金 $10,000）")
        hmd = hmd.replace("\n## ①", "\n### ①").replace("\n## ②", "\n### ②").replace("\n## ③", "\n### ③")
        L.append("\n" + hmd)
    # 九、三级流水线回顾
    t = r.get("tiers")
    if t:
        L.append("\n## 九、三级机会流水线回顾")
        L.append(f"- **T3 持仓组合**({len(t['T3'])})：{', '.join(t['T3']) or '—'}")
        L.append(f"- **T2 观察名单**({len(t['T2'])})：{', '.join(t['T2']) or '—'}")
        L.append(f"- **T1 候选观察**({len(t['T1'])})——三市场全覆盖·★=印证强度(多源自动升级)：")
        recs = t.get("T1_recs", [])
        for mk, cn in (("A", "A股·龙虎榜/涨停"), ("US", "美股·13F新建仓"), ("HK", "港股·南向净买")):
            items = [r for r in recs if r.get("market") == mk]
            if items:
                L.append(f"  - **{cn}**：")
                for r in items[:6]:
                    st = "★" * min(int(r.get("strength", 1)), 5)
                    L.append(f"    - {st} {r['symbol']} {(r.get('name') or '')[:12]} — {r.get('reason', '')[:56]}")
        if t["issues"]:
            L.append("- ⚠️ 一致性：" + "；".join(t["issues"]))
        L.append("- 流转：T1→(研究)→T2→(买入)→T3；降级 T3→T2、T2→T1(级联)。★≥3=多源印证(强)，优先研究。")
    L.append("\n---\n*数据源：东财(A/H前复权+主力资金流+龙虎榜+涨停+宏观) · Yahoo(US) · Finnhub/Nasdaq(美股预期) · SEC EDGAR(13F) · 新浪7×24(要闻)。含真实持仓，仅存本地。不构成投资建议。*")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="定期复盘编排器（三层五面，P3 心跳，零依赖）")
    ap.add_argument("--from-ledger", default="data/portfolio/transactions.csv")
    ap.add_argument("--fx", default="USD=1,HKD=0.128,CNY=0.14")
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--weekly", action="store_true")
    ap.add_argument("--quarterly", action="store_true")
    ap.add_argument("--html", action="store_true")
    ap.add_argument("--md", action="store_true", help="导出 Markdown 到 reports/private/reviews/")
    args = ap.parse_args()
    r = run(args)
    print(render_text(r))
    outdir = os.path.join(ROOT, "reports", "private", "reviews")
    if args.html:
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, f"review-{r['cadence']}-{r['date']}.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render_html(r))
        print(f"\n[review] HTML 已导出 → {path}", file=sys.stderr)
    if args.md:
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, f"review-{r['cadence']}-{r['date']}.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render_md(r))
        print(f"[review] Markdown 已导出 → {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
