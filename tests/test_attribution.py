"""attribution.py 回归测试（stdlib unittest，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import attribution as at  # noqa: E402


class TestContributions(unittest.TestCase):
    def test_basic(self):
        contrib, total = at.contributions({"A": 0.6, "B": 0.4}, {"A": 0.10, "B": 0.05})
        self.assertAlmostEqual(contrib["A"], 0.06, places=10)
        self.assertAlmostEqual(contrib["B"], 0.02, places=10)
        self.assertAlmostEqual(total, 0.08, places=10)


class TestBrinson(unittest.TestCase):
    def setUp(self):
        self.groups = [
            {"group": "A", "wp": 0.6, "rp": 0.10, "wb": 0.5, "rb": 0.08},
            {"group": "B", "wp": 0.4, "rp": 0.05, "wb": 0.5, "rb": 0.04},
        ]

    def test_totals(self):
        r = at.brinson(self.groups)
        self.assertAlmostEqual(r["rp_total"], 0.08, places=10)
        self.assertAlmostEqual(r["rb_total"], 0.06, places=10)
        self.assertAlmostEqual(r["excess"], 0.02, places=10)

    def test_effects_decompose_to_excess(self):
        r = at.brinson(self.groups)
        self.assertAlmostEqual(r["allocation"], 0.004, places=10)
        self.assertAlmostEqual(r["selection"], 0.015, places=10)
        self.assertAlmostEqual(r["interaction"], 0.001, places=10)
        # 三效应之和 == 超额
        self.assertAlmostEqual(r["allocation"] + r["selection"] + r["interaction"],
                               r["excess"], places=10)


if __name__ == "__main__":
    unittest.main()
