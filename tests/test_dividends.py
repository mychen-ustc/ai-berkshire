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


class TestAllocate(unittest.TestCase):
    def test_renorm_and_floor(self):
        # cash=100, 权重A=60/B=40(有价), C无价→排除; A价10→6股(6.0), B价7→5.71→floor 5.7142
        alloc = dv.allocate(100, {"A": 60, "B": 40, "C": 20}, {"A": 10, "B": 7})
        self.assertNotIn("C", alloc)                 # 无价被排除
        self.assertAlmostEqual(alloc["A"]["alloc"], 60.0, places=2)
        self.assertEqual(alloc["A"]["shares"], 6.0)  # 60/10=6
        # 不超额:部署 ≤ cash
        deployed = sum(a["shares"] * a["price"] for a in alloc.values())
        self.assertLessEqual(deployed, 100 + 1e-6)

    def test_whole_shares(self):
        alloc = dv.allocate(100, {"A": 100}, {"A": 30}, whole=True)
        self.assertEqual(alloc["A"]["shares"], 3.0)  # floor(100/30)=3
