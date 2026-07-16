"""valuation_cross_check.py 回归测试（估值交叉校验纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import valuation_cross_check as vx  # noqa: E402


class TestImpliedFromMultiple(unittest.TestCase):
    def test_pe_times_eps(self):
        self.assertAlmostEqual(vx.implied_from_multiple(22, 6.1), 134.2)

    def test_none(self):
        self.assertIsNone(vx.implied_from_multiple(None, 6.1))
        self.assertIsNone(vx.implied_from_multiple(22, None))


class TestDivergence(unittest.TestCase):
    def test_basic(self):
        # |165-158|/161.5 ≈ 0.04334
        self.assertAlmostEqual(vx.divergence(165, 158), 7 / 161.5, places=5)

    def test_identical_zero(self):
        self.assertEqual(vx.divergence(100, 100), 0.0)

    def test_nonpositive_mean_none(self):
        self.assertIsNone(vx.divergence(-10, 10))       # 均值 0
        self.assertIsNone(vx.divergence(-5, -5))         # 均值<0

    def test_none_inputs(self):
        self.assertIsNone(vx.divergence(None, 100))


class TestTriangulate(unittest.TestCase):
    def test_three_methods(self):
        t = vx.triangulate({"DCF": 165, "comps": 130, "ms": 150})
        self.assertEqual(t["n"], 3)
        self.assertEqual(t["median"], 150)
        self.assertEqual((t["low"], t["high"]), (130, 165))
        self.assertAlmostEqual(t["spread_pct"], (165 - 130) / 150)
        self.assertEqual(len(t["pairwise"]), 3)          # C(3,2)

    def test_drops_none(self):
        t = vx.triangulate({"DCF": 165, "comps": None})
        self.assertEqual(t["n"], 1)

    def test_empty(self):
        t = vx.triangulate({"a": None})
        self.assertEqual(t["n"], 0)
        self.assertIsNone(t["median"])


class TestCrossVerdict(unittest.TestCase):
    def test_converge(self):
        r = vx.cross_verdict({"DCF": 165, "comps": 158})
        self.assertEqual(r["status"], "收敛")           # 背离 ~4% ≤ 15%
        self.assertEqual(r["confidence"], "高")

    def test_diverge(self):
        r = vx.cross_verdict({"DCF": 165, "comps": 100})
        self.assertEqual(r["status"], "分歧")           # 背离 ~49% ≥ 35%
        self.assertEqual(r["confidence"], "低")
        self.assertTrue(any("显著高于" in f for f in r["flags"]))

    def test_partial(self):
        r = vx.cross_verdict({"DCF": 165, "comps": 134.2})
        self.assertEqual(r["status"], "部分收敛")        # 背离 ~21%,介于 15%~35%

    def test_insufficient(self):
        r = vx.cross_verdict({"DCF": 165})
        self.assertEqual(r["status"], "数据不足")

    def test_price_positioning(self):
        under = vx.cross_verdict({"DCF": 165, "comps": 158}, price=140)
        self.assertIn("低于所有方法", under["price_position"])
        self.assertGreater(under["margin_of_safety"], 0)
        over = vx.cross_verdict({"DCF": 165, "comps": 158}, price=200)
        self.assertIn("高于所有方法", over["price_position"])
        inside = vx.cross_verdict({"DCF": 165, "comps": 130}, price=150)
        self.assertIn("区间内", inside["price_position"])


if __name__ == "__main__":
    unittest.main()
