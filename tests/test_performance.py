"""performance.py 回归测试（stdlib unittest，零依赖）。"""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import performance as perf  # noqa: E402


class TestXIRR(unittest.TestCase):
    def test_simple_10pct(self):
        flows = [(datetime(2025, 7, 11), -1000), (datetime(2026, 7, 11), 1100)]
        self.assertAlmostEqual(perf.xirr(flows), 0.10, places=4)

    def test_two_year_double(self):
        # -1000 今日, +1210 两年后 → 年化 ~10%
        flows = [(datetime(2024, 7, 11), -1000), (datetime(2026, 7, 11), 1210)]
        self.assertAlmostEqual(perf.xirr(flows), 0.10, places=3)

    def test_no_sign_change_returns_none(self):
        flows = [(datetime(2025, 1, 1), -1000), (datetime(2026, 1, 1), -500)]
        self.assertIsNone(perf.xirr(flows))


class TestTWR(unittest.TestCase):
    def test_single_interval_with_flow(self):
        navs = [(datetime(2025, 1, 1), 1000.0), (datetime(2026, 1, 1), 1600.0)]
        total, ann = perf.twr(navs, {datetime(2026, 1, 1): 500.0})
        self.assertAlmostEqual(total, 0.10, places=6)  # (1600-500)/1000-1

    def test_two_intervals_with_withdrawal(self):
        navs = [
            (datetime(2025, 1, 1), 1000.0),
            (datetime(2025, 7, 1), 1200.0),
            (datetime(2026, 1, 1), 1000.0),
        ]
        total, ann = perf.twr(navs, {datetime(2026, 1, 1): -300.0})
        # r1=0.2, r2=(1000-(-300))/1200-1=0.08333 → (1.2*1.08333)-1=0.30
        self.assertAlmostEqual(total, 0.30, places=4)

    def test_annualized_one_year(self):
        navs = [(datetime(2025, 7, 11), 1000.0), (datetime(2026, 7, 11), 1100.0)]
        total, ann = perf.twr(navs)
        self.assertAlmostEqual(total, 0.10, places=6)
        self.assertAlmostEqual(ann, 0.10, places=3)


if __name__ == "__main__":
    unittest.main()
