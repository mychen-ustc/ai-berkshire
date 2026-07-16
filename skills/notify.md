# 结果通知（桌面 / webhook / 日志）

无人值守时主动"喊你"：$ARGUMENTS。L5 最后一块（运营化）。

## 解决什么

诊断指出完整 L5 尚缺**结果通知**——cron/CI 出问题只写日志、不主动告警，"装了不转/转了出错"没人知道。`notify.py`（零依赖）把 monitor 的 🔴、cron 摄取失败、CI 失败**推到能看到的地方**：

| 通道 | 说明 |
|---|---|
| 桌面通知 | macOS `osascript` / Linux `notify-send`（本地，零配置） |
| webhook | 飞书/Slack incoming webhook（URL 存 `config/secrets.local.json` 的 `NOTIFY_WEBHOOK`，**gitignore**） |
| 告警日志 | 总是追加 `logs/alerts.log`；crit 另写 `logs/ALERT.flag`（供下次会话/体检拾取） |

`level`（info/warn/crit）门控；密钥/URL 经 `keys.get_key` 读环境变量或 gitignore 文件，**永不入库**。

## 执行流程
```bash
python3 tools/notify.py channels                    # 看当前可用通道
python3 tools/notify.py test                        # 各通道发测试
python3 tools/notify.py send --title "数据陈旧" --message "点时库72h未更新" --level crit
```
已接入的自动触发：
- **monitor**：`python3 tools/monitor.py check --notify` —— 总体非 🟢 时发（cron 每日跑）。
- **cron 摄取**：`ingest_universe run` 失败即 `notify send --level crit`（见 `install-ingest-cron.sh`）。
- **CI**：`.github/workflows/ci.yml` 失败时若配了 `NOTIFY_WEBHOOK` secret 则推 webhook；否则 GitHub 默认失败邮件兜底。

## 启用 webhook（可选）
在 `config/secrets.local.json`（已 gitignore）加：`{"NOTIFY_WEBHOOK": "https://open.feishu.cn/...", "NOTIFY_WEBHOOK_KIND": "feishu"}`（或 `slack`）。CI 则在仓库 Settings→Secrets 配 `NOTIFY_WEBHOOK`。

## 原则与诚实边界
- **桌面通知仅本机**：cron 在无人在场的清晨跑，桌面弹窗可能没人看——**靠 webhook/告警日志兜底**。
- **非保证送达**：webhook/桌面失败会记在结果里但不阻断；关键告警应多通道冗余。
- monitor 的 freshness 检查是**摄取失败的兜底探测**（数据变陈旧 → 🔴 → 通知），与 cron 失败直报互补。

## 相关
`monitor`(健康体检，--notify 触发) · `install-ingest-cron.sh`(定时+失败告警) · `.github/workflows/ci.yml`(CI 失败通知)
