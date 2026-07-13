# 统一 Watchlist 状态机

管理研究流水线：$ARGUMENTS。P3 运营骨架。

## 解决什么

把散落的候选/召回/持仓合并为一个入口 + 一条状态流水线，每标的带论点/负责人/催化剂/红线/复审日，让"研究—决策—持有—退出"可持续运转、可复盘。用 `tools/watchlist.py`（零依赖，存 `data/watchlist.pipeline.json`，已 gitignore）。

## 状态流水线
`发现 → 初筛 → 深研 → 候选 → 持有 → 退出 → 归档`

## 执行流程
```bash
python3 tools/watchlist.py add 603986 --name 兆易创新 --thesis "存储质量龙头" --review 2026-08-01
python3 tools/watchlist.py promote 603986      # 前进一步（demote 后退）
python3 tools/watchlist.py set 603986 holding   # 直接置态（跳级/回退会标注）
python3 tools/watchlist.py catalyst 603986 "2026-07-30 业绩预告"
python3 tools/watchlist.py list --state candidate
python3 tools/watchlist.py due --as-of 2026-07-13   # 到期需复审
```

## 与其它工具的闭环
`portfolio-scan`(体检结论回填状态) · `catalysts`(从 next_catalyst 汇总日历) · `decision-journal`(状态迁移记录论点) · `thesis-tracker`(持有期跟踪)

## 原则
- 状态迁移留 history、跳级/回退显式标注——过程可复盘、不可悄悄改。
- 复审日到期必须复审(due)，避免"买入即遗忘"。
- 个人流水线只存本地，不入库。
