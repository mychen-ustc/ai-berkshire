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
    t1 = sorted(r["symbol"] for r in pool
                if r["symbol"].upper() not in held and r["symbol"].upper() not in
                {s.upper() for s in t2})
    issues = []
    # 一致性:持仓应在 watchlist 里标 holding
    for h in held:
        e = wl_by.get(h)
        if not e:
            issues.append(f"持仓 {h} 不在 watchlist(建议 promote 或补录)")
        elif e.get("state") != "holding":
            issues.append(f"持仓 {h} 在 watchlist 状态为 {e.get('state')}≠holding(建议同步)")
    return {"T1": t1, "T2": t2, "T3": t3, "issues": issues}


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


def pool_add(symbol, name, market, source, reason, path=POOL):
    recs = pool_load(path)
    if any(r["symbol"].upper() == symbol.upper() for r in recs):
        return False
    recs.append({"symbol": symbol, "name": name or "", "market": market or "",
                 "source": source or "", "reason": reason or "", "added": wl._today()})
    pool_save(recs, path)
    return True


def pool_remove(symbol, path=POOL):
    recs = pool_load(path)
    new = [r for r in recs if r["symbol"].upper() != symbol.upper()]
    pool_save(new, path)
    return len(new) < len(recs)


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
    import radar as rad
    n = 0
    exclude = list(_holdings()) + [e["symbol"] for e in wl.load()["entries"]]
    try:
        cands = rad.candidates(exclude, 12).get("candidates", [])
    except Exception as e:  # noqa: BLE001
        cands = []
        print(f"⚠️ A股雷达取数失败: {str(e)[:50]}")
    for c in cands:
        if pool_add(c.get("code", c.get("symbol", "")), c.get("name", ""), "A",
                    "雷达-A股龙虎榜/涨停", c.get("signal", ""), args.pool):
            n += 1
    # 美股 13F 新建仓线索
    try:
        us = us_leads()
        for c in us:
            if pool_add(c["symbol"], c["name"], "US", "雷达-美股13F新建仓", c["reason"], args.pool):
                n += 1
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 美股13F线索取数失败: {str(e)[:50]}")
    print(f"✅ 雷达线索落入 T1：新增 {n} 个候选(A股 + 美股;港股数据受限未接)")


def us_leads(funds=("berkshire", "pershing", "scion", "baupost", "appaloosa"), limit=8):
    """美股"聪明钱"线索:超级投资者最新 13F 的**新建仓**(A股龙虎榜机构买入的对等物)。
    13F 用 issuer 名(非 ticker),作线索够用——研究时再定位代码。按建仓额取前 limit。"""
    import edgar_13f as e13
    out = []
    for f in funds:
        try:
            cik = e13._resolve(None, f)
            ch = e13.changes(cik, f, top=40)
        except Exception:  # noqa: BLE001
            continue
        for m in ch.get("moves", []):
            if "新建" in str(m.get("action", "")):    # 只取新建仓(最强信号)
                out.append({"symbol": m["issuer"][:24], "name": m["issuer"], "value": m["new_value"],
                            "reason": f"{ch.get('name', f)[:16]}新建仓 {e13._yi_usd(m['new_value'])}"})
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
        print(f"\n  T1 候选池明细:")
        for r in pool:
            if r["symbol"].upper() not in {h.upper() for h in held}:
                print(f"    · {r['symbol']:<10}[{r.get('market', '?')}] {r.get('source', '')} — {r.get('reason', '')[:40]}")
    if v["issues"]:
        print(f"\n  ⚠️ 一致性检查:")
        for i in v["issues"]:
            print(f"    · {i}")
    print(f"\n  流转规则：T1→(研究)→T2→(买入)→T3；降级 T3→T2、T2→T1(级联)。")


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
    args = ap.parse_args()
    {"capture": cmd_capture, "capture-radar": cmd_capture_radar, "promote": cmd_promote,
     "demote": cmd_demote, "status": cmd_status}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
