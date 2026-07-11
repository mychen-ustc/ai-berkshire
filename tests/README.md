# tests —— 核心工具回归测试

零外部依赖，纯 stdlib `unittest`。落地路线图 P0-4「测试与模型治理」的起点。

## 运行

```bash
# 全部
python3 -m unittest discover -s tests -p "test_*.py" -v

# 单个
python3 -m unittest tests.test_ledger -v
```

## 覆盖

| 文件 | 覆盖 |
|---|---|
| `test_financial_rigor.py` | calc 全程 Decimal（0.1+0.2=0.3 等 golden case）、科学计数法、幂、除零、**AST 白名单注入防护**、exact() 辅助 |
| `test_ledger.py` | 持仓/现金/已实现盈亏/成本基础重建、拆股、换汇、`--as-of` 历史重放 |

## 约定

- 新增工具/修 bug → 同时补 golden case，把当时的正确值固化，防回归。
- 测试必须零外部依赖（stdlib only），与项目工具一致。
