"""backtest_rigorous.py 回归测试（T2-3 偏差量化与修正纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import backtest_rigorous as br  # noqa: E402


class TestSurvivorship(unittest.TestCase):
    def test_bias_overstatement(self):
        # 全域含雷曼-100%，幸存者池漏掉它 → 显著高估
        full = {"AAPL": 0.5, "LEHMQ": -1.0, "GOOGL": 0.8}
        surv = {"AAPL": 0.5, "GOOGL": 0.8}
        fa, sa, bias = br.survivorship_bias(full, surv)
        self.assertAlmostEqual(fa, (0.5 - 1.0 + 0.8) / 3, places=9)   # +10%
        self.assertAlmostEqual(sa, (0.5 + 0.8) / 2, places=9)         # +65%
        self.assertAlmostEqual(bias, sa - fa, places=9)               # +55% 高估
        self.assertGreater(bias, 0)

    def test_no_bias_when_equal(self):
        r = {"A": 0.1, "B": 0.2}
        _, _, bias = br.survivorship_bias(r, r)
        self.assertAlmostEqual(bias, 0.0, places=9)


class TestCAAdjustedReturn(unittest.TestCase):
    def test_split_restores_return(self):
        # 1拆10：期初1200、期末名义140(拆后)。不修正=-88%(假暴跌)；修正后应≈+16.7%
        actions = [{"symbol": "X", "type": "split", "date": "2024-06-10", "ratio": 10}]
        ret = br.ca_adjusted_return(actions, "X", p_start=1200, p_end=140,
                                    d_start="2024-01-01", d_end="2024-12-31")
        # 拆后140×10=1400 → 1400/1200-1 = +16.7%
        self.assertAlmostEqual(ret, 1400 / 1200 - 1, places=6)
        self.assertGreater(ret, 0)                     # 不是假暴跌

    def test_dividend_adds_to_return(self):
        actions = [{"symbol": "K", "type": "dividend", "date": "2026-06-15", "amount": 2.0}]
        ret = br.ca_adjusted_return(actions, "K", p_start=100, p_end=105,
                                    d_start="2026-01-01", d_end="2026-12-31")
        # 价格 +5% + 分红 2/100=2% = +7%
        self.assertAlmostEqual(ret, 0.05 + 0.02, places=6)


class TestPITPaths(unittest.TestCase):
    def test_pit_metric_no_lookahead(self):
        recs = [{"symbol": "G", "metric": "rev", "fiscal_period": "2025Q4",
                 "value": 96, "available_at": "2026-02-04"}]
        path = br.pit_metric_path(recs, "G", "rev", ["2026-01-15", "2026-02-10"])
        self.assertIsNone(path["2026-01-15"])      # 未披露前 = None
        self.assertEqual(path["2026-02-10"], 96)   # 披露后可见

    def test_pit_universe_path(self):
        dels = [{"symbol": "LEHMQ", "listed": "1994-05-01",
                 "delisted": "2008-09-15", "reason": "bankruptcy"}]
        path = br.pit_universe_path(dels, ["AAPL", "LEHMQ"], ["2008-06-01", "2009-06-01"])
        self.assertIn("LEHMQ", path["2008-06-01"])     # 破产前在池
        self.assertNotIn("LEHMQ", path["2009-06-01"])  # 破产后出池


class TestRigorFlags(unittest.TestCase):
    def test_flags_partition(self):
        dels = [{"symbol": "LEHMQ", "listed": "1994-05-01", "delisted": "2008-09-15", "reason": "bankruptcy"}]
        pits = [{"symbol": "GOOGL", "metric": "rev", "fiscal_period": "2025Q4",
                 "value": 96, "available_at": "2026-02-04"}]
        acts = [{"symbol": "NVDA", "type": "split", "date": "2024-06-10", "ratio": 10}]
        f = br.rigor_flags(dels, pits, acts, ["AAPL", "LEHMQ", "GOOGL", "NVDA"],
                           "2007-01-01", "2009-12-31")
        self.assertEqual(f["survivorship_dropped"], ["LEHMQ"])
        self.assertIn("GOOGL", f["pit_coverage"])
        self.assertIn("AAPL", f["pit_missing"])
        self.assertEqual(f["corporate_actions"], ["NVDA"])


if __name__ == "__main__":
    unittest.main()
