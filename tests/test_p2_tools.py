"""P2 工具回归测试：forensic + portfolio_optimizer（stdlib unittest，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import forensic as fx  # noqa: E402
import portfolio_optimizer as po  # noqa: E402


class TestForensic(unittest.TestCase):
    def test_mscore_no_change(self):
        # 各指数=1、TATA=0 → M=-2.48（不触发阈值 -1.78）
        m = fx.beneish_mscore(1, 1, 1, 1, 1, 1, 0, 1)
        self.assertAlmostEqual(m, -2.48, places=6)
        self.assertIn("未触发", fx.mscore_flag(m))

    def test_mscore_manipulator(self):
        # 应收/收入、营收、应计齐升 → 越过阈值
        m = fx.beneish_mscore(1.5, 1, 1, 1.5, 1, 1, 0.1, 1)
        self.assertGreater(m, -1.78)
        self.assertIn("可能操纵", fx.mscore_flag(m))

    def test_altman_safe(self):
        z = fx.altman_z(0.2, 0.3, 0.15, 2.0, 1.1)
        self.assertAlmostEqual(z, 3.455, places=6)
        self.assertIn("安全", fx.altman_zone(z))

    def test_altman_distress(self):
        z = fx.altman_z(-0.1, -0.2, -0.05, 0.2, 0.4)
        self.assertLess(z, 1.81)
        self.assertIn("困境", fx.altman_zone(z))

    def test_accrual_and_conversion(self):
        # 净利 142、经营现金流 -30、总资产 400（江波龙式：利润高但现金流负）
        self.assertAlmostEqual(fx.accrual_ratio(142, -30, 400), 0.43, places=6)
        self.assertAlmostEqual(fx.cash_conversion(142, -30), -30 / 142, places=6)


class TestOptimizer(unittest.TestCase):
    def test_inverse_vol(self):
        w = po.inverse_vol_weights({"A": 0.1, "B": 0.2, "C": 0.4})
        self.assertAlmostEqual(w["A"], 10 / 17.5, places=9)
        self.assertAlmostEqual(w["B"], 5 / 17.5, places=9)
        self.assertAlmostEqual(w["C"], 2.5 / 17.5, places=9)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=9)

    def test_equal(self):
        w = po.equal_weights(["A", "B", "C", "D"])
        self.assertTrue(all(abs(v - 0.25) < 1e-12 for v in w.values()))

    def test_enforce_caps_redistributes(self):
        w = po.enforce_caps({"A": 0.6, "B": 0.25, "C": 0.15}, 0.4)
        self.assertAlmostEqual(w["A"], 0.4, places=9)
        self.assertAlmostEqual(w["B"], 0.375, places=9)
        self.assertAlmostEqual(w["C"], 0.225, places=9)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=9)

    def test_enforce_caps_noop_when_within(self):
        w = po.enforce_caps({"A": 0.3, "B": 0.3, "C": 0.4}, 0.5)
        self.assertAlmostEqual(w["A"], 0.3, places=9)
        self.assertAlmostEqual(w["C"], 0.4, places=9)


if __name__ == "__main__":
    unittest.main()
