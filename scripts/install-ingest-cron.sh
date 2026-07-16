#!/usr/bin/env bash
# 安装数据底座定期摄取 + 健康监控 cron 任务（macOS / Linux）。幂等：重复运行不会重复添加。
# 每周一 06:45 跑数据底座摄取(ingest_universe run，在当日复盘前刷新事实源)；
# 工作日 07:15 跑运营健康体检(monitor check，让 dead-man's-switch 真正无人值守运行)。
#
# 诊断(全链路能力诊断评级)指出:cron 未跑摄取、monitor.py 不在 crontab、定时任务从未自主执行。
# 本脚本补上"数据自动刷新 + 健康自动体检"两块,是迈向 L5(无人值守自主运转)的第一步。
#
# 用法：
#   bash scripts/install-ingest-cron.sh          # 安装
#   bash scripts/install-ingest-cron.sh --remove  # 卸载
#   crontab -l                                    # 查看
#
# 注意：macOS 下 cron 需在「系统设置→隐私与安全性→完全磁盘访问权限」为 /usr/sbin/cron 授权，
#       否则可能无法读取项目目录。也可改用 launchd。
#       与 install-review-cron.sh 互不干扰(各用独立 TAG)。

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$(command -v python3 || echo /usr/bin/python3)"
ILOG="$ROOT/logs/ingest-cron.log"
MLOG="$ROOT/logs/monitor-cron.log"
TAG="# ai-berkshire-ingest"   # 用于幂等识别(独立于 review 的 TAG)

# 周一 06:45 摄取(在 07:30 market_review / 08:00 周复盘之前,让复盘用上新数据);失败即告警
INGEST="45 6 * * 1 cd '$ROOT' && { '$PY' tools/ingest_universe.py run >> '$ILOG' 2>&1 || '$PY' tools/notify.py send --title '数据摄取失败' --message 'ingest_universe run 非零退出,见 logs/ingest-cron.log' --level crit; } $TAG"
# 工作日 07:15 健康体检(--notify:非🟢时发桌面/webhook/日志告警;非零退出码=有🔴)
MONITOR="15 7 * * 1-5 cd '$ROOT' && '$PY' tools/monitor.py check --notify >> '$MLOG' 2>&1 $TAG"

current="$(crontab -l 2>/dev/null || true)"
cleaned="$(printf '%s\n' "$current" | grep -v "$TAG" || true)"

if [[ "${1:-}" == "--remove" ]]; then
  printf '%s\n' "$cleaned" | grep -v '^$' | crontab - || true
  echo "✅ 已移除 ai-berkshire 数据底座摄取/监控 cron 任务(review 任务不受影响)。"
  exit 0
fi

mkdir -p "$ROOT/logs"
{ printf '%s\n' "$cleaned"; echo "$INGEST"; echo "$MONITOR"; } | grep -v '^$' | crontab -
echo "✅ 已安装数据底座 cron："
echo "   · 每周一 06:45  数据底座摄取（ingest_universe run：主数据/公司行动/A股快照+财务/新鲜度清单）"
echo "   · 工作日 07:15  运营健康体检（monitor check：数据源/心跳/新鲜度，🔴 时非零退出码）"
echo "   · 日志 → ${ILOG} (摄取) / ${MLOG} (监控)"
echo ""
echo "查看：crontab -l    卸载：bash scripts/install-ingest-cron.sh --remove"
echo "⚠️ macOS 若 cron 不触发：为 /usr/sbin/cron 开启「完全磁盘访问权限」，或改用 launchd。"
