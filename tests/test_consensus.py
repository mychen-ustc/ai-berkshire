"""consensus.py 回归测试（stdlib unittest，零依赖，纯 _build）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import consensus as cs  # noqa: E402

ROW = {
    "SECURITY_NAME_ABBR": "测试股", "INDUSTRY_BOARD": "半导体",
    "RATING_ORG_NUM": 10, "RATING_BUY_NUM": 8, "RATING_ADD_NUM": 2,
    "RATING_NEUTRAL_NUM": 0, "RATING_REDUCE_NUM": 0, "RATING_SALE_NUM": 0,
    "YEAR1": 2025, "YEAR_MARK1": "A", "EPS1": 1.0,
    "YEAR2": 2026, "YEAR_MARK2": "E", "EPS2": 2.0,
    "YEAR3": 2027, "YEAR_MARK3": "E", "EPS3": 3.0,
    "YEAR4": 2028, "YEAR_MARK4": "E", "EPS4": 4.0,
}


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.c = cs._build(ROW, price=40.0, symbol="000000.SZ")

    def test_rating(self):
        self.assertAlmostEqual(self.c["bullish_pct"], 100.0)
        self.assertEqual(self.c["stance"], "乐观")

    def test_eps_series_and_growth(self):
        self.assertEqual(len(self.c["eps_series"]), 4)
        self.assertAlmostEqual(self.c["eps_growth_pct"][0], 100.0, places=1)  # 2→1
        self.assertAlmostEqual(self.c["eps_growth_pct"][1], 50.0, places=1)

    def test_eps_cagr(self):
        # (4/1)^(1/3)-1 = 58.74%
        self.assertAlmostEqual(self.c["eps_cagr_pct"], 58.7, places=1)

    def test_forward_pe_and_peg(self):
        self.assertAlmostEqual(self.c["fwd_pe"], 20.0, places=1)   # 40 / 2.0(首个E)
        self.assertAlmostEqual(self.c["peg"], 0.34, places=2)      # 20 / 58.74

    def test_cautious_stance(self):
        row = dict(ROW, RATING_BUY_NUM=2, RATING_ADD_NUM=1, RATING_NEUTRAL_NUM=7)
        c = cs._build(row, price=None, symbol="x")
        self.assertEqual(c["stance"], "谨慎")   # 看多 3/10 = 30% < 50%
        self.assertIsNone(c["fwd_pe"])           # 无现价→无前瞻PE


if __name__ == "__main__":
    unittest.main()
