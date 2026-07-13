"""backtest.py 回归测试（stdlib unittest，零依赖，纯信号/指标）。"""
import argparse
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import backtest as bt  # noqa: E402


def _args(**kw):
    d = {"sma": 3, "lookback": 4, "top": 1, "strategy": "momentum"}
    d.update(kw)
    return argparse.Namespace(**d)


class TestSignals(unittest.TestCase):
    COLS = {"A": [10, 11, 12, 13, 14, 15], "B": [10, 9, 8, 7, 6, 5]}
    SYMS = ["A", "B"]

    def test_buyhold_equal(self):
        w = bt.w_buyhold(self.COLS, self.SYMS, 4, _args())
        self.assertAlmostEqual(w["A"], 0.5)
        self.assertAlmostEqual(sum(w.values()), 1.0)

    def test_trend_holds_uptrend_only(self):
        w = bt.w_trend(self.COLS, self.SYMS, 4, _args(sma=3))   # A>SMA持有, B<SMA空仓
        self.assertEqual(w["A"], 1.0)
        self.assertEqual(w["B"], 0.0)

    def test_trend_all_cash(self):
        cols = {"A": [10, 9, 8, 7]}                              # 单调跌→全空仓
        w = bt.w_trend(cols, ["A"], 3, _args(sma=3))
        self.assertEqual(w["A"], 0.0)

    def test_momentum_picks_top(self):
        w = bt.w_momentum(self.COLS, self.SYMS, 4, _args(lookback=4, top=1))  # A动量高→选A
        self.assertEqual(w["A"], 1.0)
        self.assertEqual(w["B"], 0.0)


class TestMetrics(unittest.TestCase):
    def test_metrics(self):
        m = bt.metrics([0.1, -0.1, 0.1], 12)
        self.assertEqual(m["periods"], 3)
        self.assertAlmostEqual(m["hit_rate"], 2 / 3, places=6)
        self.assertAlmostEqual(m["best"], 0.1)
        self.assertAlmostEqual(m["worst"], -0.1)
        # nav = 1*1.1*0.9*1.1 = 1.089
        self.assertAlmostEqual(m["final_nav"], 1.089, places=6)

    def test_empty(self):
        self.assertEqual(bt.metrics([], 12), {})


if __name__ == "__main__":
    unittest.main()
