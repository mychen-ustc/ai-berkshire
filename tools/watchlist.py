#!/usr/bin/env python3
"""统一 Watchlist 状态机（零外部依赖，仅 stdlib）。P3 运营骨架。

把散落的候选/召回/持仓合并为一个入口 + 一条状态流水线，每个标的都带
论点/负责人/下一催化剂/红线/复审日——让"研究—决策—持有—退出"可持续运转、可复盘。

状态流水线：
  发现 → 初筛 → 深研 → 候选 → 持有 → 退出 → 归档
  (discovered → screening → researching → candidate → holding → exiting → archived)

存储：data/watchlist.json（个人研究流水线，已 gitignore；committed 的是 .example）。

用法：
  python3 tools/watchlist.py add 603986 --name 兆易创新 --thesis "存储超级周期质量龙头" --owner me --review 2026-08-01
  python3 tools/watchlist.py promote 603986            # 沿流水线前进一步
  python3 tools/watchlist.py set 603986 holding        # 直接置某状态
  python3 tools/watchlist.py list [--state candidate]
  python3 tools/watchlist.py due [--as-of 2026-07-13]  # 到期需复审
  python3 tools/watchlist.py catalyst 603986 "2026-07-30 业绩预告"
"""
import argparse
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 独立文件，避免与既有 data/watchlist.json（watch.py/stock_screener 的召回池，异 schema）冲突
STORE = os.path.join(ROOT, "data", "watchlist.pipeline.json")
STATES = ["discovered", "screening", "researching", "candidate", "holding", "exiting", "archived"]
STATE_CN = {"discovered": "发现", "screening": "初筛", "researching": "深研",
            "candidate": "候选", "holding": "持有", "exiting": "退出", "archived": "归档"}


# --------------------------------------------------------------------------
# 纯逻辑
# --------------------------------------------------------------------------
def next_state(state):
    i = STATES.index(state)
    return STATES[min(i + 1, len(STATES) - 1)]


def prev_state(state):
    i = STATES.index(state)
    return STATES[max(i - 1, 0)]


def is_due(review_date, as_of):
    """复审日 <= as_of 即到期（YYYY-MM-DD 字符串比较，ISO 可直接比）。"""
    return bool(review_date) and review_date <= as_of


def transition_note(old, new):
    oi, ni = STATES.index(old), STATES.index(new)
    if new == "archived" or ni == oi + 1 or ni == oi - 1:
        return "ok"
    if ni > oi:
        return f"跳进 {ni - oi} 级（{STATE_CN[old]}→{STATE_CN[new]}）"
    return f"回退 {oi - ni} 级（{STATE_CN[old]}→{STATE_CN[new]}）"


# --------------------------------------------------------------------------
# 存储
# --------------------------------------------------------------------------
def load():
    if not os.path.exists(STORE):
        return {"entries": []}
    with open(STORE, encoding="utf-8") as f:
        db = json.load(f) or {}
    db.setdefault("entries", [])
    return db


def save(db):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def _find(db, symbol):
    return next((e for e in db["entries"] if e["symbol"].upper() == symbol.upper()), None)


def _today():
    return datetime.now().strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# 操作
# --------------------------------------------------------------------------
def add(symbol, **kw):
    db = load()
    if _find(db, symbol):
        raise SystemExit(f"{symbol} 已在 watchlist，用 set/promote/catalyst 更新")
    e = {"symbol": symbol.upper(), "name": kw.get("name"), "state": kw.get("state") or "discovered",
         "thesis": kw.get("thesis"), "owner": kw.get("owner"), "next_catalyst": kw.get("catalyst"),
         "red_lines": kw.get("red_lines"), "review_date": kw.get("review"),
         "added": _today(), "updated": _today(), "history": [f"{_today()} 加入·{kw.get('state') or 'discovered'}"]}
    db["entries"].append(e)
    save(db)
    return e


def set_state(symbol, state):
    if state not in STATES:
        raise SystemExit(f"未知状态 {state}；可选：{'/'.join(STATES)}")
    db = load()
    e = _find(db, symbol) or _err(symbol)
    note = transition_note(e["state"], state)
    e["history"].append(f"{_today()} {STATE_CN[e['state']]}→{STATE_CN[state]}"
                        + ("" if note == "ok" else f"（{note}）"))
    e["state"], e["updated"] = state, _today()
    save(db)
    return e, note


def catalyst(symbol, text, review=None):
    db = load()
    e = _find(db, symbol) or _err(symbol)
    e["next_catalyst"] = text
    if review:
        e["review_date"] = review
    e["updated"] = _today()
    save(db)
    return e


def remove(symbol):
    db = load()
    e = _find(db, symbol) or _err(symbol)
    db["entries"].remove(e)
    save(db)
    return e


def _err(symbol):
    raise SystemExit(f"{symbol} 不在 watchlist")


# --------------------------------------------------------------------------
# 展示
# --------------------------------------------------------------------------
def render_list(entries):
    if not entries:
        return "  (空)"
    L = []
    for e in sorted(entries, key=lambda x: STATES.index(x["state"])):
        cat = f" · 催化剂:{e['next_catalyst']}" if e.get("next_catalyst") else ""
        rev = f" · 复审:{e['review_date']}" if e.get("review_date") else ""
        L.append(f"  [{STATE_CN[e['state']]}] {e['symbol']} {e.get('name') or ''}"
                 f"{'  论点:' + e['thesis'] if e.get('thesis') else ''}{cat}{rev}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="统一 Watchlist 状态机（P3 运营骨架，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("add", help="加入 watchlist")
    a.add_argument("symbol")
    for opt in ("name", "thesis", "owner", "catalyst", "red-lines", "review", "state"):
        a.add_argument(f"--{opt}")
    p = sub.add_parser("promote", help="沿流水线前进一步"); p.add_argument("symbol")
    dm = sub.add_parser("demote", help="沿流水线后退一步"); dm.add_argument("symbol")
    s = sub.add_parser("set", help="直接置某状态"); s.add_argument("symbol"); s.add_argument("state")
    c = sub.add_parser("catalyst", help="更新下一催化剂"); c.add_argument("symbol"); c.add_argument("text"); c.add_argument("--review")
    li = sub.add_parser("list", help="列出（可按状态）"); li.add_argument("--state"); li.add_argument("--json", action="store_true")
    du = sub.add_parser("due", help="到期需复审"); du.add_argument("--as-of")
    rm = sub.add_parser("remove", help="移除"); rm.add_argument("symbol")
    args = ap.parse_args()

    if args.cmd == "add":
        e = add(args.symbol, name=args.name, thesis=args.thesis, owner=args.owner,
                catalyst=args.catalyst, red_lines=getattr(args, "red_lines"), review=args.review, state=args.state)
        print(f"✅ 加入 [{STATE_CN[e['state']]}] {e['symbol']} {e.get('name') or ''}")
    elif args.cmd in ("promote", "demote"):
        db = load(); e = _find(db, args.symbol) or _err(args.symbol)
        new = next_state(e["state"]) if args.cmd == "promote" else prev_state(e["state"])
        _, note = set_state(args.symbol, new)
        print(f"✅ {args.symbol}: → [{STATE_CN[new]}]" + ("" if note == "ok" else f"（{note}）"))
    elif args.cmd == "set":
        _, note = set_state(args.symbol, args.state)
        print(f"✅ {args.symbol}: → [{STATE_CN[args.state]}]" + ("" if note == "ok" else f"（{note}）"))
    elif args.cmd == "catalyst":
        catalyst(args.symbol, args.text, args.review)
        print(f"✅ {args.symbol} 催化剂已更新")
    elif args.cmd == "list":
        db = load()
        es = [e for e in db["entries"] if not args.state or e["state"] == args.state]
        print(json.dumps(es, ensure_ascii=False, indent=2) if args.json else render_list(es))
    elif args.cmd == "due":
        as_of = args.as_of or _today()
        db = load()
        due = [e for e in db["entries"] if is_due(e.get("review_date"), as_of)]
        print(f"截至 {as_of} 需复审 {len(due)} 只:")
        print(render_list(due))
    elif args.cmd == "remove":
        remove(args.symbol); print(f"✅ 已移除 {args.symbol}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
