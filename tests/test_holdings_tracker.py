"""holdings_tracker.py 回归测试（stdlib unittest，零依赖，纯 build_*）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import holdings_tracker as ht  # noqa: E402


class TestDragon(unittest.TestCase):
    ROWS = [
        {"TRADE_DATE": "2026-01-05 00:00:00", "EXPLAIN": "4家机构买入，成功率53%",
         "BILLBOARD_DEAL_AMT": 2.13e9, "DEAL_AMOUNT_RATIO": 43.36, "CHANGE_RATE": 10, "CLOSE_PRICE": 195},
        {"TRADE_DATE": "2025-12-20 00:00:00", "EXPLAIN": "买一主买，成功率55%",
         "BILLBOARD_DEAL_AMT": 1e8, "DEAL_AMOUNT_RATIO": 20.0, "CHANGE_RATE": -3.5, "CLOSE_PRICE": 180},
    ]

    def test_build_dragon(self):
        d = ht.build_dragon(self.ROWS, "300750.SZ")
        self.assertEqual(d["n"], 2)
        self.assertEqual(d["inst_appearances"], 1)              # 仅第一条含"机构"
        self.assertAlmostEqual(d["records"][0]["deal_amt_yi"], 21.3, places=1)
        self.assertEqual(d["records"][0]["date"], "2026-01-05")
        self.assertAlmostEqual(d["records"][0]["deal_ratio_pct"], 43.36, places=2)


class TestHolder(unittest.TestCase):
    def test_concentration(self):
        rows = [{"HOLDER_NUM": 100000, "PRE_HOLDER_NUM": 120000, "HOLDER_NUM_CHANGE": -20000,
                 "HOLDER_NUM_RATIO": -16.67, "END_DATE": "2025-09-30 00:00:00",
                 "PRE_END_DATE": "2025-06-30 00:00:00"}]
        h = ht.build_holder(rows, "300750.SZ")
        self.assertTrue(h["available"])
        self.assertAlmostEqual(h["change_pct"], -16.67, places=2)
        self.assertIn("筹码集中", h["signal"])

    def test_dispersion(self):
        rows = [{"HOLDER_NUM": 120000, "PRE_HOLDER_NUM": 100000, "HOLDER_NUM_CHANGE": 20000,
                 "HOLDER_NUM_RATIO": 20.0, "END_DATE": "2025-09-30 00:00:00"}]
        self.assertIn("筹码分散", ht.build_holder(rows, "x")["signal"])

    def test_empty(self):
        self.assertFalse(ht.build_holder([], "x")["available"])


if __name__ == "__main__":
    unittest.main()
