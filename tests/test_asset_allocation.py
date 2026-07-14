"""asset_allocation.py 回归测试（T3-2 SAA/TAA 纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import asset_allocation as aa  # noqa: E402


class TestSAA(unittest.TestCase):
    def test_sums_100(self):
        for risk in aa.SAA:
            self.assertAlmostEqual(sum(aa.strategic(risk).values()), 100, places=6)

    def test_growth_more_stock(self):
        self.assertGreater(aa.strategic("aggressive")["stock"], aa.strategic("conservative")["stock"])

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            aa.strategic("nonsense")


class TestTAA(unittest.TestCase):
    def test_recovery_overweights_stock(self):
        saa = aa.strategic("balanced")
        taa = aa.tactical(saa, "复苏")
        self.assertGreater(taa["stock"], saa["stock"])    # 复苏超配股票
        self.assertAlmostEqual(sum(taa.values()), 100, places=1)  # 归一

    def test_stagflation_overweights_cash_commodity(self):
        saa = aa.strategic("balanced")
        taa = aa.tactical(saa, "滞胀")
        self.assertLess(taa["stock"], saa["stock"])       # 滞胀低配股票
        self.assertGreater(taa["commodity"], saa["commodity"])

    def test_tilt_capped(self):
        # 单类倾斜不超过 max_tilt(截断)
        saa = {"stock": 55, "bond": 30, "commodity": 5, "cash": 10}
        taa = aa.tactical(saa, "复苏", max_tilt=3)
        # 归一前 stock 最多 +3 → 归一后仍应接近但不暴增
        self.assertLess(taa["stock"], 62)

    def test_no_negative(self):
        saa = {"stock": 55, "bond": 3, "commodity": 5, "cash": 10}
        taa = aa.tactical(saa, "衰退")             # bond+10, 不会负
        self.assertTrue(all(v >= 0 for v in taa.values()))


class TestRebalance(unittest.TestCase):
    def test_triggers_over_band(self):
        tgt = {"stock": 55, "bond": 30, "commodity": 5, "cash": 10}
        cur = {"stock": 64, "bond": 22, "commodity": 4, "cash": 10}
        trig = aa.rebalance_triggers(tgt, cur, band=5)
        assets = {t["asset"] for t in trig}
        self.assertIn("stock", assets)     # +9 > 5
        self.assertIn("bond", assets)      # -8 > 5
        self.assertNotIn("commodity", assets)  # -1 < 5

    def test_stock_reduce_action(self):
        trig = aa.rebalance_triggers({"stock": 55}, {"stock": 64}, 5)
        self.assertEqual(trig[0]["action"], "减")

    def test_drift_summary(self):
        tgt = {"stock": 55, "bond": 30, "commodity": 5, "cash": 10}
        cur = {"stock": 64, "bond": 22, "commodity": 4, "cash": 10}
        # |9|+|8|+|1|+|0| = 18, /2 = 9
        self.assertAlmostEqual(aa.drift_summary(tgt, cur), 9.0, places=6)

    def test_no_trigger_within_band(self):
        self.assertEqual(aa.rebalance_triggers({"stock": 55}, {"stock": 57}, 5), [])


if __name__ == "__main__":
    unittest.main()
