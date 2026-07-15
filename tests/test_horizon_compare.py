"""horizon_compare.py 回归测试（多周期对比纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import horizon_compare as hc  # noqa: E402


class TestResample(unittest.TestCase):
    def test_month_last_obs(self):
        pts = [("2024-01-05", 10), ("2024-01-26", 11), ("2024-02-02", 12)]
        r = hc.resample_monthly(pts)
        self.assertEqual(r, [("2024-01", 11), ("2024-02", 12)])   # 1月取最后11


class TestAlign(unittest.TestCase):
    def _mk(self, i):
        return f"20{16 + i // 12:02d}-{i % 12 + 1:02d}"   # 真实可排序月键 YYYY-MM

    def test_common_dates_weighted(self):
        s = {"A": [(self._mk(i), 100 * (1.1 ** i)) for i in range(15)],
             "B": [(self._mk(i), 50) for i in range(15)]}   # B 不动
        dates, rets, start = hc.align_weekly(s, {"A": 50, "B": 50})
        self.assertEqual(len(rets), 14)
        # 组合 = 50%A(+10%/期) + 50%B(0) = +5%/期
        self.assertAlmostEqual(rets[0], 0.05, places=6)

    def test_intersection_only(self):
        s = {"A": [(self._mk(i), 100) for i in range(20)],
             "B": [(self._mk(i), 100) for i in range(5, 20)]}   # B 从第5月开始
        dates, rets, start = hc.align_weekly(s, {"A": 50, "B": 50})
        self.assertEqual(start, self._mk(5))    # 共同起点=较晚者

    def test_insufficient_returns_empty(self):
        s = {"A": [("m0", 1), ("m1", 2)]}       # 点太少
        self.assertEqual(hc.align_weekly(s, {"A": 100}), ([], [], None))


class TestHorizonSlice(unittest.TestCase):
    def test_slice_years(self):
        rets = list(range(60))                  # 60 个月
        self.assertEqual(len(hc.horizon_slice(rets, 3, 12)), 36)   # 3年=36月
        self.assertEqual(hc.horizon_slice(rets, 3, 12), list(range(24, 60)))

    def test_insufficient_none(self):
        self.assertIsNone(hc.horizon_slice(list(range(24)), 5, 12))   # 24月 < 5年(60月)


class TestMonthRange(unittest.TestCase):
    def test_range(self):
        self.assertEqual(hc.month_range("2024-11", "2025-02"),
                         ["2024-11", "2024-12", "2025-01", "2025-02"])

    def test_single(self):
        self.assertEqual(hc.month_range("2024-06", "2024-06"), ["2024-06"])


class TestForwardFill(unittest.TestCase):
    def test_fill_and_none_before(self):
        grid = ["2024-01", "2024-02", "2024-03", "2024-04"]
        pairs = [("2024-02", 10), ("2024-04", 12)]   # 缺 03(前向填充为10)、01前为None
        self.assertEqual(hc.forward_fill(pairs, grid), [None, 10, 10, 12])


class TestPortfolioReturns(unittest.TestCase):
    def test_renormalized_weighted(self):
        # A(+10%/期,权重40)+B(0,权重40)，C 不合格未纳入 → renorm 到 50/50 → +5%/期
        filled = {"A": [100, 110, 121], "B": [50, 50, 50]}
        rets = hc.portfolio_returns(filled, {"A": 40, "B": 40, "C": 20}, ["A", "B"])
        self.assertEqual(len(rets), 2)
        self.assertAlmostEqual(rets[0], 0.05, places=6)   # (0.5×0.1 + 0.5×0)

    def test_skip_none(self):
        filled = {"A": [None, 100, 110]}                  # 首期 None → 跳过
        rets = hc.portfolio_returns(filled, {"A": 100}, ["A"])
        self.assertEqual(len(rets), 1)                    # 只算 100→110
        self.assertAlmostEqual(rets[0], 0.1, places=6)


class TestSeriesMetrics(unittest.TestCase):
    def test_growth(self):
        # 12 个月每月 +1% → 总回报 (1.01^12 - 1)
        rets = [0.01] * 12
        m = hc.series_metrics(rets, rf=0.0, ppy=12)
        self.assertAlmostEqual(m["total_return"], 1.01 ** 12 - 1, places=9)
        self.assertAlmostEqual(m["final_balance"], 10000 * 1.01 ** 12, places=4)
        self.assertAlmostEqual(m["cagr"], 1.01 ** 12 - 1, places=6)   # 1年→CAGR=总回报

    def test_none_empty(self):
        self.assertIsNone(hc.series_metrics([]))


if __name__ == "__main__":
    unittest.main()
