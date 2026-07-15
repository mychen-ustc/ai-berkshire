"""dividends.py 回归测试（分红入账纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import dividends as dv  # noqa: E402


class TestFilterCalendar(unittest.TestCase):
    def test_filter_and_sort(self):
        divs = [("2026-06-15", 0.53), ("2025-01-01", 0.48), ("2026-03-13", 0.51)]
        r = dv.filter_calendar(divs, "2026-01-01", "2026-07-01")
        self.assertEqual(r, [("2026-03-13", 0.51), ("2026-06-15", 0.53)])   # 排除2025,排序

    def test_boundary_inclusive(self):
        divs = [("2026-01-01", 1.0), ("2026-12-31", 2.0)]
        self.assertEqual(len(dv.filter_calendar(divs, "2026-01-01", "2026-12-31")), 2)


class TestDivCash(unittest.TestCase):
    def test_gross(self):
        self.assertAlmostEqual(dv.div_cash(35, 0.53), 18.55, places=6)

    def test_with_withholding_tax(self):
        # 100股 × $0.5 × (1-0.3) = $35 净
        self.assertAlmostEqual(dv.div_cash(100, 0.5, tax=0.3), 35.0, places=6)

    def test_zero_shares(self):
        self.assertEqual(dv.div_cash(0, 0.53), 0.0)


if __name__ == "__main__":
    unittest.main()
