#!/usr/bin/env bash
# 安装定期复盘 cron 任务（macOS / Linux）。幂等：重复运行不会重复添加。
# 每周一 08:00 跑周复盘 + 出 HTML；每季度首日 08:30 跑季度复盘。
# 复盘结果追加到 logs/review-cron.log，HTML 存 reports/private/reviews/。
#
# 用法：
#   bash scripts/install-review-cron.sh          # 安装
#   bash scripts/install-review-cron.sh --remove  # 卸载
#   crontab -l                                    # 查看
#
# 注意：macOS 下 cron 需在「系统设置→隐私与安全性→完全磁盘访问权限」为 /usr/sbin/cron 授权，
#       否则可能无法读取项目目录。也可改用 launchd（见文末提示）。

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$(command -v python3 || echo /usr/bin/python3)"
LOG="$ROOT/logs/review-cron.log"
TAG="# ai-berkshire-review"   # 用于幂等识别

WEEKLY="0 8 * * 1 cd '$ROOT' && '$PY' tools/review.py --from-ledger data/portfolio/transactions.csv --weekly --html >> '$LOG' 2>&1 $TAG"
QUARTERLY="30 8 1 1,4,7,10 * cd '$ROOT' && '$PY' tools/review.py --from-ledger data/portfolio/transactions.csv --quarterly --html >> '$LOG' 2>&1 $TAG"

current="$(crontab -l 2>/dev/null || true)"
cleaned="$(printf '%s\n' "$current" | grep -v "$TAG" || true)"

if [[ "${1:-}" == "--remove" ]]; then
  printf '%s\n' "$cleaned" | crontab -
  echo "✅ 已移除 ai-berkshire 复盘 cron 任务。"
  exit 0
fi

mkdir -p "$ROOT/logs" "$ROOT/reports/private/reviews"
{ printf '%s\n' "$cleaned"; echo "$WEEKLY"; echo "$QUARTERLY"; } | grep -v '^$' | crontab -
echo "✅ 已安装复盘 cron："
echo "   · 每周一 08:00  周复盘（--weekly --html）"
echo "   · 每季首日 08:30 季度复盘（--quarterly --html）"
echo "   · 日志 → $LOG ; 报告 → reports/private/reviews/"
echo ""
echo "查看：crontab -l    卸载：bash scripts/install-review-cron.sh --remove"
echo "⚠️ macOS 若 cron 不触发：为 /usr/sbin/cron 开启「完全磁盘访问权限」，或改用 launchd。"
