"""tca.py 回归测试（T3-1 交易成本模型纯函数，零依赖）。"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import tca  # noqa: E402


class TestImpact(unittest.TestCase):
    def test_sqrt_law(self):
        # 参与率翻4倍,冲击翻2倍(√定律)
        i1 = tca.impact_cost_bps(100000, 1000000, 0.02)     # 参与10%
        i2 = tca.impact_cost_bps(400000, 1000000, 0.02)     # 参与40%
        self.assertAlmostEqual(i2 / i1, 2.0, places=6)

    def test_zero_adv(self):
        self.assertEqual(tca.impact_cost_bps(1000, 0, 0.02), 0.0)

    def test_value_check(self):
        # coef=1, vol=0.02, participation=0.25 → 0.02×√0.25×10000 = 100bps
        self.assertAlmostEqual(tca.impact_cost_bps(250000, 1000000, 0.02), 100.0, places=6)


class TestTotalCost(unittest.TestCase):
    def test_decomposition_sums(self):
        c = tca.total_cost(250000, 1000000, 0.02, spread_bps=6, commission_bps=1, coef=1.0)
        self.assertAlmostEqual(c["spread_bps"], 3.0)          # 半价差
        self.assertAlmostEqual(c["impact_bps"], 100.0)        # 上面算过
        self.assertAlmostEqual(c["total_bps"], 1 + 3 + 100, places=6)
        self.assertAlmostEqual(c["total_cash"], (104.0 / 10000) * 250000, places=4)

    def test_participation(self):
        c = tca.total_cost(300000, 1000000, 0.02, 5)
        self.assertAlmostEqual(c["participation"], 0.3, places=9)


class TestShortfall(unittest.TestCase):
    def test_buy_higher_is_loss(self):
        s = tca.implementation_shortfall(100, 100.4, 5000, "buy")
        self.assertAlmostEqual(s["slippage_per_share"], 0.4, places=6)
        self.assertAlmostEqual(s["slippage_bps"], 40.0, places=6)
        self.assertAlmostEqual(s["total_cash"], 2000.0, places=4)

    def test_sell_lower_is_loss(self):
        # 卖出成交价低于决策价 = 被吃(正落差)
        s = tca.implementation_shortfall(100, 99.5, 1000, "sell")
        self.assertAlmostEqual(s["slippage_per_share"], 0.5, places=6)  # sign=-1 × (99.5-100)
        self.assertAlmostEqual(s["total_cash"], 500.0, places=4)


class TestDaysToExecute(unittest.TestCase):
    def test_days(self):
        # 订单占 ADV 60%,按20%上限 → 3天
        self.assertAlmostEqual(tca.days_to_execute(600000, 1000000, 0.2), 3.0, places=6)

    def test_inf_when_no_adv(self):
        self.assertEqual(tca.days_to_execute(1000, 0), math.inf)


if __name__ == "__main__":
    unittest.main()
