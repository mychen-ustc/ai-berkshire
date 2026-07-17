#!/usr/bin/env python3
"""运营监控与健康检查（零外部依赖）。

64 个工具 + cron 会跑，但没有监控——数据源挂了、cron 静默失败、数据变陈旧，没人知道。
本工具是系统的"心跳监测"：让机器出问题时**会喊你**，从"会跑的脚本"变"可信赖的机构"。

四类检查：
  1) 数据源健康——各市场行情(A/US/HK) + EDGAR 是否可达、返回是否新鲜(canary 探测)。
  2) cron 心跳(dead-man's-switch)——复盘日志多久没更新了?超期即告警。
  3) 数据新鲜度——账本/watchlist/点时库等关键文件的更新时效。
  4) 汇总健康看板——🟢/🟡/🔴 逐项 + 总体;不健康则非零退出码(接 cron/CI 告警)。

用法：
  python3 tools/monitor.py check           # 全面健康体检(退出码 0=健康,1=有🔴)
  python3 tools/monitor.py check --json
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------
# 纯函数（可测）
# --------------------------------------------------------------------------
def freshness_verdict(age_hours, warn_h, crit_h):
    """按数据年龄判健康。→ ('🟢'/'🟡'/'🔴', 文字)。纯函数。"""
    if age_hours is None:
        return ("🔴", "缺失/无数据")
    if age_hours <= warn_h:
        return ("🟢", f"{age_hours:.1f}h 内")
    if age_hours <= crit_h:
        return ("🟡", f"{age_hours:.1f}h(偏旧)")
    return ("🔴", f"{age_hours:.1f}h(过期)")


def deadman_verdict(age_hours, expected_interval_h):
    """dead-man's-switch:上次心跳距今 vs 预期间隔。超 1.5× 即过期。纯函数。"""
    if age_hours is None:
        return ("🔴", "从未运行")
    if age_hours <= expected_interval_h:
        return ("🟢", f"{age_hours:.1f}h 前")
    if age_hours <= expected_interval_h * 1.5:
        return ("🟡", f"{age_hours:.1f}h 前(略超期)")
    return ("🔴", f"{age_hours:.1f}h 前(严重超期,cron 可能已停)")


def overall_health(statuses):
    """一组状态(emoji)取最差。🔴>🟡>🟢。纯函数。"""
    if any(s == "🔴" for s in statuses):
        return "🔴"
    if any(s == "🟡" for s in statuses):
        return "🟡"
    return "🟢" if statuses else "🔴"


def _age_hours(ts, now):
    return None if ts is None else max(0.0, (now - ts) / 3600.0)


def _parse_iso(s):
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# 检查（I/O）
# --------------------------------------------------------------------------
def check_data_sources(now):
    """canary 探测各市场行情 + EDGAR 可达性/新鲜度。"""
    import datalayer as dl
    out = []
    canaries = [("A股行情(东财)", "600519"), ("美股行情(Yahoo)", "VOO"), ("港股行情(东财)", "2800.HK")]
    for name, sym in canaries:
        try:
            q = dl.fetch_quote(sym, cross=False)
            px = q.get("price")
            ao = q.get("as_of")
            ts = None
            if ao:
                try:
                    ts = datetime.strptime(ao[:19], "%Y-%m-%d %H:%M:%S").timestamp()
                except Exception:  # noqa: BLE001
                    ts = now
            emoji, note = ("🟢", f"可达·价{px}") if px else ("🔴", "返回空")
            # 行情新鲜度(交易时段外允许旧,故仅极端过期告警:>96h)
            if ts and _age_hours(ts, now) and _age_hours(ts, now) > 96:
                emoji, note = "🟡", f"{note}·数据{_age_hours(ts, now):.0f}h旧"
            out.append({"name": name, "status": emoji, "note": note})
        except Exception as e:  # noqa: BLE001
            out.append({"name": name, "status": "🔴", "note": f"不可达: {str(e)[:40]}"})
    # EDGAR
    try:
        import edgar_13f as e13
        r = e13._get("https://data.sec.gov/submissions/CIK0001067983.json")
        out.append({"name": "SEC EDGAR", "status": "🟢" if r else "🔴",
                    "note": "可达" if r else "返回空"})
    except Exception as e:  # noqa: BLE001
        out.append({"name": "SEC EDGAR", "status": "🔴", "note": f"不可达: {str(e)[:40]}"})
    return out


def check_files(now):
    """关键数据文件新鲜度。"""
    specs = [
        ("账本 transactions.csv", "data/portfolio/transactions.csv", 24 * 30, 24 * 90),
        ("watchlist 流水线", "data/watchlist.pipeline.json", 24 * 30, 24 * 120),
        ("T1 候选池", "data/candidate_pool.jsonl", 24 * 14, 24 * 45),
        ("点时财务库", "data/pit_financials.jsonl", 24 * 120, 24 * 400),
        ("数据底座清单", "data/ingest_manifest.json", 24 * 30, 24 * 90),
    ]
    out = []
    for name, rel, warn_h, crit_h in specs:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            out.append({"name": name, "status": "🟡", "note": "未创建(可选)"})
            continue
        age = _age_hours(os.path.getmtime(p), now)
        emoji, note = freshness_verdict(age, warn_h, crit_h)
        out.append({"name": name, "status": emoji, "note": note})
    return out


def check_runs(now):
    """自动运行审计:各触发源最近运行时效 + 失败连击(基于 run_audit 真实记录,精确 dead-man's-switch)。"""
    try:
        import run_audit as ra
    except Exception:  # noqa: BLE001
        return [{"name": "运行审计", "status": "🟡", "note": "run_audit 不可用"}]
    recs = ra.load()
    if not recs:
        return [{"name": "运行审计", "status": "🟢", "note": "暂无记录（cron/CI 首次运行后填充）"}]
    s = ra.summarize(recs)
    expect = {"cron-ingest": (8 * 24, 16 * 24), "cron-monitor": (3 * 24, 8 * 24)}  # (warn_h, crit_h)
    out = []
    for trig, v in sorted(s.items()):
        if v["failure_streak"] >= 2:
            out.append({"name": trig, "status": "🔴",
                        "note": f"连续失败 {v['failure_streak']} 次（最近 {v['last_run']}）"})
            continue
        status = "🟡" if v["last_status"] == "failed" else "🟢"
        note = f"最近 {v['last_run']}（{v['last_status']}）"
        if trig in expect:
            age = _age_hours(_parse_iso(v["last_run"]), now)
            emoji, fnote = freshness_verdict(age, *expect[trig])
            if emoji == "🔴":
                status, note = "🔴", f"{fnote}（最近 {v['last_run']}）"
            elif emoji == "🟡" and status == "🟢":
                status, note = "🟡", f"{fnote}（最近 {v['last_run']}）"
        out.append({"name": trig, "status": status, "note": note})
    return out


def check_cron(now):
    """cron 心跳:复盘日志 mtime 作 dead-man's-switch(预期至少每周更新一次)。"""
    p = os.path.join(ROOT, "logs", "review-cron.log")
    if not os.path.exists(p):
        return [{"name": "cron 复盘心跳", "status": "🟡",
                 "note": "无日志(cron 未装或未跑过)"}]
    age = _age_hours(os.path.getmtime(p), now)
    emoji, note = deadman_verdict(age, expected_interval_h=24 * 7)   # 周频预期
    return [{"name": "cron 复盘心跳", "status": emoji, "note": note}]


# --------------------------------------------------------------------------
# 编排
# --------------------------------------------------------------------------
def run_checks():
    now = datetime.now().timestamp()
    groups = {
        "数据源": check_data_sources(now),
        "cron 心跳": check_cron(now),
        "自动运行审计": check_runs(now),
        "数据新鲜度": check_files(now),
    }
    all_status = [c["status"] for g in groups.values() for c in g]
    return {"overall": overall_health(all_status), "groups": groups,
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


def render(res):
    print("=" * 60)
    print(f"运营健康体检 · {res['checked_at']} · 总体 {res['overall']}")
    print("=" * 60)
    for gname, checks in res["groups"].items():
        print(f"\n  【{gname}】")
        for c in checks:
            print(f"    {c['status']} {c['name']:<20} {c['note']}")
    print()
    if res["overall"] == "🔴":
        print("  🔴 存在故障项——需立即处理(数据源不可达/cron 停摆/数据过期)。")
    elif res["overall"] == "🟡":
        print("  🟡 有告警项——关注但非紧急。")
    else:
        print("  🟢 全部健康。")
    print(f"\n  ⚠️ 行情新鲜度在交易时段外天然偏旧(仅极端过期告警);监控是运营底线,非投资信号。")


def _notify_health(res):
    """总体非🟢时,把故障/告警项摘要推给 notify(桌面/webhook/日志)。"""
    try:
        import notify
    except Exception:  # noqa: BLE001
        return
    bad = [f"{c['status']}{c['name']}" for checks in res["groups"].values()
           for c in checks if c["status"] != "🟢"]
    level = "crit" if res["overall"] == "🔴" else "warn"
    notify.send(f"运营健康 {res['overall']}", "; ".join(bad) or "见 monitor check", level=level, min_level="warn")


def main():
    ap = argparse.ArgumentParser(description="运营监控与健康检查(心跳/数据源/新鲜度,零依赖)")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check", help="全面健康体检")
    c.add_argument("--json", action="store_true")
    c.add_argument("--notify", action="store_true",
                   help="总体非🟢时发结果通知(桌面/webhook/日志)——供 cron 无人值守告警")
    args = ap.parse_args()
    if args.cmd == "check":
        res = run_checks()
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            render(res)
        if getattr(args, "notify", False) and res["overall"] != "🟢":
            _notify_health(res)
        sys.exit(0 if res["overall"] != "🔴" else 1)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
