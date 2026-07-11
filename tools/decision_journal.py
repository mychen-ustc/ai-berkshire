#!/usr/bin/env python3
"""决策日志与校准（P1，零外部依赖）。

记录每一次买/卖/持有/放弃的决策：论点、信心、对"论点成立"赋的概率、
目标价、仓位、卖出触发器。事后 resolve 记录结果，再用 **Brier 分数** 检验
"当初的概率估计到底准不准"（决策校准）——这是机构自我进化的核心，也是把
"我觉得七成会涨"变成可问责、可复盘的量化记录。

隐私：真实决策存 data/portfolio/decisions.jsonl（gitignore）；示例见 .example。

用法：
  python3 tools/decision_journal.py add --date 2026-07-11 --action BUY --symbol 0700.HK \
      --price 460 --currency HKD --size 8 --conviction 4 --p-base 0.7 --target 620 \
      --horizon 24 --thesis "微信生态现金牛，AI是免费期权，当前~15x非IFRS" \
      --triggers "MAU连续两季下滑" "AI capex连续2年吞噬FCF"
  python3 tools/decision_journal.py list [--open|--resolved]
  python3 tools/decision_journal.py resolve --id 1 --date 2026-12-31 --price 640
  python3 tools/decision_journal.py calibrate      # Brier + 命中率 + 按信心分层
"""
import argparse
import json
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOURNAL = os.path.join(ROOT, "data", "portfolio", "decisions.jsonl")


# --------------------------------------------------------------------------
# 校准数学（纯函数，可测）
# --------------------------------------------------------------------------
def brier_score(preds):
    """preds: [(p, outcome0or1)]。Brier = 均方误差，越低越准；0=完美，0.25=瞎猜。"""
    preds = [(float(p), int(o)) for p, o in preds]
    if not preds:
        return None
    return sum((p - o) ** 2 for p, o in preds) / len(preds)


def calibration_buckets(preds, edges=(0.0, 0.2, 0.4, 0.6, 0.8, 1.01)):
    """按预测概率分桶，比较"预测均值"与"实际命中率"，看是否系统性高估/低估。"""
    out = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        grp = [(p, o) for p, o in preds if lo <= p < hi]
        if grp:
            pred_mean = sum(p for p, _ in grp) / len(grp)
            actual = sum(o for _, o in grp) / len(grp)
            out.append((f"{lo:.0%}-{hi if hi <= 1 else 1:.0%}", len(grp), pred_mean, actual))
    return out


# --------------------------------------------------------------------------
# 存取
# --------------------------------------------------------------------------
def load(path=JOURNAL):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def append(record, path=JOURNAL):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def rewrite(records, path=JOURNAL):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
def cmd_add(args):
    recs = load(args.path)
    rec = {
        "id": (max([r["id"] for r in recs]) + 1) if recs else 1,
        "date": args.date, "action": args.action.upper(), "symbol": args.symbol,
        "price": args.price, "currency": args.currency, "size_pct": args.size,
        "conviction": args.conviction, "p_base": args.p_base, "base_target": args.target,
        "horizon_months": args.horizon, "thesis": args.thesis,
        "triggers": args.triggers or [], "status": "open", "resolved": None,
    }
    append(rec, args.path)
    print(f"✅ 已记录决策 #{rec['id']}: {rec['action']} {rec['symbol']} @ {rec['price']} "
          f"(信心{rec['conviction']}/5, P(论点成立)={rec['p_base']})")
    if args.thesis and len(args.thesis) > 200:
        print(f"  ⚠️ 论点 {len(args.thesis)} 字 > 200：说不清就不该买（镜子测试）")
    if not rec["triggers"]:
        print("  ⚠️ 未设卖出触发器：买入前应先想清楚什么情况下认错离场")


def cmd_list(args):
    recs = load(args.path)
    if args.open:
        recs = [r for r in recs if r["status"] == "open"]
    if args.resolved:
        recs = [r for r in recs if r["status"] == "resolved"]
    if args.symbol:
        recs = [r for r in recs if r["symbol"] == args.symbol]
    print(f"决策日志（{len(recs)} 条）")
    for r in recs:
        tag = "🟢open" if r["status"] == "open" else "✔resolved"
        line = (f"  #{r['id']} {r['date']} {r['action']:<4} {r['symbol']:<10} @{r['price']} "
                f"信心{r['conviction']} P={r['p_base']} 目标{r['base_target']} [{tag}]")
        if r["status"] == "resolved" and r["resolved"]:
            rv = r["resolved"]
            line += f" → {rv['date']} @{rv['price']} {'命中✓' if rv['hit'] else '未中✗'}"
        print(line)


def cmd_resolve(args):
    recs = load(args.path)
    hit_target = None
    for r in recs:
        if r["id"] == args.id:
            entry = r["price"]
            realized = (args.price / entry - 1) if entry else None
            # 命中定义：达到/超过基准目标价（做多方向）
            hit = (args.price >= r["base_target"]) if r["base_target"] else None
            r["status"] = "resolved"
            r["resolved"] = {"date": args.date, "price": args.price,
                             "hit": bool(hit), "realized_return": realized, "note": args.note or ""}
            hit_target = hit
            break
    else:
        raise SystemExit(f"未找到决策 #{args.id}")
    rewrite(recs, args.path)
    print(f"✅ 决策 #{args.id} 已了结 @ {args.price}："
          f"{'命中目标✓' if hit_target else '未达目标✗'}，实现收益 {realized:+.1%}"
          if realized is not None else f"✅ 决策 #{args.id} 已了结")


def cmd_calibrate(args):
    recs = [r for r in load(args.path) if r["status"] == "resolved" and r.get("p_base") is not None]
    preds = [(r["p_base"], 1 if r["resolved"]["hit"] else 0) for r in recs]
    print("=" * 58)
    print(f"决策校准（{len(preds)} 个已了结、含概率的决策）")
    print("=" * 58)
    if not preds:
        print("  样本不足：先 resolve 一些带 --p-base 的决策")
        return
    bs = brier_score(preds)
    hit = sum(o for _, o in preds) / len(preds)
    print(f"  Brier 分数: {bs:.4f}   (0=完美, 0.25=瞎猜, 越低越准)")
    print(f"  总命中率:   {hit:.1%}")
    print("\n  校准表（预测概率 vs 实际命中）——差得多说明系统性高估/低估:")
    print("    区间        样本   预测均值   实际命中")
    for label, n, pm, ac in calibration_buckets(preds):
        flag = "  ⚠️高估" if pm - ac > 0.15 else ("  ⚠️低估" if ac - pm > 0.15 else "")
        print(f"    {label:<10}{n:>4}    {pm:>7.0%}    {ac:>7.0%}{flag}")
    print("\n  按信心分层命中率:")
    for c in sorted({r["conviction"] for r in recs}):
        grp = [r for r in recs if r["conviction"] == c]
        h = sum(1 for r in grp if r["resolved"]["hit"]) / len(grp)
        print(f"    信心 {c}/5: {h:.0%}  ({len(grp)} 个)")


def main():
    ap = argparse.ArgumentParser(description="决策日志与校准（P1，零依赖）")
    ap.add_argument("--path", default=JOURNAL, help="决策日志文件(默认 data/portfolio/decisions.jsonl)")
    sub = ap.add_subparsers(dest="cmd")

    a = sub.add_parser("add", help="记录一个决策")
    a.add_argument("--date", required=True)
    a.add_argument("--action", required=True, choices=["BUY", "ADD", "TRIM", "SELL", "HOLD", "PASS",
                                                       "buy", "add", "trim", "sell", "hold", "pass"])
    a.add_argument("--symbol", required=True)
    a.add_argument("--price", type=float, required=True)
    a.add_argument("--currency", default="")
    a.add_argument("--size", type=float, help="目标仓位%")
    a.add_argument("--conviction", type=int, choices=[1, 2, 3, 4, 5], required=True)
    a.add_argument("--p-base", type=float, dest="p_base", help="P(论点成立) 0-1")
    a.add_argument("--target", type=float, dest="target", help="基准目标价")
    a.add_argument("--horizon", type=int, help="持有期(月)")
    a.add_argument("--thesis", default="", help="≤200字买入理由")
    a.add_argument("--triggers", nargs="*", help="卖出/复审触发器")

    li = sub.add_parser("list", help="列出决策")
    li.add_argument("--open", action="store_true")
    li.add_argument("--resolved", action="store_true")
    li.add_argument("--symbol")

    rs = sub.add_parser("resolve", help="了结一个决策并记录结果")
    rs.add_argument("--id", type=int, required=True)
    rs.add_argument("--date", required=True)
    rs.add_argument("--price", type=float, required=True)
    rs.add_argument("--note", default="")

    sub.add_parser("calibrate", help="Brier 校准 + 命中率 + 按信心分层")

    args = ap.parse_args()
    {"add": cmd_add, "list": cmd_list, "resolve": cmd_resolve,
     "calibrate": cmd_calibrate}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
