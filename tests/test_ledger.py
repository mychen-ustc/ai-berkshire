"""ledger.py 回归测试（stdlib unittest，零依赖）。

用合成示例账本验证持仓重建的正确性：期末持仓、现金、已实现盈亏、
成本基础、拆股、换汇、以及 --as-of 历史重放。运行：
    python3 -m unittest discover -s tests
"""
import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import ledger  # noqa: E402

EXAMPLE = os.path.join(
    os.path.dirname(__file__), "..", "data", "portfolio", "transactions.example.csv"
)
CENT = Decimal("0.01")


class TestLedgerRebuild(unittest.TestCase):
    def setUp(self):
        self.rows = ledger.load_ledger(EXAMPLE)

    def test_final_quantities(self):
        pos, cash, realized, warn = ledger.rebuild(self.rows)
        self.assertEqual(pos["0700.HK"].qty, Decimal("600"))   # 700 建仓 - 100 减仓
        self.assertEqual(pos["9988.HK"].qty, Decimal("1000"))  # 500 → 1:2 拆股
        self.assertEqual(pos["PDD"].qty, Decimal("250"))

    def test_cash_by_currency(self):
        pos, cash, realized, warn = ledger.rebuild(self.rows)
        # HKD: 600000 -234000(FX) -315050(买0700) -40040(买9988) +1500(息) +47970(卖0700)
        self.assertEqual(cash["HKD"], Decimal("60380"))
        # USD: +30000(FX) -25005(买PDD)
        self.assertEqual(cash["USD"], Decimal("4995"))

    def test_realized_pnl(self):
        pos, cash, realized, warn = ledger.rebuild(self.rows)
        # 卖0700 100@480, 卖时均价 315050/700, 减手续费30
        self.assertEqual(realized.quantize(CENT), Decimal("2962.86"))

    def test_cost_basis(self):
        pos, cash, realized, warn = ledger.rebuild(self.rows)
        self.assertEqual(pos["0700.HK"].cost_basis.quantize(CENT), Decimal("270042.86"))
        self.assertEqual(pos["9988.HK"].cost_basis, Decimal("40040"))  # 拆股不改成本
        self.assertEqual(pos["PDD"].cost_basis, Decimal("25005"))

    def test_dividends_recorded(self):
        pos, cash, realized, warn = ledger.rebuild(self.rows)
        self.assertEqual(pos["0700.HK"].dividends, Decimal("1500"))

    def test_no_warnings(self):
        pos, cash, realized, warn = ledger.rebuild(self.rows)
        self.assertEqual(warn, [])

    def test_as_of_replay_before_split_and_sell(self):
        pos, cash, realized, warn = ledger.rebuild(self.rows, as_of="2026-02-01")
        self.assertEqual(pos["0700.HK"].qty, Decimal("700"))   # 减仓(05-10)之前
        self.assertEqual(pos["9988.HK"].qty, Decimal("500"))   # 拆股(04-15)之前
        self.assertEqual(realized, Decimal("0"))               # 尚无卖出

    def test_split_preserves_cost(self):
        # 拆股后股数×2、成本不变 → 均价减半
        pos, _, _, _ = ledger.rebuild(self.rows)
        p = pos["9988.HK"]
        self.assertEqual(p.qty, Decimal("1000"))
        self.assertEqual(p.avg_cost, Decimal("40.04"))  # 原 80.08 → /2


if __name__ == "__main__":
    unittest.main()
