#!/usr/bin/env python3
"""可重放审计（自动运行留痕，零外部依赖）——L5 收尾:任何一次自动运行都可追溯/可复现。

诊断(全链路能力诊断评级)指出:完整 L5 尚缺**可重放审计**——cron/CI 跑过就跑过了,没有
"哪次、何时、在哪个代码版本、结果如何"的不可变记录。本工具补这块:每次自动运行(cron 摄取/
monitor 体检/CI)都生成 **run-id + 审计记录**(时间/触发源/命令/git SHA/退出码/耗时),追加到
不可变审计账本 data/run_audit.jsonl。

可复现语义(诚实):
  · **代码可追溯** —— 记录 git commit SHA + 命令,任何一次运行都能 `git checkout <SHA>` 复跑;
  · **确定性可精确复现** —— 纯函数工具 + 固定输入,配合 lineage 签名可字节级复现;
  · **活数据摄取不可逐字节复现**(源在变),但口径/版本/时点可追溯。
与 lineage(数据签名可复现)互补:lineage 管"数据怎么算的"、run_audit 管"哪次运行、跑没跑、成没成"。

用法：
  # 包裹一条命令并留痕(cron/CI 用):记录 run-id/SHA/耗时/退出码,透传退出码
  python3 tools/run_audit.py wrap --trigger cron-ingest -- python3 tools/ingest_universe.py run
  # 手工登记一次运行(CI 里用 GITHUB_* 环境)
  python3 tools/run_audit.py record --trigger ci --run-id 123 --git-sha abc --command "ci gate" --status success
  python3 tools/run_audit.py log [--trigger cron-ingest] [--limit 10]   # 近期运行
  python3 tools/run_audit.py trace <run-id>                             # 单次详情 + 复跑提示
  python3 tools/run_audit.py summary                                    # 各触发源最近运行 + 失败连击(供 monitor)
"""
import argparse
import json
import os
import socket
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "data", "run_audit.jsonl")


# --------------------------------------------------------------------------
# 纯函数（可测）
# --------------------------------------------------------------------------
def status_of(exit_code):
    return "success" if exit_code == 0 else "failed"


def make_run_id(trigger, ts_compact, git_sha):
    """可读且唯一的 run-id：{触发源}-{时间戳}-{SHA7}。纯函数(时间/ SHA 由调用方传入)。"""
    sha7 = (git_sha or "nogit")[:7]
    return f"{trigger}-{ts_compact}-{sha7}"


def build_record(run_id, trigger, command, git_sha, git_dirty,
                 started_at, finished_at, duration_s, exit_code, python_version, host, extra=None):
    """一次运行的不可变审计记录。纯函数。"""
    rec = {
        "run_id": run_id, "trigger": trigger, "command": command,
        "git_sha": git_sha, "git_dirty": git_dirty,
        "started_at": started_at, "finished_at": finished_at, "duration_s": duration_s,
        "exit_code": exit_code, "status": status_of(exit_code),
        "python": python_version, "host": host,
    }
    if extra:
        rec["extra"] = extra
    return rec


def replay_hint(record):
    """如何复跑这次运行。纯函数。"""
    sha = record.get("git_sha") or "?"
    dirty = "（注意:当时工作区有未提交改动，非纯净复现）" if record.get("git_dirty") else ""
    return f"git checkout {sha} && {record.get('command', '?')}{dirty}"


def failure_streak(records_for_trigger):
    """某触发源按时间升序的记录 → 末尾起连续失败次数。纯函数。"""
    streak = 0
    for r in reversed(records_for_trigger):
        if r.get("status") == "failed":
            streak += 1
        else:
            break
    return streak


def summarize(records):
    """→ 各触发源:最近一次(时间/状态) + 总次数 + 当前失败连击。纯函数。"""
    by_trig = {}
    for r in records:
        by_trig.setdefault(r.get("trigger", "?"), []).append(r)
    out = {}
    for trig, rs in by_trig.items():
        rs_sorted = sorted(rs, key=lambda x: x.get("started_at", ""))
        last = rs_sorted[-1]
        out[trig] = {
            "last_run": last.get("started_at"), "last_status": last.get("status"),
            "last_run_id": last.get("run_id"), "total": len(rs_sorted),
            "failure_streak": failure_streak(rs_sorted),
        }
    return out


# --------------------------------------------------------------------------
# IO
# --------------------------------------------------------------------------
def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _ts_compact():
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def git_sha():
    try:
        return subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def git_dirty():
    try:
        out = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return bool(out)
    except Exception:  # noqa: BLE001
        return None


def load(path=STORE):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def append(rec, path=STORE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
def cmd_wrap(args):
    cmd = list(args.command)
    if cmd and cmd[0] == "--":            # argparse.REMAINDER 会保留分隔符 --
        cmd = cmd[1:]
    if not cmd:
        raise SystemExit("wrap 需在 -- 之后给出要执行的命令")
    args.command = cmd
    sha, dirty = git_sha(), git_dirty()
    started = _now_iso()
    t0 = datetime.now()
    run_id = make_run_id(args.trigger, _ts_compact(), sha)
    # 执行被包裹命令(透传 stdout/stderr)
    proc = subprocess.run(args.command)
    dur = round((datetime.now() - t0).total_seconds(), 3)
    rec = build_record(run_id, args.trigger, " ".join(args.command), sha, dirty,
                       started, _now_iso(), dur, proc.returncode,
                       sys.version.split()[0], socket.gethostname(),
                       extra={"note": args.note} if args.note else None)
    append(rec, args.path)
    print(f"[run_audit] {run_id} · {rec['status']} · {dur}s · exit {proc.returncode}", file=sys.stderr)
    sys.exit(proc.returncode)                        # 透传退出码(cron 的 || notify 仍生效)


def cmd_record(args):
    sha = args.git_sha or git_sha()
    ts = _ts_compact()
    run_id = args.run_id or make_run_id(args.trigger, ts, sha)
    exit_code = args.exit_code if args.exit_code is not None else (0 if args.status == "success" else 1)
    now = _now_iso()
    rec = build_record(run_id, args.trigger, args.command or "", sha, git_dirty(),
                       now, now, args.duration or 0.0, exit_code,
                       sys.version.split()[0], args.host or socket.gethostname(),
                       extra={"note": args.note} if args.note else None)
    append(rec, args.path)
    print(f"✅ 已登记运行 {run_id} · {rec['status']}")


def cmd_log(args):
    recs = load(args.path)
    if args.trigger:
        recs = [r for r in recs if r.get("trigger") == args.trigger]
    recs = sorted(recs, key=lambda x: x.get("started_at", ""))[-args.limit:]
    print(f"运行审计 · {len(recs)} 条" + (f"（{args.trigger}）" if args.trigger else ""))
    for r in recs:
        mark = "✅" if r["status"] == "success" else "🔴"
        print(f"  {mark} {r['started_at']} · {r['trigger']:<13} · {r.get('duration_s',0):>6.1f}s · "
              f"{(r.get('git_sha') or 'nogit')[:7]} · {r['run_id']}")


def cmd_trace(args):
    rec = next((r for r in load(args.path) if r.get("run_id") == args.run_id), None)
    if not rec:
        raise SystemExit(f"未找到 run-id：{args.run_id}")
    print(json.dumps(rec, ensure_ascii=False, indent=2) if args.json else
          "\n".join([
              "=" * 60, f"运行审计 · {rec['run_id']}", "=" * 60,
              f"  触发源  : {rec['trigger']}",
              f"  时间    : {rec['started_at']} → {rec['finished_at']}（{rec['duration_s']}s）",
              f"  结果    : {rec['status']}（exit {rec['exit_code']}）",
              f"  代码版本: {rec.get('git_sha')}" + ("（工作区有未提交改动）" if rec.get("git_dirty") else "（纯净）"),
              f"  命令    : {rec['command']}",
              f"  主机/Py : {rec.get('host')} / {rec.get('python')}",
              f"\n  ↻ 复跑  : {replay_hint(rec)}",
          ]))


def cmd_summary(args):
    s = summarize(load(args.path))
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return
    print("=" * 64)
    print("自动运行审计汇总（各触发源最近运行 + 失败连击）")
    print("=" * 64)
    if not s:
        print("  （暂无运行记录——cron/CI 首次跑过后即有）")
        return
    for trig, v in sorted(s.items()):
        mark = "🔴" if v["failure_streak"] >= 2 else ("🟡" if v["last_status"] == "failed" else "✅")
        print(f"  {mark} {trig:<14} 最近 {v['last_run']}（{v['last_status']}）· 共 {v['total']} 次"
              + (f" · ⚠️ 连续失败 {v['failure_streak']} 次" if v["failure_streak"] else ""))


def main():
    ap = argparse.ArgumentParser(description="可重放审计:自动运行留痕(run-id/SHA/结果,零依赖)")
    ap.add_argument("--path", default=STORE)
    sub = ap.add_subparsers(dest="cmd")

    w = sub.add_parser("wrap", help="包裹命令并留痕(透传退出码)")
    w.add_argument("--trigger", required=True, help="触发源:cron-ingest/cron-monitor/ci/manual")
    w.add_argument("--note", default="")
    w.add_argument("command", nargs=argparse.REMAINDER, help="-- 之后为要执行的命令")

    rc = sub.add_parser("record", help="手工登记一次运行(CI 等)")
    rc.add_argument("--trigger", required=True)
    rc.add_argument("--run-id", dest="run_id")
    rc.add_argument("--git-sha", dest="git_sha")
    rc.add_argument("--command", default="")
    rc.add_argument("--status", choices=["success", "failed"], default="success")
    rc.add_argument("--exit-code", dest="exit_code", type=int)
    rc.add_argument("--duration", type=float)
    rc.add_argument("--host")
    rc.add_argument("--note", default="")

    lg = sub.add_parser("log", help="近期运行")
    lg.add_argument("--trigger")
    lg.add_argument("--limit", type=int, default=15)

    tr = sub.add_parser("trace", help="单次详情 + 复跑提示")
    tr.add_argument("run_id")
    tr.add_argument("--json", action="store_true")

    sm = sub.add_parser("summary", help="各触发源最近运行 + 失败连击")
    sm.add_argument("--json", action="store_true")

    args = ap.parse_args()
    {"wrap": cmd_wrap, "record": cmd_record, "log": cmd_log,
     "trace": cmd_trace, "summary": cmd_summary}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
