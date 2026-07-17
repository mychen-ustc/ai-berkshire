"""strategy_backtest.py 回归测试（因子策略回测纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import strategy_backtest as sb  # noqa: E402


class TestMonthEnd(unittest.TestCase):
    def test_picks_last_per_month(self):
        d = ["2024-01-05", "2024-01-19", "2024-02-02", "2024-02-27", "2024-03-01"]
        self.assertEqual(sb.month_end_dates(d), ["2024-01-19", "2024-02-27", "2024-03-01"])


class TestSelectTop(unittest.TestCase):
    def test_top_frac(self):
        sc = {"A": 0.3, "B": 0.1, "C": 0.2, "D": 0.05}
        self.assertEqual(sb.select_top(sc, 0.5), ["A", "C"])       # 前 50% 按分降序

    def test_drops_none(self):
        self.assertEqual(sb.select_top({"A": None, "B": 0.1}, 1.0), ["B"])

    def test_min_one(self):
        self.assertEqual(len(sb.select_top({"A": 0.3, "B": 0.1}, 0.1)), 1)  # 至少选1

    def test_empty(self):
        self.assertEqual(sb.select_top({"A": None}, 0.5), [])


class TestWeightsTurnover(unittest.TestCase):
    def test_equal_weight(self):
        self.assertEqual(sb.equal_weight(["A", "B", "C"]), {"A": 1/3, "B": 1/3, "C": 1/3})
        self.assertEqual(sb.equal_weight([]), {})

    def test_turnover(self):
        self.assertEqual(sb.turnover({}, {"A": 0.5, "B": 0.5}), 0.5)        # 从空到满仓=0.5单边
        self.assertEqual(sb.turnover({"A": 0.5, "B": 0.5}, {"A": 0.5, "B": 0.5}), 0.0)
        self.assertAlmostEqual(sb.turnover({"A": 1.0}, {"B": 1.0}), 1.0)    # 全换


class TestHoldingReturn(unittest.TestCase):
    def setUp(self):
        self.prices = {"A": {"d0": 100, "d1": 110}, "B": {"d0": 50, "d1": 45}}

    def test_weighted(self):
        r = sb.holding_return(self.prices, {"A": 0.5, "B": 0.5}, "d0", "d1")
        self.assertAlmostEqual(r, 0.5 * 0.10 + 0.5 * (-0.10))      # +5%/-10% → 0

    def test_missing_price_renormalizes(self):
        # B 缺 d1 价 → 只用 A,权重重归一到 1.0
        p = {"A": {"d0": 100, "d1": 110}, "B": {"d0": 50}}
        self.assertAlmostEqual(sb.holding_return(p, {"A": 0.5, "B": 0.5}, "d0", "d1"), 0.10)

    def test_no_avail(self):
        self.assertEqual(sb.holding_return({}, {"A": 1.0}, "d0", "d1"), 0.0)


class TestBacktestPeriods(unittest.TestCase):
    def test_end_to_end_pure(self):
        rebal = ["m0", "m1", "m2"]
        prices = {"A": {"m0": 100, "m1": 110, "m2": 121},
                  "B": {"m0": 100, "m1": 100, "m2": 100}}
        scores = {"m0": {"A": 0.3, "B": 0.1}, "m1": {"A": 0.3, "B": 0.1}}
        periods = sb.backtest_periods(rebal, scores, prices, top_frac=0.5, cost_bps=0)
        self.assertEqual(len(periods), 2)
        self.assertEqual(periods[0]["n_sel"], 1)                  # 选A
        self.assertAlmostEqual(periods[0]["gross"], 0.10)         # A m0→m1 +10%
        self.assertEqual(periods[0]["turnover"], 0.5)            # 空→满A

    def test_cost_reduces_net(self):
        rebal = ["m0", "m1"]
        prices = {"A": {"m0": 100, "m1": 110}}
        scores = {"m0": {"A": 0.3}}
        p = sb.backtest_periods(rebal, scores, prices, top_frac=1.0, cost_bps=100)[0]
        self.assertLess(p["net"], p["gross"])                    # 扣成本后净<毛


class TestSplitAndPerf(unittest.TestCase):
    def test_split(self):
        periods = [{"net": 0.01}] * 10
        is_p, oos_p = sb.split_is_oos(periods, oos_frac=0.4)
        self.assertEqual((len(is_p), len(oos_p)), (6, 4))

    def test_perf_positive(self):
        periods = [{"net": 0.01, "turnover": 0.1}] * 12          # 每月+1%,一年
        p = sb.perf(periods, ppy=12)
        self.assertEqual(p["n"], 12)
        self.assertAlmostEqual(p["cagr"], (1.01 ** 12) - 1, places=4)
        self.assertGreater(p["sharpe"], 0)

    def test_perf_empty(self):
        self.assertIsNone(sb.perf([])["cagr"])


if __name__ == "__main__":
    unittest.main()
