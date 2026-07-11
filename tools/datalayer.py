#!/usr/bin/env python3
"""统一数据层（P0-3，零外部依赖，仅 stdlib + curl）。

A/H/美股统一行情：符号自动路由到对应市场的数据源，取数后为每条记录盖上
完整元数据信封（source/source_url/fetched_at/as_of/currency/unit/version），
做跨源交叉校验（主源 vs 第二源），过质量门禁（缺失/过期/冲突显式标记、不静默使用），
并写入本地快照缓存以保证「同一快照→相同输出」的可复现性。

来源登记与许可见 config/data-sources.json。

用法：
  python3 tools/datalayer.py quote 600519            # A股(贵州茅台)
  python3 tools/datalayer.py quote 0700.HK           # 港股(腾讯)
  python3 tools/datalayer.py quote AAPL --json       # 美股，输出JSON信封
  python3 tools/datalayer.py quote 600519 --offline  # 只读缓存快照(可复现)
  python3 tools/datalayer.py sources --market A       # 列出该市场可用数据源
"""
import argparse
import json
import os
import re
import subprocess
from datetime import datetime

VERSION = "datalayer/0.1"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data", "cache", "quotes")
REGISTRY = os.path.join(ROOT, "config", "data-sources.json")
_DATE_SLASH = re.compile(r"^\d{4}/\d{2}/\d{2}")       # 港股: 2026/07/10 16:08:46
_DATE_COMPACT = re.compile(r"^\d{14}$")               # A股: 20260710161445


def _norm_dt(tok):
    """把腾讯行情两种时间格式统一成 ISO 'YYYY-MM-DD HH:MM:SS'。"""
    if _DATE_SLASH.match(tok):
        return tok.replace("/", "-")
    if _DATE_COMPACT.match(tok):
        return f"{tok[0:4]}-{tok[4:6]}-{tok[6:8]} {tok[8:10]}:{tok[10:12]}:{tok[12:14]}"
    return None


# --------------------------------------------------------------------------
# 网络（curl 直连，绕过系统代理；GBK/UTF-8 自适应）
# --------------------------------------------------------------------------
def _curl(url, headers=None, timeout=12):
    cmd = ["/usr/bin/curl", "-s", "--max-time", str(timeout), "--noproxy", "*",
           "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"]
    for h in headers or []:
        cmd += ["-H", h]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, timeout=timeout + 3)
    if r.returncode != 0 or not r.stdout:
        raise ConnectionError(f"请求失败: {url}")
    try:
        return r.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return r.stdout.decode("gbk", errors="replace")


# --------------------------------------------------------------------------
# 符号 → 市场路由与规范化
# --------------------------------------------------------------------------
def detect(symbol):
    """返回 {market, symbol(规范化), tencent, sina, yahoo, stooq, currency}。"""
    s = symbol.strip()
    u = s.upper()

    # 港股：*.HK 或 hkNNNNN 或纯5位带HK
    if u.endswith(".HK") or u.startswith("HK"):
        digits = re.sub(r"\D", "", u)
        code5 = f"{int(digits):05d}"
        return {"market": "HK", "symbol": f"{int(digits):04d}.HK",
                "tencent": f"hk{code5}", "sina": f"hk{code5}",
                "yahoo": f"{int(digits):04d}.HK", "stooq": None, "currency": "HKD"}

    # A股：6位数字，或带 .SS/.SH/.SZ/.BJ 或 sh/sz 前缀
    m = re.match(r"^(SH|SZ|BJ)?(\d{6})(\.(SS|SH|SZ|BJ))?$", u)
    if m:
        code = m.group(2)
        pfx = (m.group(1) or "").lower()
        suf = (m.group(4) or "")
        if not pfx:
            if suf in ("SS", "SH"):
                pfx = "sh"
            elif suf == "SZ":
                pfx = "sz"
            elif suf == "BJ":
                pfx = "bj"
            else:
                pfx = "sh" if code[0] == "6" else ("bj" if code[0] in "48" else "sz")
        yh = {"sh": ".SS", "sz": ".SZ", "bj": ".BJ"}[pfx]
        return {"market": "A", "symbol": f"{code}.{pfx.upper()}",
                "tencent": f"{pfx}{code}", "sina": f"{pfx}{code}",
                "yahoo": f"{code}{yh}", "stooq": None, "currency": "CNY"}

    # 其余按美股
    return {"market": "US", "symbol": u, "tencent": None, "sina": None,
            "yahoo": u, "stooq": f"{s.lower()}.us", "currency": "USD"}


# --------------------------------------------------------------------------
# 解析器（纯函数，可用 fixture 离线测试）
# --------------------------------------------------------------------------
def parse_tencent(raw):
    """腾讯 gtimg：v_xxx="1~名称~代码~现价~昨收~今开~量~...~日期时间~涨跌~涨跌%~最高~最低~..."。"""
    body = raw.split('"', 2)[1] if '"' in raw else raw
    f = body.split("~")
    if len(f) < 6:
        raise ValueError("腾讯行情字段不足")
    out = {"name": f[1], "code": f[2], "price": float(f[3]),
           "prev_close": float(f[4]), "open": float(f[5])}
    try:
        out["volume"] = float(f[6])
    except (ValueError, IndexError):
        out["volume"] = None
    # 用日期时间锚点定位涨跌/最高/最低（A/H 索引与格式不同，锚点法更稳）
    for i, tok in enumerate(f):
        nd = _norm_dt(tok)
        if nd:
            out["as_of"] = nd
            try:
                out["change"] = float(f[i + 1])
                out["change_pct"] = float(f[i + 2])
                out["high"] = float(f[i + 3])
                out["low"] = float(f[i + 4])
            except (ValueError, IndexError):
                pass
            break
    return out


def parse_yahoo(text):
    data = json.loads(text)
    res = data["chart"]["result"][0]
    meta = res["meta"]
    price = meta.get("regularMarketPrice")
    if price is None:
        closes = [c for c in res.get("indicators", {}).get("quote", [{}])[0].get("close", []) if c is not None]
        price = closes[-1] if closes else None
    as_of = None
    if meta.get("regularMarketTime"):
        as_of = datetime.utcfromtimestamp(meta["regularMarketTime"]).strftime("%Y-%m-%d %H:%M:%S")
    return {"name": meta.get("shortName") or meta.get("symbol"), "code": meta.get("symbol"),
            "price": float(price) if price is not None else None,
            "prev_close": meta.get("chartPreviousClose") or meta.get("previousClose"),
            "open": meta.get("regularMarketDayOpen"),
            "high": meta.get("regularMarketDayHigh"), "low": meta.get("regularMarketDayLow"),
            "volume": meta.get("regularMarketVolume"), "as_of": as_of,
            "exchange": meta.get("fullExchangeName"), "currency": meta.get("currency")}


def parse_sina(raw, market):
    body = raw.split('"', 2)[1] if '"' in raw else raw
    f = body.split(",")
    if len(f) < 4:
        return None
    if market == "HK":
        return float(f[6])   # HK: 英文名,中文名,开,昨收,高,低,现价
    return float(f[3])       # A: 名称,开,昨收,现价


def parse_stooq(csv_text):
    lines = [ln for ln in csv_text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    header = [h.strip().lower() for h in lines[0].split(",")]
    row = lines[1].split(",")
    rec = dict(zip(header, row))
    try:
        return float(rec.get("close"))
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# 交叉校验 & 质量门禁（纯函数）
# --------------------------------------------------------------------------
def cross_check(p1, p2, tol_pct=1.0):
    if p2 is None:
        return {"status": "single-source", "note": "第二源不可用，未交叉校验"}
    if not p1:
        return {"status": "conflict", "note": "主源价格缺失"}
    div = abs(p1 - p2) / p1 * 100
    return {"status": "ok" if div <= tol_pct else "conflict",
            "second_price": p2, "divergence_pct": round(div, 4), "tolerance_pct": tol_pct}


def assess_quality(env, now=None, stale_days=5):
    now = now or datetime.now()
    warns = []
    if not env.get("price") or env["price"] <= 0:
        warns.append("价格缺失或非正")
    ao = env.get("as_of")
    if ao:
        try:
            d = datetime.strptime(ao[:10], "%Y-%m-%d")
            if (now - d).days > stale_days:
                warns.append(f"数据过期：as_of 距今 {(now - d).days} 天 > {stale_days}")
        except ValueError:
            pass
    if env.get("cross_check", {}).get("status") == "conflict":
        warns.append(f"跨源冲突：偏差 {env['cross_check'].get('divergence_pct')}% > 容差")
    status = "ok"
    if any("过期" in w for w in warns):
        status = "stale"
    if any(("冲突" in w) or ("缺失" in w) for w in warns):
        status = "warn"
    return {"status": status, "warnings": warns}


# --------------------------------------------------------------------------
# 取数编排 + 信封
# --------------------------------------------------------------------------
def fetch_quote(symbol, cross=True, stale_days=5):
    info = detect(symbol)
    fetched_at = datetime.now().astimezone().isoformat(timespec="seconds")
    src, url, parsed = _fetch_primary(info)
    raw_symbol = info["tencent"] if info["market"] in ("A", "HK") else info["yahoo"]
    env = {
        "symbol": info["symbol"], "raw_symbol": raw_symbol,
        "market": info["market"], "field": "quote",
        "name": parsed.get("name"), "price": parsed.get("price"),
        "prev_close": parsed.get("prev_close"), "open": parsed.get("open"),
        "high": parsed.get("high"), "low": parsed.get("low"), "volume": parsed.get("volume"),
        "change_pct": parsed.get("change_pct"),
        "currency": parsed.get("currency") or info["currency"], "unit": "share",
        "as_of": parsed.get("as_of"), "available_at": parsed.get("as_of"),
        "source": src, "source_url": url, "fetched_at": fetched_at, "version": VERSION,
    }
    if env["price"] and env["prev_close"] and env.get("change_pct") is None:
        env["change_pct"] = round((env["price"] / env["prev_close"] - 1) * 100, 4)
    if cross:
        env["cross_check"] = _fetch_second(info, env["price"])
    else:
        env["cross_check"] = {"status": "single-source", "note": "已禁用交叉校验"}
    env["quality"] = assess_quality(env, stale_days=stale_days)
    return env


def _fetch_primary(info):
    if info["market"] in ("A", "HK"):
        url = f"https://qt.gtimg.cn/q={info['tencent']}"
        return "tencent_gtimg", url, parse_tencent(_curl(url))
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{info['yahoo']}?interval=1d&range=5d"
    return "yahoo_finance", url, parse_yahoo(_curl(url))


def _fetch_second(info, primary_price):
    try:
        if info["market"] in ("A", "HK"):
            url = f"https://hq.sinajs.cn/list={info['sina']}"
            p2 = parse_sina(_curl(url, headers=["Referer: https://finance.sina.com.cn"]), info["market"])
        else:
            url = f"https://stooq.com/q/l/?s={info['stooq']}&f=sd2t2ohlcv&e=csv"
            p2 = parse_stooq(_curl(url))
        cc = cross_check(primary_price, p2)
        cc["second_source"] = "sina_hq" if info["market"] in ("A", "HK") else "stooq"
        return cc
    except Exception as e:  # noqa: BLE001  第二源失败不应阻断主流程，显式降级
        return {"status": "single-source", "note": f"第二源取数失败：{e}"}


# --------------------------------------------------------------------------
# 快照缓存（可复现）
# --------------------------------------------------------------------------
def cache_path(symbol):
    return os.path.join(CACHE_DIR, f"{detect(symbol)['symbol'].replace('/', '_')}.json")


def save_snapshot(env):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_path(env["symbol"]), "w", encoding="utf-8") as f:
        json.dump(env, f, ensure_ascii=False, indent=2)


def load_snapshot(symbol):
    p = cache_path(symbol)
    if not os.path.exists(p):
        raise FileNotFoundError(f"无缓存快照：{p}（请先联网取一次）")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _print_env(env):
    q = env["quality"]
    icon = {"ok": "✅", "warn": "⚠️", "stale": "🕒"}.get(q["status"], "•")
    print("=" * 62)
    print(f"{env['name']}  [{env['symbol']} · {env['market']}]  {icon} {q['status']}")
    print("=" * 62)
    print(f"  现价:     {env['price']} {env['currency']}   (昨收 {env['prev_close']}, 涨跌 {env['change_pct']}%)")
    if env.get("high") is not None:
        print(f"  高/低/开: {env['high']} / {env['low']} / {env['open']}")
    print(f"  数据时点: {env['as_of']}   抓取: {env['fetched_at']}")
    print(f"  主源:     {env['source']}  ({env['source_url']})")
    cc = env["cross_check"]
    if cc.get("status") == "ok":
        print(f"  交叉校验: ✅ {cc.get('second_source')} 偏差 {cc.get('divergence_pct')}%（≤{cc.get('tolerance_pct')}%）")
    elif cc.get("status") == "conflict":
        print(f"  交叉校验: ❌ 冲突 {cc.get('second_source')} 偏差 {cc.get('divergence_pct')}%")
    else:
        print(f"  交叉校验: — {cc.get('note')}")
    if q["warnings"]:
        for w in q["warnings"]:
            print(f"  ⚠️ {w}")


def main():
    ap = argparse.ArgumentParser(description="统一数据层：A/H/美股行情 + 元数据 + 交叉校验（P0-3，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    q = sub.add_parser("quote", help="取单只行情（自动路由市场）")
    q.add_argument("symbol")
    q.add_argument("--no-cross-check", action="store_true")
    q.add_argument("--offline", action="store_true", help="只读缓存快照(可复现)")
    q.add_argument("--json", action="store_true")
    q.add_argument("--stale-days", type=int, default=5)
    s = sub.add_parser("sources", help="列出数据源与投研服务商登记册")
    s.add_argument("--market", choices=["A", "HK", "US"])
    s.add_argument("--tier", choices=["free-scrape", "free-api", "paid-pro"])
    args = ap.parse_args()

    if args.cmd == "quote":
        if args.offline:
            env = load_snapshot(args.symbol)
        else:
            env = fetch_quote(args.symbol, cross=not args.no_cross_check, stale_days=args.stale_days)
            save_snapshot(env)
        print(json.dumps(env, ensure_ascii=False, indent=2) if args.json else "")
        if not args.json:
            _print_env(env)
    elif args.cmd == "sources":
        reg = json.load(open(REGISTRY, encoding="utf-8"))
        rows = [x for x in reg["sources"]
                if (not args.market or args.market in x["markets"])
                and (not args.tier or x["tier"] == args.tier)]
        print(f"数据源登记册 v{reg['version']}（{reg['status']}）— 共 {len(rows)} 条")
        for x in sorted(rows, key=lambda r: (r["tier"], r["priority"])):
            live = "🟢live" if x.get("live_adapter") else "○"
            print(f"  [{x['tier']:<11}] {x['name']:<22} {'/'.join(x['markets']):<14} "
                  f"P{x['priority']} {live}  {'·'.join(x['data'])}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
