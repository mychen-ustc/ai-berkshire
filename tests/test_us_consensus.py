"""us_consensus.py 回归测试（stdlib unittest，零依赖，纯 rating_stance）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import us_consensus as uc  # noqa: E402


class TestRatingStance(unittest.TestCase):
    def test_bullish(self):
        r = uc.rating_stance({"period": "2026-07-01", "strongBuy": 13, "buy": 23,
                              "hold": 16, "sell": 2, "strongSell": 0})
        # 看多 36 / 54 = 66.7%
        self.assertAlmostEqual(r["bullish_pct"], 66.7, places=1)
        self.assertEqual(r["stance"], "乐观")

    def test_cautious(self):
        r = uc.rating_stance({"strongBuy": 1, "buy": 1, "hold": 5, "sell": 3, "strongSell": 0})
        self.assertEqual(r["stance"], "谨慎")          # 看多 2/10 = 20% < 40%

    def test_neutral(self):
        r = uc.rating_stance({"strongBuy": 0, "buy": 5, "hold": 5, "sell": 0, "strongSell": 0})
        self.assertEqual(r["stance"], "中性")          # 5/10 = 50%

    def test_empty(self):
        r = uc.rating_stance({})
        self.assertIsNone(r["bullish_pct"])


if __name__ == "__main__":
    unittest.main()
