"""comps.py 回归测试（stdlib unittest，零依赖，纯 cross_section）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import comps as cp  # noqa: E402


class TestCrossSection(unittest.TestCase):
    def test_median_and_relative(self):
        rows = [{"symbol": "A", "pe": 10.0, "pb": 1.0}, {"symbol": "B", "pe": 20.0, "pb": 2.0},
                {"symbol": "C", "pe": 30.0, "pb": 3.0}]
        med_pe, med_pb = cp.cross_section(rows)
        self.assertEqual(med_pe, 20.0)
        self.assertEqual(med_pb, 2.0)
        self.assertAlmostEqual(rows[0]["pe_vs_median_pct"], -50.0, places=1)   # 10 vs 20
        self.assertAlmostEqual(rows[2]["pe_vs_median_pct"], 50.0, places=1)    # 30 vs 20

    def test_negative_pe_excluded_from_median(self):
        rows = [{"symbol": "A", "pe": 10.0}, {"symbol": "B", "pe": 20.0},
                {"symbol": "Loss", "pe": -5.0}]                                 # 亏损剔除
        med_pe, _ = cp.cross_section(rows)
        self.assertEqual(med_pe, 15.0)                                          # median(10,20)
        self.assertNotIn("pe_vs_median_pct", rows[2])                          # 负 PE 不标注

    def test_empty(self):
        med_pe, med_pb = cp.cross_section([{"symbol": "A", "error": "x"}])
        self.assertIsNone(med_pe)


if __name__ == "__main__":
    unittest.main()
