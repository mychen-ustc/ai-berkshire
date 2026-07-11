"""P1 四工具回归测试：watch / sector_rotation / special_situations / sell_discipline
（stdlib unittest，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import watch  # noqa: E402
import sector_rotation as sr  # noqa: E402
import special_situations as ss  # noqa: E402
import sell_discipline as sd  # noqa: E402


class TestWatch(unittest.TestCase):
    def test_stop_loss(self):
        a = watch.evaluate_triggers(100, 80, {"stop_loss_pct": 15})
        self.assertTrue(any(lvl == "alert" and "止损" in m for lvl, m in a))

    def test_take_profit(self):
        a = watch.evaluate_triggers(100, 160, {"take_profit_pct": 50})
        self.assertTrue(any("止盈" in m for _, m in a))

    def test_flat_no_alert(self):
        self.assertEqual(watch.evaluate_triggers(100, 100, {"stop_loss_pct": 15}), [])

    def test_price_below(self):
        a = watch.evaluate_triggers(100, 90, {"price_below": 95})
        self.assertTrue(any("跌破" in m for _, m in a))

    def test_day_move(self):
        a = watch.evaluate_triggers(100, 100, {"day_move_pct": 5}, change_pct=-7)
        self.assertTrue(any("异动" in m for _, m in a))


class TestSectorRotation(unittest.TestCase):
    def test_trailing_return(self):
        self.assertAlmostEqual(sr.trailing_return([100, 110], 1), 0.1, places=10)
        self.assertIsNone(sr.trailing_return([100], 1))

    def test_momentum_score(self):
        self.assertAlmostEqual(sr.momentum_score([100, 110, 121], [1]), 0.1, places=10)

    def test_rank(self):
        rows, market = sr.rank_sectors({"A": [100, 120], "B": [100, 100]}, lookbacks=(1,))
        self.assertEqual(rows[0]["sector"], "A")
        self.assertAlmostEqual(market, 0.1, places=10)
        self.assertAlmostEqual(rows[0]["rs"], 0.1, places=10)
        self.assertAlmostEqual(rows[-1]["rs"], -0.1, places=10)


class TestMergerArb(unittest.TestCase):
    def test_gross_and_annualized(self):
        r = ss.merger_arb(100, 110, 365)
        self.assertAlmostEqual(r["gross_spread"], 0.10, places=10)
        self.assertAlmostEqual(r["annualized"], 0.10, places=6)

    def test_expected_value(self):
        r = ss.merger_arb(100, 110, 365, downside=80, prob=0.9)
        self.assertAlmostEqual(r["expected_value"], 107.0, places=6)
        self.assertAlmostEqual(r["ev_return"], 0.07, places=6)


class TestSellDiscipline(unittest.TestCase):
    def test_thesis_broken_sell(self):
        v, _ = sd.sell_verdict(thesis_broken=True)
        self.assertEqual(v, "SELL")

    def test_stop_loss_sell(self):
        v, _ = sd.sell_verdict(entry=100, current=70, stop_loss_pct=20)
        self.assertEqual(v, "SELL")

    def test_far_above_fair_sell(self):
        v, _ = sd.sell_verdict(current=130, fair_value=100)
        self.assertEqual(v, "SELL")

    def test_at_fair_trim(self):
        v, _ = sd.sell_verdict(current=105, fair_value=100)
        self.assertEqual(v, "TRIM")

    def test_opportunity_cost_sell(self):
        v, _ = sd.sell_verdict(expected_return=0.02, risk_free=0.04)
        self.assertEqual(v, "SELL")

    def test_switch_trim(self):
        v, _ = sd.sell_verdict(expected_return=0.10, better_opp_return=0.20)
        self.assertEqual(v, "TRIM")

    def test_healthy_hold(self):
        v, _ = sd.sell_verdict(entry=100, current=105, fair_value=150, stop_loss_pct=25,
                               expected_return=0.10, risk_free=0.04)
        self.assertEqual(v, "HOLD")


if __name__ == "__main__":
    unittest.main()
