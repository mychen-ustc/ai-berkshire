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

DAILY="30 7 * * 1-5 cd '$ROOT' && '$PY' tools/market_review.py --md --html >> '$LOG' 2>&1 $TAG"
WEEKLY="0 8 * * 1 cd '$ROOT' && '$PY' tools/review.py --from-ledger data/portfolio/transactions.csv --weekly --md --html >> '$LOG' 2>&1 $TAG"
QUARTERLY="30 8 1 1,4,7,10 * cd '$ROOT' && '$PY' tools/review.py --from-ledger data/portfolio/transactions.csv --quarterly --md --html >> '$LOG' 2>&1 $TAG"

current="$(crontab -l 2>/dev/null || true)"
cleaned="$(printf '%s\n' "$current" | grep -v "$TAG" || true)"

if [[ "${1:-}" == "--remove" ]]; then
  printf '%s\n' "$cleaned" | crontab -
  echo "✅ 已移除 ai-berkshire 复盘 cron 任务。"
  exit 0
fi

mkdir -p "$ROOT/logs" "$ROOT/reports/private/reviews" "$ROOT/reports/private/market"
{ printf '%s\n' "$cleaned"; echo "$DAILY"; echo "$WEEKLY"; echo "$QUARTERLY"; } | grep -v '^$' | crontab -
echo "✅ 已安装复盘 cron："
echo "   · 工作日 07:30  每日市场全景盘点（market_review --md --html）"
echo "   · 每周一 08:00  组合周复盘（review --weekly --md --html）"
echo "   · 每季首日 08:30 季度复盘（review --quarterly --md --html）"
echo "   · 日志 → $LOG ; 报告 → reports/private/{reviews,market}/"
echo ""
echo "查看：crontab -l    卸载：bash scripts/install-review-cron.sh --remove"
echo "⚠️ macOS 若 cron 不触发：为 /usr/sbin/cron 开启「完全磁盘访问权限」，或改用 launchd。"
