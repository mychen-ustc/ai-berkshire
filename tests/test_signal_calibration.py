"""signal_calibration.py 回归测试（信号有效性校准纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import signal_calibration as sc  # noqa: E402
import technicals as tech  # noqa: E402


class TestForwardReturn(unittest.TestCase):
    def test_basic(self):
        self.assertAlmostEqual(sc.forward_return([10, 11, 12, 11], 0, 2), 12 / 10 - 1)

    def test_out_of_range(self):
        self.assertIsNone(sc.forward_return([10, 11, 12], 2, 3))
        self.assertIsNone(sc.forward_return([10, 11, 12], -1, 1))

    def test_zero_or_none_price(self):
        self.assertIsNone(sc.forward_return([0, 11, 12], 0, 1))
        self.assertIsNone(sc.forward_return([10, None, 12], 1, 1))


class TestCollectAndBaseline(unittest.TestCase):
    def test_collect_drops_invalid(self):
        prices = [10, 11, 12, 13]
        out = sc.collect_forward(prices, [0, 3], 2)      # idx3+2 越界 → 丢
        self.assertEqual(len(out), 1)

    def test_baseline_count(self):
        prices = [1, 2, 3, 4, 5]
        self.assertEqual(len(sc.baseline_forward(prices, 2)), 3)   # i=0,1,2 可算


class TestCalibrate(unittest.TestCase):
    def test_edge(self):
        cal = sc.calibrate([0.10, 0.08, 0.12], [0.02, -0.01, 0.03, 0.0])
        self.assertAlmostEqual(cal["signal_mean"], 0.10)
        self.assertAlmostEqual(cal["baseline_mean"], 0.01)
        self.assertAlmostEqual(cal["edge_mean"], 0.09)
        self.assertEqual(cal["signal_hit"], 1.0)
        self.assertEqual(cal["n_signals"], 3)


class TestVerdict(unittest.TestCase):
    def _cal(self, em, eh, n):
        return {"n_signals": n, "edge_mean": em, "edge_hit": eh}

    def test_effective(self):
        self.assertEqual(sc.verdict(self._cal(0.02, 0.05, 30))["status"], "有效")

    def test_ineffective(self):
        self.assertEqual(sc.verdict(self._cal(-0.01, -0.02, 30))["status"], "无效")

    def test_mixed(self):
        self.assertEqual(sc.verdict(self._cal(0.02, -0.01, 30))["status"], "存疑")

    def test_insufficient(self):
        self.assertEqual(sc.verdict(self._cal(0.05, 0.05, 5), min_n=20)["status"], "样本不足")


class TestSignalDetectors(unittest.TestCase):
    def test_rsi_series_matches_technicals_last(self):
        closes = [100, 102, 101, 103, 105, 104, 106, 108, 107, 109,
                  111, 110, 112, 114, 113, 115, 117, 116, 118, 120]
        self.assertAlmostEqual(sc.rsi_series(closes)[-1], tech.rsi(closes), places=9)

    def test_rsi_series_pads_none(self):
        s = sc.rsi_series([1, 2, 3], n=14)               # 数据不足
        self.assertTrue(all(x is None for x in s))

    def test_cross_below(self):
        self.assertEqual(sc.cross_below([35, 32, 28, 31, 25], 30), [2, 4])

    def test_cross_over(self):
        # fast 上穿 slow
        fast = [1, 2, 3, 5]
        slow = [4, 4, 4, 4]
        self.assertEqual(sc.cross_over(fast, slow), [3])

    def test_fire_indices_unknown_raises(self):
        with self.assertRaises(ValueError):
            sc.fire_indices([1, 2, 3], "nope")


if __name__ == "__main__":
    unittest.main()
