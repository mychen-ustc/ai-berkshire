"""pipeline.py 回归测试（三级流水线纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import pipeline as pl  # noqa: E402


class TestDedupPool(unittest.TestCase):
    def test_dedup_keeps_earliest(self):
        recs = [{"symbol": "NVDA", "added": "2026-07-10"},
                {"symbol": "nvda", "added": "2026-07-01"},   # 同标的(大小写),更早
                {"symbol": "MSFT", "added": "2026-07-05"}]
        out = pl.dedup_pool(recs)
        self.assertEqual(len(out), 2)                         # NVDA 去重
        nvda = [r for r in out if r["symbol"].upper() == "NVDA"][0]
        self.assertEqual(nvda["added"], "2026-07-01")         # 保留最早


class TestTierView(unittest.TestCase):
    def setUp(self):
        self.pool = [{"symbol": "NVDA", "added": "d"}, {"symbol": "AXP", "added": "d"}]
        self.wl = [{"symbol": "GOOGL", "state": "holding"},
                   {"symbol": "VNQ", "state": "discovered"},
                   {"symbol": "MOAT", "state": "researching"}]
        self.holdings = {"GOOGL", "KO"}

    def test_three_tiers(self):
        v = pl.tier_view(self.pool, self.wl, self.holdings)
        self.assertEqual(v["T3"], ["GOOGL", "KO"])            # 持仓
        self.assertEqual(set(v["T2"]), {"VNQ", "MOAT"})       # watchlist在看(非持仓)
        # NVDA 在池且不在T2/T3 → T1; AXP 同理
        self.assertIn("NVDA", v["T1"])

    def test_dedup_across_tiers(self):
        # 若候选池的标的已在 T3 持仓,不应重复出现在 T1
        pool = [{"symbol": "GOOGL", "added": "d"}]
        v = pl.tier_view(pool, self.wl, self.holdings)
        self.assertNotIn("GOOGL", v["T1"])                    # 已持仓,不在候选池视图

    def test_consistency_issue(self):
        # KO 持仓但不在 watchlist → 报一致性问题
        v = pl.tier_view(self.pool, self.wl, self.holdings)
        self.assertTrue(any("KO" in i for i in v["issues"]))


if __name__ == "__main__":
    unittest.main()
