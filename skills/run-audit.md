# 可重放审计（自动运行留痕）

任何一次自动运行都可追溯/复现：$ARGUMENTS。L5 收尾（运营化）。

## 解决什么

诊断指出完整 L5 尚缺**可重放审计**——cron/CI 跑过就跑过了，没有"哪次、何时、在哪个代码版本、结果如何"的不可变记录。`run_audit.py`（零依赖）补这块：每次自动运行都生成 **run-id + 审计记录**（时间/触发源/命令/git SHA/git 是否 dirty/退出码/耗时）→ 追加到不可变账本 `data/run_audit.jsonl`（gitignore）。

**可复现语义（诚实）**：
- **代码可追溯**：记录 git commit SHA + 命令，任何一次都能 `git checkout <SHA>` 复跑。
- **确定性可精确复现**：纯函数工具 + 固定输入，配合 `lineage` 签名可字节级复现。
- **活数据摄取不可逐字节复现**（源在变），但口径/版本/时点可追溯。

与 `lineage`（数据签名可复现）互补：lineage 管"数据怎么算的"，run_audit 管"哪次运行、跑没跑、成没成"。

## 执行流程
```bash
# 包裹命令并留痕(cron 用,透传退出码 → 后续 || notify 仍生效)
python3 tools/run_audit.py wrap --trigger cron-ingest -- python3 tools/ingest_universe.py run
python3 tools/run_audit.py log [--trigger cron-ingest] [--limit 10]   # 近期运行
python3 tools/run_audit.py trace <run-id>                             # 单次详情 + 复跑提示
python3 tools/run_audit.py summary                                    # 各触发源最近运行 + 失败连击
```
**已接入**：
- **cron**：`install-ingest-cron.sh` 用 `wrap` 包裹 ingest / monitor（run-id/SHA/结果落盘）。
- **CI**：`ci.yml` 用 `record`（run-id=GITHUB_RUN_ID + SHA + job 状态）+ 复跑提示写入运行摘要页。
- **monitor**：`check_runs` 读 run_audit summary，作**精确 dead-man's-switch**——某触发源太久没跑或**连续失败≥2 次**即 🔴（比日志 mtime 精确）。

## 原则与诚实边界
- **run_audit 记"执行"、lineage 记"数据"、monitor 读它做健康**——三者构成 L5 的可运营闭环。
- 活数据摄取只可追溯不可逐字节复现；确定性计算才能字节级复现。
- 同触发源同一秒运行的 run-id 会撞（实际 cron 周频/CI 用 GITHUB_RUN_ID，不会发生）。

## 相关
`lineage`(数据签名可复现) · `monitor`(check_runs 读审计做 dead-man's-switch) · `notify`(失败告警) · `install-ingest-cron.sh` · `ci.yml`
