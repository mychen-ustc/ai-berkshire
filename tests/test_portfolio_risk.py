"""portfolio_risk.py 回归测试（stdlib unittest，零依赖）。"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import portfolio_risk as pr  # noqa: E402


class TestRiskMath(unittest.TestCase):
    def test_pct_returns(self):
        got = pr.pct_returns([100, 110, 99])
        self.assertEqual(len(got), 2)
        self.assertAlmostEqual(got[0], 0.1, places=9)
        self.assertAlmostEqual(got[1], -0.1, places=9)

    def test_max_drawdown(self):
        nav = pr.nav_from_returns([0.1, -0.2, 0.1])  # [1,1.1,0.88,0.968]
        self.assertAlmostEqual(pr.max_drawdown(nav), -0.2, places=10)

    def test_ann_vol(self):
        r = [0.01, -0.01, 0.01, -0.01]
        self.assertAlmostEqual(pr.ann_vol(r, 252), 0.01 * math.sqrt(252), places=9)

    def test_hhi_and_effective_n(self):
        self.assertAlmostEqual(pr.hhi([0.5, 0.5]), 0.5, places=10)
        self.assertAlmostEqual(1 / pr.hhi([0.5, 0.5]), 2.0, places=10)
        self.assertAlmostEqual(pr.hhi([0.47, 0.42, 0.11]), 0.4094, places=10)

    def test_beta_self_is_one(self):
        r = [0.02, -0.01, 0.03, 0.0, -0.02]
        self.assertAlmostEqual(pr.beta(r, r), 1.0, places=9)

    def test_correlation(self):
        a = [0.02, -0.01, 0.03, -0.02]
        self.assertAlmostEqual(pr.correlation(a, a), 1.0, places=9)
        self.assertAlmostEqual(pr.correlation(a, [-x for x in a]), -1.0, places=9)

    def test_cagr(self):
        nav = [1.0, 1.1, 1.21]
        self.assertAlmostEqual(pr.cagr(nav, 1, 2), 0.1, places=9)

    def test_parse_weights_normalizes(self):
        w = pr.parse_weights("A=2,B=2", ["A", "B", "C"])
        self.assertAlmostEqual(w["A"], 0.5)
        self.assertAlmostEqual(w["B"], 0.5)


if __name__ == "__main__":
    unittest.main()
