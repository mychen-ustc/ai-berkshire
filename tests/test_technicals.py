"""technicals.py 回归测试（stdlib unittest，零依赖，golden case 可手算）。"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import technicals as ta  # noqa: E402


class TestIndicators(unittest.TestCase):
    def test_sma_last(self):
        self.assertEqual(ta.sma_last([1, 2, 3, 4, 5], 3), 4.0)   # (3+4+5)/3
        self.assertIsNone(ta.sma_last([1, 2], 3))                # 数据不足

    def test_ema_constant(self):
        self.assertEqual(ta.ema([5, 5, 5, 5], 3), [5.0, 5.0, 5.0, 5.0])

    def test_rsi_bounds(self):
        self.assertEqual(ta.rsi(list(range(1, 20)), 14), 100.0)   # 单调涨→100
        self.assertEqual(ta.rsi(list(range(20, 1, -1)), 14), 0.0)  # 单调跌→0
        self.assertIsNone(ta.rsi([1, 2, 3], 14))                  # 数据不足

    def test_macd_constant_is_zero(self):
        r = ta.macd([10.0] * 40)
        self.assertAlmostEqual(r["macd"], 0.0, places=9)
        self.assertAlmostEqual(r["hist"], 0.0, places=9)

    def test_bollinger(self):
        b = ta.bollinger([1, 2, 3, 4, 5], n=5, k=2.0)
        self.assertAlmostEqual(b["mid"], 3.0, places=9)
        self.assertAlmostEqual(b["upper"], 3 + 2 * math.sqrt(2), places=6)
        self.assertAlmostEqual(b["pctB"], 0.8535533, places=6)
        # 常数序列 → 上下轨重合，%B 记为 0.5，带宽 0
        flat = ta.bollinger([10.0] * 20)
        self.assertEqual(flat["pctB"], 0.5)
        self.assertEqual(flat["bandwidth"], 0.0)

    def test_true_ranges_and_atr(self):
        bars = [{"high": 11, "low": 9, "close": 10},
                {"high": 12, "low": 8, "close": 11},
                {"high": 13, "low": 11, "close": 12}]
        self.assertEqual(ta.true_ranges(bars), [4.0, 2.0])
        self.assertEqual(ta.atr(bars, n=2), 3.0)

    def test_roc(self):
        self.assertAlmostEqual(ta.roc([10, 11, 12, 13], 3), 30.0, places=9)
        self.assertIsNone(ta.roc([10, 11], 3))

    def test_high_low_distance(self):
        d = ta.high_low_distance([10, 20, 5, 15], lookback=250)
        self.assertEqual(d["high"], 20)
        self.assertEqual(d["low"], 5)
        self.assertAlmostEqual(d["from_high_pct"], -25.0, places=9)
        self.assertAlmostEqual(d["from_low_pct"], 200.0, places=9)

    def test_ma_alignment_trend(self):
        self.assertEqual(ta.ma_alignment(list(range(1, 211)))["trend"], "up")
        self.assertEqual(ta.ma_alignment(list(range(210, 0, -1)))["trend"], "down")

    def test_relative_strength(self):
        stock = [{"date": "2026-01-01", "close": 10}, {"date": "2026-01-02", "close": 11},
                 {"date": "2026-01-03", "close": 12}]
        bench = [{"date": "2026-01-01", "close": 10}, {"date": "2026-01-02", "close": 10},
                 {"date": "2026-01-03", "close": 10}]
        rs = ta.relative_strength(stock, bench)
        self.assertAlmostEqual(rs["rs_now"], 1.2, places=9)
        self.assertAlmostEqual(rs["outperform_since_start_pct"], 20.0, places=9)

    def test_compute_runs_endtoend(self):
        # 构造 210 根递增K线，确保各指标不崩且姿态为上升趋势
        bars = [{"date": f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
                 "open": i + 0.5, "high": i + 1, "low": i - 0.5,
                 "close": float(i), "volume": 1000.0 + i} for i in range(1, 211)]
        r = ta.compute(bars)
        self.assertIn("上升趋势", r["posture"]["trend"])
        self.assertEqual(r["last"], 210.0)


if __name__ == "__main__":
    unittest.main()
