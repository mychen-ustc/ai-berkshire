#!/usr/bin/env python3
"""结果通知（零外部依赖）——L5 最后一块：无人值守时主动"喊你"。

诊断(全链路能力诊断评级)指出：完整 L5 尚缺**结果通知**——cron/CI 出问题只写日志、不主动告警,
"装了不转/转了出错"没人知道。本工具补这块:把 monitor 的🔴、cron 摄取失败、CI 失败**推到能看到的地方**。

多通道(自动探测,可用即发):
  ① 桌面通知  —— macOS osascript / Linux notify-send(本地,零配置)
  ② webhook   —— 飞书/Slack incoming webhook(URL 存 config/secrets.local.json 的 NOTIFY_WEBHOOK,gitignore)
  ③ 告警日志  —— 总是追加 logs/alerts.log;crit 另写 logs/ALERT.flag(供下次会话/体检拾取)

密钥/URL 永不入库(经 keys.get_key 读环境变量或 gitignore 的 secrets.local.json)。

用法：
  python3 tools/notify.py test                                   # 各通道发一条测试
  python3 tools/notify.py send --title "数据陈旧" --message "点时库72h未更新" --level crit
  python3 tools/notify.py channels                               # 看当前可用通道
  # 常与 monitor 联动:  python3 tools/monitor.py check --notify
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keys  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALERTS_LOG = os.path.join(ROOT, "logs", "alerts.log")
ALERT_FLAG = os.path.join(ROOT, "logs", "ALERT.flag")
_LEVELS = {"info": 0, "warn": 1, "crit": 2}


# --------------------------------------------------------------------------
# 纯函数（可测）
# --------------------------------------------------------------------------
def level_rank(level):
    return _LEVELS.get(level, 0)


def should_notify(level, min_level):
    """level 达到/超过 min_level 才通知。纯函数。"""
    return level_rank(level) >= level_rank(min_level)


def format_line(title, message, level, ts="?"):
    """告警日志/桌面单行文案。纯函数。"""
    tag = {"crit": "🔴 CRIT", "warn": "🟡 WARN", "info": "ℹ️ INFO"}.get(level, level)
    return f"[{ts}] {tag} · {title} · {message}"


def webhook_payload(kind, title, message, level):
    """→ 飞书/Slack incoming webhook 的 JSON body。纯函数。"""
    tag = {"crit": "🔴", "warn": "🟡", "info": "ℹ️"}.get(level, "")
    text = f"{tag} [ai-berkshire] {title}\n{message}"
    if kind == "slack":
        return {"text": text}
    # 默认飞书 text 消息
    return {"msg_type": "text", "content": {"text": text}}


def resolve_channels(has_webhook, platform, has_desktop_cmd):
    """当前可用通道列表(日志总在)。纯函数。"""
    ch = ["log"]
    if has_desktop_cmd and platform in ("darwin", "linux"):
        ch.append("desktop")
    if has_webhook:
        ch.append("webhook")
    return ch


# --------------------------------------------------------------------------
# IO
# --------------------------------------------------------------------------
def _now():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _desktop_cmd():
    """返回 (可执行, 平台) —— macOS osascript / Linux notify-send。"""
    import shutil
    if sys.platform == "darwin" and shutil.which("osascript"):
        return "osascript", "darwin"
    if sys.platform.startswith("linux") and shutil.which("notify-send"):
        return "notify-send", "linux"
    return None, sys.platform


def notify_desktop(title, message):
    cmd, plat = _desktop_cmd()
    if not cmd:
        return False
    t = title.replace('"', "'")
    m = message.replace('"', "'")
    try:
        if plat == "darwin":
            subprocess.run(["osascript", "-e",
                            f'display notification "{m}" with title "ai-berkshire" subtitle "{t}"'],
                           capture_output=True, timeout=10)
        else:
            subprocess.run(["notify-send", f"ai-berkshire · {t}", m], capture_output=True, timeout=10)
        return True
    except Exception:  # noqa: BLE001
        return False


def notify_webhook(url, kind, title, message, level):
    payload = json.dumps(webhook_payload(kind, title, message, level), ensure_ascii=False)
    try:
        r = subprocess.run(["curl", "-s", "-m", "10", "-X", "POST",
                            "-H", "Content-Type: application/json", "-d", payload, url],
                           capture_output=True, text=True, timeout=15)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def log_alert(title, message, level):
    os.makedirs(os.path.dirname(ALERTS_LOG), exist_ok=True)
    line = format_line(title, message, level, _now())
    with open(ALERTS_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    if level == "crit":
        with open(ALERT_FLAG, "w", encoding="utf-8") as f:
            f.write(line + "\n")
    return True


def send(title, message, level="warn", min_level="warn"):
    """按可用通道发通知。→ {channel: ok}。日志总发;桌面/ webhook 视可用性。"""
    if not should_notify(level, min_level):
        return {"skipped": True, "reason": f"level {level} < min {min_level}"}
    webhook_url = keys.get_key("NOTIFY_WEBHOOK")
    webhook_kind = (keys.get_key("NOTIFY_WEBHOOK_KIND") or "feishu").lower()
    cmd, _ = _desktop_cmd()
    results = {"log": log_alert(title, message, level)}
    if cmd:
        results["desktop"] = notify_desktop(title, message)
    if webhook_url:
        results["webhook"] = notify_webhook(webhook_url, webhook_kind, title, message, level)
    return results


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def cmd_send(args):
    res = send(args.title, args.message, args.level, args.min_level)
    print(json.dumps(res, ensure_ascii=False) if args.json
          else "通知已发: " + ", ".join(f"{k}={'✅' if v else '❌'}" for k, v in res.items()))


def cmd_test(args):
    res = send("通知自测", "这是一条 ai-berkshire 结果通知测试(收到即通道畅通)。", "warn", "info")
    print("测试通知结果: " + ", ".join(f"{k}={'✅' if v else '❌'}" for k, v in res.items()))


def cmd_channels(args):
    webhook = bool(keys.get_key("NOTIFY_WEBHOOK"))
    cmd, plat = _desktop_cmd()
    ch = resolve_channels(webhook, plat if cmd else sys.platform, bool(cmd))
    print(f"平台 {sys.platform} · 可用通道: {', '.join(ch)}")
    print(f"  桌面: {'✅ ' + cmd if cmd else '❌(无 osascript/notify-send)'}")
    print(f"  webhook: {'✅ 已配置 NOTIFY_WEBHOOK' if webhook else '❌ 未配置(写 config/secrets.local.json 的 NOTIFY_WEBHOOK 启用飞书/Slack)'}")
    print(f"  日志: ✅ {ALERTS_LOG}")


def main():
    ap = argparse.ArgumentParser(description="结果通知(桌面/webhook/日志,零依赖)")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("send", help="发一条通知")
    s.add_argument("--title", required=True)
    s.add_argument("--message", default="")
    s.add_argument("--level", default="warn", choices=["info", "warn", "crit"])
    s.add_argument("--min-level", dest="min_level", default="info", choices=["info", "warn", "crit"])
    s.add_argument("--json", action="store_true")
    sub.add_parser("test", help="各通道发测试通知")
    sub.add_parser("channels", help="列出当前可用通道")
    args = ap.parse_args()
    {"send": cmd_send, "test": cmd_test, "channels": cmd_channels}.get(
        args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
