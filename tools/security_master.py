#!/usr/bin/env python3
"""标的主数据 + 点时(PIT)快照库（零外部依赖，仅 stdlib）。P3-1 事实源持久化。

给整套系统一个**单一事实源**：
  ① Security Master：内部ID ↔ 各市场代码/交易所/币种/名称/行业/上市退市状态，持久化到
     data/security_master.json。解决"同一标的多处硬编码"、跨市场对齐、退市标记。
  ② 点时(point-in-time)快照库：把每次取到的关键指标按 as_of 存档；查询 as_of(date) 只返回
     "该日期前已知"的数据 —— 防止回测/归因的**前视偏差(look-ahead bias)**。随快照积累而增值。

诚实边界：主数据的 market/exchange/currency 由 datalayer.detect 路由(可靠)、name 由行情取；
行业/上市日/退市状态受免费数据访问限制，支持**手动设定**或后续接入(自动退市列表本环境不稳，
故 backtest 的幸存者偏差仍需人工补退市样本)。PIT 库只在快照积累后才对回测有意义。

用法：
  python3 tools/security_master.py resolve 600519          # 解析并登记
  python3 tools/security_master.py set 9660.HK --status delisted --industry 智驾芯片
  python3 tools/security_master.py list [--status active]
  python3 tools/security_master.py snapshot 600519          # 记一条今日点时快照(价/PE/PB)
  python3 tools/security_master.py asof 600519 --date 2026-06-30   # 查该日期前已知数据
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SM_STORE = os.path.join(ROOT, "data", "security_master.json")
PIT_STORE = os.path.join(ROOT, "data", "pit_store.json")
STATUSES = ("active", "suspended", "delisted")


def _today():
    return datetime.now().strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# 纯逻辑
# --------------------------------------------------------------------------
def internal_id(market, symbol):
    return f"{market}-{symbol}"


def exchange_of(info):
    if info["market"] == "A":
        return {"SH": "SSE", "SZ": "SZSE", "BJ": "BSE"}.get(info["symbol"].split(".")[-1], "?")
    if info["market"] == "HK":
        return "HKEX"
    return "US"


def pit_latest(snapshots, as_of):
    """点时查询：合并 as_of<=给定日期 的所有快照(晚者覆盖早者)，返回生效日与字段。防前视。"""
    valid = sorted([s for s in snapshots if s.get("as_of") and s["as_of"] <= as_of], key=lambda s: s["as_of"])
    merged = {}
    for s in valid:
        merged.update(s.get("fields") or {})
    return {"as_of_effective": valid[-1]["as_of"] if valid else None, "fields": merged, "n_snapshots": len(valid)}


# --------------------------------------------------------------------------
# 存储
# --------------------------------------------------------------------------
def _load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f) or default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def resolve(symbol, refresh=False):
    db = _load(SM_STORE, {"securities": {}})
    info = dl.detect(symbol)
    key = info["symbol"]
    if key in db["securities"] and not refresh:
        return db["securities"][key]
    name = db["securities"].get(key, {}).get("name")
    try:
        name = dl.fetch_quote(symbol, cross=False).get("name") or name
    except Exception:  # noqa: BLE001
        pass
    rec = db["securities"].get(key, {})
    rec.update({"internal_id": internal_id(info["market"], key), "symbol": key,
                "market": info["market"], "exchange": exchange_of(info),
                "currency": info["currency"], "name": name,
                "status": rec.get("status", "active"),
                "industry": rec.get("industry"), "listing_date": rec.get("listing_date"),
                "updated": _today(), "added": rec.get("added", _today())})
    db["securities"][key] = rec
    _save(SM_STORE, db)
    return rec


def set_field(symbol, **kv):
    db = _load(SM_STORE, {"securities": {}})
    key = dl.detect(symbol)["symbol"]
    if key not in db["securities"]:
        resolve(symbol)
        db = _load(SM_STORE, {"securities": {}})
    for k, v in kv.items():
        if v is not None:
            if k == "status" and v not in STATUSES:
                raise SystemExit(f"status 须为 {STATUSES}")
            db["securities"][key][k] = v
    db["securities"][key]["updated"] = _today()
    _save(SM_STORE, db)
    return db["securities"][key]


def snapshot(symbol):
    """记一条今日点时快照(价/PE/PB/总市值，来自腾讯 gtimg，A股)。其它市场记价。"""
    resolve(symbol)
    info = dl.detect(symbol)
    fields = {}
    try:
        if info["market"] == "A":
            raw = dl._curl(f"https://qt.gtimg.cn/q={info['tencent']}")
            f = raw.split('"', 2)[1].split("~")
            fields = {"price": float(f[3]), "pe": float(f[39]), "pb": float(f[46]), "mktcap_yi": float(f[44])}
        else:
            q = dl.fetch_quote(symbol, cross=False)
            fields = {"price": q.get("price")}
    except Exception as e:  # noqa: BLE001
        fields = {"error": str(e)}
    db = _load(PIT_STORE, {})
    key = info["symbol"]
    db.setdefault(key, []).append({"as_of": _today(), "fields": fields})
    _save(PIT_STORE, db)
    return {"symbol": key, "as_of": _today(), "fields": fields}


def asof(symbol, date):
    key = dl.detect(symbol)["symbol"]
    snaps = _load(PIT_STORE, {}).get(key, [])
    return pit_latest(snaps, date)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="标的主数据 + 点时快照库（P3-1 事实源，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("resolve", help="解析并登记标的主数据")
    r.add_argument("symbol"); r.add_argument("--refresh", action="store_true"); r.add_argument("--json", action="store_true")
    s = sub.add_parser("set", help="手动设定字段(status/industry/listing_date)")
    s.add_argument("symbol"); s.add_argument("--status"); s.add_argument("--industry"); s.add_argument("--listing-date")
    li = sub.add_parser("list", help="列出主数据"); li.add_argument("--status"); li.add_argument("--json", action="store_true")
    sn = sub.add_parser("snapshot", help="记一条今日点时快照"); sn.add_argument("symbol"); sn.add_argument("--json", action="store_true")
    ao = sub.add_parser("asof", help="点时查询(防前视)"); ao.add_argument("symbol"); ao.add_argument("--date", required=True); ao.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.cmd == "resolve":
        rec = resolve(args.symbol, args.refresh)
        print(json.dumps(rec, ensure_ascii=False, indent=2) if args.json
              else f"[{rec['internal_id']}] {rec['name']} · {rec['exchange']} · {rec['currency']} · {rec['status']}")
    elif args.cmd == "set":
        rec = set_field(args.symbol, status=args.status, industry=args.industry, listing_date=args.listing_date)
        print(f"✅ {rec['symbol']}: status={rec['status']} · industry={rec.get('industry')} · listing={rec.get('listing_date')}")
    elif args.cmd == "list":
        db = _load(SM_STORE, {"securities": {}})
        recs = [v for v in db["securities"].values() if not args.status or v.get("status") == args.status]
        if args.json:
            print(json.dumps(recs, ensure_ascii=False, indent=2))
        else:
            print(f"Security Master · {len(recs)} 条")
            for v in sorted(recs, key=lambda x: x["internal_id"]):
                print(f"  [{v['internal_id']:<14}] {v['name'] or '':<12} {v['exchange']:<6} {v['currency']:<4} {v['status']}"
                      + (f" · {v['industry']}" if v.get("industry") else ""))
    elif args.cmd == "snapshot":
        d = snapshot(args.symbol)
        print(json.dumps(d, ensure_ascii=False, indent=2) if args.json else f"✅ {d['symbol']} 快照 @ {d['as_of']}: {d['fields']}")
    elif args.cmd == "asof":
        d = asof(args.symbol, args.date)
        print(json.dumps(d, ensure_ascii=False, indent=2) if args.json
              else f"截至 {args.date} 已知({d['n_snapshots']}条快照，生效 {d['as_of_effective']}): {d['fields']}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
