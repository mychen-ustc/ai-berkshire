#!/usr/bin/env python3
"""三级机会流水线（零外部依赖）。

把"从线索到持仓"做成有纪律的三级漏斗，并支持降级级联：

  T1 候选观察名单 (data/candidate_pool.jsonl) —— 原始线索(雷达/选股器/手工)，低承诺，无需论点。
  T2 观察名单     (watchlist.pipeline.json)   —— 已承诺研究，有论点/红线/复审日。
  T3 持仓组合     (账本 transactions.csv)      —— 实际持有。

  晋级：T1 →(commit研究)→ T2 →(买入)→ T3
  降级(级联)：T3 剔除 →回到 T2；T2 剔除 →回到 T1。  ← 用户指定规则

复盘时对三层清单一并回顾(review.py 第九节)。radar 线索(A股龙虎榜 + 美股13F新建仓)
自动落入 T1，避免"线索一闪而过、没人跟进"。

用法：
  python3 tools/pipeline.py capture --symbol NVDA --market US --source 手工 --reason "AI算力龙头"
  python3 tools/pipeline.py capture-radar         # 雷达线索(A+US)批量落入 T1
  python3 tools/pipeline.py promote --symbol NVDA # T1→T2(晋级观察名单)
  python3 tools/pipeline.py demote  --symbol COST # T3→T2 或 T2→T1(级联降级)
  python3 tools/pipeline.py status                # 三层总览 + 一致性检查
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import watchlist as wl  # noqa: E402
import ledger as L  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL = os.path.join(ROOT, "data", "candidate_pool.jsonl")
LEDGER = os.path.join(ROOT, "data", "portfolio", "transactions.csv")
WATCHING = ("discovered", "screening", "researching", "candidate")   # T2 的"在看"状态


# --------------------------------------------------------------------------
# 纯函数（可测）
# --------------------------------------------------------------------------
ISSUER_TICKER = {   # 13F issuer 名 → ticker(用于与持仓去重;13F无ticker)
    "ALPHABET": "GOOGL", "APPLE": "AAPL", "MICROSOFT": "MSFT", "NVIDIA": "NVDA",
    "AMERICAN EXPRESS": "AXP", "COCA": "KO", "COSTCO": "COST", "NASDAQ": "NDAQ",
    "META PLATFORMS": "META", "AMAZON": "AMZN", "BERKSHIRE": "BRK.B",
}


def canon_symbol(sym):
    """把 13F issuer 名归一到 ticker(便于与持仓去重);其余原样大写。纯函数。"""
    u = (sym or "").upper()
    for name, tk in ISSUER_TICKER.items():
        if name in u:
            return tk
    return u


def dedup_pool(records):
    """候选池按 symbol 去重(保留最早 added)。纯函数。"""
    seen = {}
    for r in sorted(records, key=lambda x: x.get("added", "")):
        seen.setdefault(r["symbol"].upper(), r)
    return sorted(seen.values(), key=lambda x: x.get("added", ""))


def tier_view(pool, wl_entries, holdings):
    """→ {T1:[...], T2:[...], T3:[...], issues:[...]}。三层视图 + 一致性检查。纯函数。
    holdings: set of held symbols(账本)。wl_entries: watchlist entries。"""
    held = {h.upper() for h in holdings}
    wl_by = {e["symbol"].upper(): e for e in wl_entries}
    t3 = sorted(held)
    t2 = sorted(e["symbol"] for e in wl_entries if e.get("state") in WATCHING
                and e["symbol"].upper() not in held)
    t2u = {s.upper() for s in t2}
    # 去重用 canon(把 13F issuer 名归一到 ticker,避免已持仓的 Alphabet 当新线索)
    t1_recs = sorted((r for r in pool if canon_symbol(r["symbol"]) not in held
                      and canon_symbol(r["symbol"]) not in t2u and r["symbol"].upper() not in t2u),
                     key=lambda x: (-x.get("strength", 1)))
    t1 = [r["symbol"] for r in t1_recs]
    issues = []
    # 一致性:持仓应在 watchlist 里标 holding
    for h in held:
        e = wl_by.get(h)
        if not e:
            issues.append(f"持仓 {h} 不在 watchlist(建议 promote 或补录)")
        elif e.get("state") != "holding":
            issues.append(f"持仓 {h} 在 watchlist 状态为 {e.get('state')}≠holding(建议同步)")
    return {"T1": t1, "T2": t2, "T3": t3, "T1_recs": t1_recs, "issues": issues}


# --------------------------------------------------------------------------
# 候选池存取
# --------------------------------------------------------------------------
def pool_load(path=POOL):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return dedup_pool([json.loads(ln) for ln in f if ln.strip()])


def pool_save(records, path=POOL):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in dedup_pool(records):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def pool_add(symbol, name, market, source, reason, strength=1, path=POOL):
    recs = pool_load(path)
    ex = next((r for r in recs if r["symbol"].upper() == symbol.upper()), None)
    if ex:
        # 已存在:若新证据更强或来自不同信号，累积印证(多源=更强)
        if reason and reason not in (ex.get("reason") or ""):
            ex["reason"] = (ex.get("reason", "") + " ⊕ " + reason)[:200]
            ex["strength"] = max(ex.get("strength", 1), strength) + 1   # 多源印证升级
            pool_save(recs, path)
        return False
    recs.append({"symbol": symbol, "name": name or "", "market": market or "",
                 "source": source or "", "reason": reason or "", "strength": strength,
                 "added": wl._today()})
    pool_save(recs, path)
    return True


def pool_remove(symbol, path=POOL):
    recs = pool_load(path)
    new = [r for r in recs if r["symbol"].upper() != symbol.upper()]
    pool_save(new, path)
    return len(new) < len(recs)


def triage_score(strength, mom_3m, ann_vol):
    """线索分诊分:证据强度为主(×2) + 动量/波动微调。→ (score, tags)。纯函数。"""
    score = float(strength) * 2.0
    tags = []
    if mom_3m is not None:
        if mom_3m > 0.05:
            score += 1.0
            tags.append("动量↑")
        elif mom_3m < -0.15:
            score -= 1.0
            tags.append("下跌趋势⚠")
    if ann_vol is not None and ann_vol > 0.6:
        score -= 0.5
        tags.append("高波⚠")
    return round(score, 1), tags


def _quick_price(symbol):
    """→ (mom_3m, ann_vol) 由周频价格算;取不到(如美股issuer名)返回(None,None)。"""
    import datalayer as dl
    import math as _m
    try:
        px = [p[1] for p in dl.fetch_history(symbol, freq="weekly", period="1y")["points"]]
        if len(px) < 20:
            return None, None
        mom = px[-1] / px[-14] - 1                       # 近~3月动量
        rets = [_m.log(px[i] / px[i - 1]) for i in range(1, len(px))]
        mu = sum(rets) / len(rets)
        vol = _m.sqrt(sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)) * _m.sqrt(52)
        return mom, vol
    except Exception:  # noqa: BLE001
        return None, None


def _holdings(ledger_path=LEDGER):
    try:
        pos, _, _, _ = L.rebuild(L.load_ledger(ledger_path))
        return {s for s, p in pos.items() if p.qty > 0}
    except Exception:  # noqa: BLE001
        return set()


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
def cmd_capture(args):
    ok = pool_add(args.symbol, args.name, args.market, args.source, args.reason, args.pool)
    print(f"{'✅ 已加入' if ok else '⏭️ 已存在'} T1 候选观察名单: {args.symbol}"
          + (f"（{args.source}: {args.reason}）" if ok else ""))


def cmd_capture_radar(args):
    n = {"A": 0, "US": 0, "HK": 0}
    for market, fn in (("A", _a_leads), ("US", us_leads), ("HK", hk_leads)):
        try:
            for c in fn():
                if pool_add(c["symbol"], c.get("name", ""), market,
                            f"雷达-{c.get('signal', '')}", c.get("reason", ""),
                            c.get("strength", 1), args.pool):
                    n[market] += 1
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ {market} 线索取数失败: {str(e)[:50]}")
    print(f"✅ 雷达线索落入 T1：A股 +{n['A']} · 美股 +{n['US']} · 港股 +{n['HK']}"
          f"（全覆盖三市场;线索附印证证据,多源自动升级强度）")


def _a_leads(limit=12):
    """A股线索:龙虎榜机构买入(强,含席位数/成功率) + 高连板(弱)。附证据强度。"""
    import radar as rad
    exclude = list(_holdings()) + [e["symbol"] for e in wl.load()["entries"]]
    out = []
    for c in rad.candidates(exclude, limit).get("candidates", []):
        strg = int(c.get("strength", 1))               # 龙虎榜机构=3,连板=1
        out.append({"symbol": c.get("code", ""), "name": c.get("name", ""),
                    "signal": c.get("signal", "").replace("🏛️", "").strip(),
                    "strength": strg, "reason": c.get("detail", c.get("signal", ""))})
    return out


def us_leads(funds=("berkshire", "pershing", "scion", "baupost", "appaloosa"), limit=8):
    """美股"聪明钱"线索:超级投资者最新 13F 的**新建仓**(A股龙虎榜机构买入的对等物)。
    跨基金印证:同一标的被多位买入 → strength 更高(多源印证=强)。按建仓额取前 limit。"""
    import edgar_13f as e13
    agg = {}                                            # issuer → {funds:[], value}
    for f in funds:
        try:
            cik = e13._resolve(None, f)
            ch = e13.changes(cik, f, top=40)
        except Exception:  # noqa: BLE001
            continue
        fname = ch.get("name", f)[:16]
        for m in ch.get("moves", []):
            if "新建" in str(m.get("action", "")):
                iss = m["issuer"][:24]
                a = agg.setdefault(iss, {"funds": [], "value": 0.0})
                a["funds"].append(fname)
                a["value"] = max(a["value"], m["new_value"])
    out = []
    for iss, a in agg.items():
        nf = len(a["funds"])
        strength = 3 if nf >= 2 else 2                  # 多基金新建=强印证(3)
        corr = f"·{nf}位投资者共建({'/'.join(a['funds'][:2])})" if nf >= 2 else f"·{a['funds'][0]}"
        out.append({"symbol": iss, "name": iss, "value": a["value"], "strength": strength,
                    "market": "US", "signal": "13F新建仓",
                    "reason": f"13F新建仓 {e13._yi_usd(a['value'])}{corr}"})
    return sorted(out, key=lambda x: (-x["strength"], -x["value"]))[:limit]


def hk_leads(limit=8):
    """港股"聪明钱"线索:港股通南向**净买入**(内地资金买港股;A股龙虎榜的港股对等物)。
    datacenter 南向十大成交,取净买入为正者。"""
    import datalayer as dl
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_MUTUAL_TOP10DEAL"
           "&columns=ALL&filter=(MUTUAL_TYPE=%22004%22)&sortColumns=TRADE_DATE,RANK"
           "&sortTypes=-1,1&pageSize=30")
    try:
        d = json.loads(dl._curl(url, headers=["Referer: https://data.eastmoney.com/"]))
        data = (d.get("result") or {}).get("data") or []
    except Exception:  # noqa: BLE001
        return []
    latest = data[0].get("TRADE_DATE") if data else None
    out = []
    for r in data:
        if r.get("TRADE_DATE") != latest:               # 只取最新交易日
            continue
        nb = r.get("NET_BUY_AMT")
        if nb is None or nb <= 0:                        # 只要净买入为正(南向看多)
            continue
        code = str(r.get("SECURITY_CODE") or r.get("SECUCODE", "")).split(".")[0]
        out.append({"symbol": f"{code}.HK", "name": r.get("SECURITY_NAME", code),
                    "value": nb, "strength": 2, "market": "HK", "signal": "南向净买入",
                    "reason": f"港股通南向净买 {nb / 1e8:.1f}亿"})
    return sorted(out, key=lambda x: -x["value"])[:limit]


def cmd_promote(args):
    sym = args.symbol
    pool = pool_load(args.pool)
    in_pool = any(r["symbol"].upper() == sym.upper() for r in pool)
    db = wl.load()
    e = wl._find(db, sym)
    if in_pool and not e:
        rec = next(r for r in pool if r["symbol"].upper() == sym.upper())
        wl.add(sym, name=rec.get("name", ""), state="researching",
               thesis=f"从T1候选池晋级：{rec.get('source', '')} {rec.get('reason', '')}"[:200],
               owner="pipeline")
        pool_remove(sym, args.pool)
        print(f"⬆️ {sym}: T1 候选池 → T2 观察名单(researching)")
    elif e and e["state"] in WATCHING:
        print(f"ℹ️ {sym} 已在 T2 观察名单(状态 {e['state']})。晋级 T3 持仓 = 实际买入"
              f"(用 rebalance/账本下单后 `watchlist set {sym} holding`)。")
    elif e and e["state"] == "holding":
        print(f"ℹ️ {sym} 已是 T3 持仓。")
    else:
        print(f"⚠️ {sym} 不在 T1;先 capture 加入候选池。")


def cmd_demote(args):
    sym = args.symbol
    held = _holdings()
    db = wl.load()
    e = wl._find(db, sym)
    if sym.upper() in {h.upper() for h in held} or (e and e["state"] == "holding"):
        # T3 → T2：从持仓剔除,回到观察名单(exiting)
        if e:
            wl.set_state(sym, "exiting")
        else:
            wl.add(sym, state="exiting", thesis="从持仓剔除→回观察名单", owner="pipeline")
        print(f"⬇️ {sym}: T3 持仓 → T2 观察名单(exiting)。"
              f"⚠️ 实际减仓请用 rebalance 下卖单;本操作只更新流水线状态。")
    elif e and e["state"] in WATCHING:
        # T2 → T1：从 watchlist 剔除,回到候选池
        pool_add(sym, e.get("name", ""), "", "从T2观察名单降级",
                 (e.get("thesis", "") or "")[:80], args.pool)
        wl.remove(sym)
        print(f"⬇️ {sym}: T2 观察名单 → T1 候选池(降级保留线索)")
    else:
        print(f"⚠️ {sym} 不在 T2/T3。")


def cmd_status(args):
    pool = pool_load(args.pool)
    db = wl.load()
    held = _holdings()
    v = tier_view(pool, db["entries"], held)
    print("=" * 60)
    print("三级机会流水线 · 总览")
    print("=" * 60)
    print(f"\n  T3 持仓组合({len(v['T3'])}): {', '.join(v['T3']) or '—'}")
    print(f"  T2 观察名单({len(v['T2'])}): {', '.join(v['T2']) or '—'}")
    print(f"  T1 候选观察({len(v['T1'])}): {', '.join(v['T1']) or '—'}")
    if pool:
        print(f"\n  T1 候选池明细(按市场分组·★=印证强度,多源自动升级):")
        held_u = {h.upper() for h in held}
        for mk, cn in (("A", "A股"), ("US", "美股"), ("HK", "港股")):
            items = [r for r in pool if r.get("market") == mk and r["symbol"].upper() not in held_u]
            if not items:
                continue
            print(f"    【{cn}】")
            for r in sorted(items, key=lambda x: -x.get("strength", 1)):
                st = "★" * min(int(r.get("strength", 1)), 5)
                print(f"      {st:<5}{r['symbol']:<11}{(r.get('name') or '')[:12]:<13} {r.get('reason', '')[:50]}")
    if v["issues"]:
        print(f"\n  ⚠️ 一致性检查:")
        for i in v["issues"]:
            print(f"    · {i}")
    print(f"\n  流转规则：T1→(研究)→T2→(买入)→T3；降级 T3→T2、T2→T1(级联)。")


def cmd_triage(args):
    """对 T1 候选池自动分诊:证据强度 + 快速价格信号(动量/波动) → 排序 + 晋级建议。"""
    pool = pool_load(args.pool)
    held = {h.upper() for h in _holdings()}
    wl_syms = {e["symbol"].upper() for e in wl.load()["entries"]}
    cands = [r for r in pool if canon_symbol(r["symbol"]) not in held
             and canon_symbol(r["symbol"]) not in wl_syms and r["symbol"].upper() not in wl_syms]
    scored = []
    for r in cands:
        mom, vol = (None, None)
        if r.get("market") in ("A", "HK"):               # 有代码,可取价;美股为issuer名跳过
            mom, vol = _quick_price(r["symbol"])
        sc, tags = triage_score(r.get("strength", 1), mom, vol)
        scored.append({**r, "score": sc, "mom_3m": mom, "ann_vol": vol, "tags": tags})
    scored.sort(key=lambda x: -x["score"])
    print("=" * 72)
    print(f"T1 候选池自动分诊 · {len(scored)} 个线索 · 分=证据强度×2 + 动量/波动微调")
    print("=" * 72)
    print(f"  {'分':>4} {'市场':<4}{'标的':<12}{'名称':<12}{'快速信号':<16}{'提示线索'}")
    for r in scored:
        m = {"A": "A股", "US": "美股", "HK": "港股"}.get(r.get("market"), "?")
        sig = []
        if r["mom_3m"] is not None:
            sig.append(f"动量{r['mom_3m']:+.0%}")
        if r["ann_vol"] is not None:
            sig.append(f"波{r['ann_vol']:.0%}")
        sig += r["tags"]
        print(f"  {r['score']:>4.1f} {m:<4}{r['symbol']:<12}{(r.get('name') or '')[:11]:<12}"
              f"{('·'.join(sig))[:15]:<16}{r.get('reason', '')[:30]}")
    top = [r for r in scored if r["score"] >= args.threshold]
    print(f"\n  🎯 建议优先研究(分≥{args.threshold}, {len(top)}个): "
          + (", ".join(f"{r['symbol']}({r['score']})" for r in top[:8]) or "无"))
    print(f"  → 分高=证据强+动量正;仍须 /investment-research 基本面研究后再 promote 到 T2,非买入信号。")
    print(f"  ⚠️ 美股线索为 13F issuer 名(无ticker),仅按证据强度评分,需手工定位代码再研究。")


def main():
    ap = argparse.ArgumentParser(description="三级机会流水线:候选池/观察名单/持仓(零依赖)")
    ap.add_argument("--pool", default=POOL)
    sub = ap.add_subparsers(dest="cmd")
    cap = sub.add_parser("capture", help="加线索到 T1 候选池")
    cap.add_argument("--symbol", required=True)
    cap.add_argument("--name", default="")
    cap.add_argument("--market", default="")
    cap.add_argument("--source", default="手工")
    cap.add_argument("--reason", default="")
    cr = sub.add_parser("capture-radar", help="雷达线索(A+US)批量落入 T1")
    pr = sub.add_parser("promote", help="晋级 T1→T2")
    pr.add_argument("--symbol", required=True)
    dm = sub.add_parser("demote", help="降级 T3→T2 或 T2→T1")
    dm.add_argument("--symbol", required=True)
    sub.add_parser("status", help="三层总览 + 一致性检查")
    tr = sub.add_parser("triage", help="T1候选池自动分诊(证据+快速信号排序)")
    tr.add_argument("--threshold", type=float, default=6.0, help="晋级建议分数线(默认6)")
    args = ap.parse_args()
    {"capture": cmd_capture, "capture-radar": cmd_capture_radar, "promote": cmd_promote,
     "demote": cmd_demote, "status": cmd_status, "triage": cmd_triage}.get(
        args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
