#!/usr/bin/env python3
"""数据底座自动摄取编排器（P0 事实源补齐，零外部依赖）。

诊断(全链路能力诊断评级-20260716)发现地基裂缝：security_master.json/pit_store.json
磁盘不存在、corporate_actions/delisting 仅 demo 各 1 条、反偏差引擎对真实工作 universe
(持仓+候选池+watchlist)**纯空转**。本编排器一键补齐、且带新鲜度戳，让 monitor 能体检：

  ① security_master  — 解析真实工作 universe 的证券主数据(名称/市场/交易所/币种)并持久化
  ② corporate_actions — 从 Yahoo events 抓**真实**拆股/分红(美股)，去重增量入库(供复权/持仓账务)
  ③ pit_store        — 对 A 股记点时快照(价/PE/PB/市值,腾讯)，让点时库真正开始积累
  ④ 新鲜度清单        — data/ingest_manifest.json 记录各源 count + updated，供 monitor 体检

诚实边界：摄取即**真数据**，不编。A 股/港股公司行动免费源不稳，本环境只自动抓美股 Yahoo
(A/H 的拆股/分红需另补或靠 datalayer 前复权);13F issuer 名(非 ticker)自动跳过、需 ticker 映射;
退市库(防幸存者)是另一维度，见 seed-delisting(补录真实退市样本)。

用法：
  python3 tools/ingest_universe.py universe          # 打印解析出的真实工作 universe
  python3 tools/ingest_universe.py run               # 全量摄取 → 三库 + 新鲜度清单
  python3 tools/ingest_universe.py run --dry-run     # 只列 universe/计划,不写盘
  python3 tools/ingest_universe.py seed-delisting     # 补录若干真实退市样本(防幸存者)
  python3 tools/ingest_universe.py manifest          # 看新鲜度清单
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl          # noqa: E402
import security_master as sm    # noqa: E402
import corporate_actions as ca  # noqa: E402
import delisting as dz          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "data", "portfolio", "transactions.csv")
POOL = os.path.join(ROOT, "data", "candidate_pool.jsonl")
WATCHLIST = os.path.join(ROOT, "data", "watchlist.pipeline.json")
MANIFEST = os.path.join(ROOT, "data", "ingest_manifest.json")


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _market(symbol):
    """崩溃安全的市场判定：非法/无法解析的 symbol 返回 '?' 而非抛错。"""
    try:
        return dl.detect(symbol)["market"]
    except Exception:  # noqa: BLE001
        return "?"


# --------------------------------------------------------------------------
# 纯函数（可测）
# --------------------------------------------------------------------------
# 现金/币种记号(账本里 FX/入金行会把币种写进 symbol 列),非证券
CASH_TOKENS = {"CNY", "USD", "HKD", "EUR", "GBP", "JPY", "SGD", "CASH", "现金"}


def is_ticker(symbol):
    """是否像可解析的交易代码(而非 13F issuer 名如 'ALPHABET INC'、或币种记号)。纯函数。
    规则：非空、无空格、长度合理、非币种/现金记号。"""
    s = (symbol or "").strip()
    if not s or " " in s or len(s) > 12:
        return False
    if s.upper() in CASH_TOKENS:
        return False
    return any(c.isalnum() for c in s)


def parse_universe(ledger_syms, pool_recs, watchlist_items):
    """合并三源为去重的真实工作 universe。返回 (universe[list of {symbol, sources}], skipped[list])。
    非 ticker(如 13F issuer 名)进 skipped。纯函数。"""
    src = {}   # symbol -> set(sources)
    skipped = []

    def add(sym, source):
        s = (sym or "").strip()
        if not s:
            return
        if not is_ticker(s):
            skipped.append({"symbol": s, "source": source})
            return
        src.setdefault(s, set()).add(source)

    for s in ledger_syms:
        add(s, "持仓")
    for r in pool_recs:
        add(r.get("symbol"), "候选池")
    for it in watchlist_items:
        add(it.get("symbol"), "watchlist")

    universe = [{"symbol": s, "sources": sorted(v)} for s, v in sorted(src.items())]
    # skipped 去重(按 symbol)
    seen, sk = set(), []
    for x in skipped:
        if x["symbol"] not in seen:
            seen.add(x["symbol"])
            sk.append(x)
    return universe, sk


def parse_yahoo_events(result, symbol):
    """把 Yahoo chart events(dividends/splits) 解析为 corporate_actions 记录。纯函数。
    split: numerator/denominator → ratio(1拆N 的 N)；dividend: amount(每股)。"""
    out = []
    events = (result or {}).get("events", {}) or {}
    for k, v in (events.get("splits", {}) or {}).items():
        dt = datetime.fromtimestamp(int(k), tz=timezone.utc).strftime("%Y-%m-%d")
        num = float(v.get("numerator", 0) or 0)
        den = float(v.get("denominator", 0) or 0)
        if den > 0 and num > 0:
            out.append({"symbol": symbol, "type": "split", "date": dt,
                        "ratio": num / den, "source": "Yahoo"})
    for k, v in (events.get("dividends", {}) or {}).items():
        dt = datetime.fromtimestamp(int(k), tz=timezone.utc).strftime("%Y-%m-%d")
        out.append({"symbol": symbol, "type": "dividend", "date": dt,
                    "amount": float(v["amount"]), "source": "Yahoo"})
    return sorted(out, key=lambda x: (x["date"], x["type"]))


def ca_key(rec):
    """公司行动去重键(同标的同日同类型同幅度视为同一条)。纯函数。"""
    amt = rec.get("ratio", rec.get("amount", ""))
    return (rec.get("symbol"), rec.get("type"), rec.get("date"), round(float(amt), 6) if amt != "" else "")


def merge_actions(existing, incoming):
    """把 incoming 里 existing 没有的公司行动挑出来(去重)。返回 new[list]。纯函数。"""
    seen = {ca_key(r) for r in existing}
    new = []
    for r in incoming:
        if ca_key(r) not in seen:
            seen.add(ca_key(r))
            new.append(r)
    return new


# --------------------------------------------------------------------------
# 读 universe（IO）
# --------------------------------------------------------------------------
def _ledger_symbols(path=LEDGER):
    if not os.path.exists(path):
        return []
    syms = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            s = (row.get("symbol") or "").strip()
            if s:
                syms.append(s)
    return syms


def _pool_recs(path=POOL):
    if not os.path.exists(path):
        return []
    return [json.loads(ln) for ln in open(path, encoding="utf-8") if ln.strip()]


def _watchlist_items(path=WATCHLIST):
    if not os.path.exists(path):
        return []
    d = json.load(open(path, encoding="utf-8"))
    if isinstance(d, list):
        return d
    for k in ("items", "watchlist", "securities"):
        if isinstance(d.get(k), list):
            return d[k]
    return []


def load_universe():
    return parse_universe(_ledger_symbols(), _pool_recs(), _watchlist_items())


# --------------------------------------------------------------------------
# 抓取（IO）
# --------------------------------------------------------------------------
def fetch_yahoo_actions(symbol, years=10):
    """Yahoo events=div,split → corporate_actions 记录(仅美股)。IO。"""
    info = dl.detect(symbol)
    if info["market"] != "US":
        return []
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{info['yahoo']}"
           f"?interval=1d&range={years}y&events=div,split")
    try:
        d = json.loads(dl._curl(url))
        result = d["chart"]["result"][0]
    except Exception:  # noqa: BLE001
        return []
    return parse_yahoo_events(result, symbol)


# --------------------------------------------------------------------------
# 摄取编排
# --------------------------------------------------------------------------
def ingest_security_master(universe):
    ok, fail = 0, []
    for u in universe:
        try:
            sm.resolve(u["symbol"], refresh=True)
            ok += 1
        except Exception as e:  # noqa: BLE001
            fail.append((u["symbol"], str(e)[:40]))
    return ok, fail


def ingest_corporate_actions(universe):
    existing = ca.load()
    all_new = []
    for u in universe:
        if _market(u["symbol"]) != "US":
            continue
        incoming = fetch_yahoo_actions(u["symbol"])
        new = merge_actions(existing + all_new, incoming)
        all_new.extend(new)
    for r in all_new:
        ca.append(r)
    return len(all_new)


def ingest_pit_snapshots(universe):
    n = 0
    for u in universe:
        if _market(u["symbol"]) != "A":
            continue
        try:
            res = sm.snapshot(u["symbol"])
            if res["fields"] and "error" not in res["fields"]:
                n += 1
        except Exception:  # noqa: BLE001
            pass
    return n


def _count_jsonl(path):
    if not os.path.exists(path):
        return 0
    return sum(1 for ln in open(path, encoding="utf-8") if ln.strip())


def _count_master():
    db = sm._load(sm.SM_STORE, {"securities": {}})
    return len(db.get("securities", {}))


def _count_pit():
    db = sm._load(sm.PIT_STORE, {})
    return sum(len(v) for v in db.values())


def write_manifest(universe_size, skipped, extra=None):
    m = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "universe_size": universe_size,
        "skipped_non_ticker": skipped,
        "sources": {
            "security_master": {"count": _count_master(), "path": "data/security_master.json"},
            "corporate_actions": {"count": _count_jsonl(ca.STORE), "path": "data/corporate_actions.jsonl"},
            "pit_store": {"count": _count_pit(), "path": "data/pit_store.json"},
            "pit_financials": {"count": _count_jsonl(os.path.join(ROOT, "data", "pit_financials.jsonl")), "path": "data/pit_financials.jsonl"},
            "delisting": {"count": _count_jsonl(dz.STORE), "path": "data/delisting.jsonl"},
        },
    }
    if extra:
        m.update(extra)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    return m


# --------------------------------------------------------------------------
# 真实退市样本(高置信、textbook；防幸存者的“墓地”起始集，可扩)
# --------------------------------------------------------------------------
DELISTING_SEED = [
    {"symbol": "ENRNQ", "name": "安然", "listed": "1986-01-01", "delisted": "2001-12-02",
     "reason": "bankruptcy", "terminal_return": -1.0, "note": "财务造假破产,股权归零"},
    {"symbol": "WCOEQ", "name": "世通WorldCom", "listed": "1989-01-01", "delisted": "2002-07-21",
     "reason": "bankruptcy", "terminal_return": -1.0, "note": "会计丑闻破产"},
    {"symbol": "300104", "name": "乐视网", "listed": "2010-08-12", "delisted": "2020-07-21",
     "reason": "regulatory", "terminal_return": -0.85, "note": "面值退市(估近似)"},
]


def cmd_seed_delisting(args):
    existing = {r["symbol"] for r in dz.load()}
    added = 0
    for r in DELISTING_SEED:
        if r["symbol"] in existing:
            continue
        dz.append(r)
        added += 1
        print(f"  ✅ {r['symbol']:<8}{r['name']:<12} 退市 {r['delisted']} ({r['reason']})")
    print(f"\n补录 {added} 条真实退市样本(已有 {len(existing)} 条)。"
          f"这是高置信 textbook 起始集,非全市场库——survivorship-check 现可产出真实结果。")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def cmd_universe(args):
    universe, skipped = load_universe()
    print("=" * 62)
    print(f"真实工作 universe · {len(universe)} 个可解析标的（持仓 ⊕ 候选池 ⊕ watchlist）")
    print("=" * 62)
    by_mkt = {}
    for u in universe:
        m = _market(u["symbol"])
        by_mkt.setdefault(m, []).append(u["symbol"])
    for m in sorted(by_mkt):
        print(f"  [{m}] ({len(by_mkt[m])}): {', '.join(by_mkt[m])}")
    if skipped:
        print(f"\n  ⏭️ 跳过 {len(skipped)} 个非 ticker(13F issuer 名,需映射): "
              + ", ".join(x["symbol"] for x in skipped))


def cmd_run(args):
    universe, skipped = load_universe()
    print("=" * 62)
    print(f"数据底座摄取 · universe {len(universe)} 标的 · 跳过 {len(skipped)} 非ticker" +
          (" · [DRY-RUN]" if args.dry_run else ""))
    print("=" * 62)
    if args.dry_run:
        cmd_universe(args)
        print("\n  [DRY-RUN] 未写盘。去掉 --dry-run 执行真实摄取。")
        return

    print("\n① security_master 解析证券主数据...")
    ok, fail = ingest_security_master(universe)
    print(f"   ✅ 登记/刷新 {ok} 条主数据 → data/security_master.json"
          + (f"（{len(fail)} 失败）" if fail else ""))

    print("\n② corporate_actions 抓 Yahoo 真实拆股/分红(美股)...")
    n_ca = ingest_corporate_actions(universe)
    print(f"   ✅ 新增 {n_ca} 条公司行动 → data/corporate_actions.jsonl（去重增量）")

    print("\n③ pit_store A股点时快照(价/PE/PB/市值,腾讯)...")
    n_pit = ingest_pit_snapshots(universe)
    print(f"   ✅ 新增 {n_pit} 条 A股点时快照 → data/pit_store.json")

    print("\n④ 写新鲜度清单...")
    m = write_manifest(len(universe), skipped)
    print(f"   ✅ data/ingest_manifest.json @ {m['generated_at']}")
    print("      " + " · ".join(f"{k}:{v['count']}" for k, v in m["sources"].items()))
    print("\n完成。monitor.py 现可体检数据新鲜度;反偏差引擎不再对空池空转。")
    if fail:
        print(f"\n  ⚠️ {len(fail)} 个主数据解析失败: " + ", ".join(f"{s}({e})" for s, e in fail[:5]))


def cmd_manifest(args):
    if not os.path.exists(MANIFEST):
        print("尚无 ingest_manifest.json，先跑 `ingest_universe.py run`。")
        return
    m = json.load(open(MANIFEST, encoding="utf-8"))
    print("=" * 62)
    print(f"数据底座新鲜度清单 · 生成于 {m['generated_at']}")
    print("=" * 62)
    print(f"  universe: {m['universe_size']} 标的 · 跳过非ticker {len(m.get('skipped_non_ticker', []))}")
    for k, v in m["sources"].items():
        print(f"  {k:<20} {v['count']:>5} 条  ({v['path']})")


def main():
    ap = argparse.ArgumentParser(description="数据底座自动摄取编排器(P0 事实源补齐,零依赖)")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="全量摄取真实 universe → 三库 + 新鲜度清单")
    r.add_argument("--dry-run", action="store_true", help="只列不写")
    sub.add_parser("universe", help="打印解析出的真实工作 universe")
    sub.add_parser("seed-delisting", help="补录真实退市样本(防幸存者)")
    sub.add_parser("manifest", help="看新鲜度清单")
    args = ap.parse_args()
    {"run": cmd_run, "universe": cmd_universe, "seed-delisting": cmd_seed_delisting,
     "manifest": cmd_manifest}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
