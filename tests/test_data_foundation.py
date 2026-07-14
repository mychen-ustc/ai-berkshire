"""Tier 1 数据地基回归测试：点时财务库 + 公司行动 + 退市样本(纯函数，零依赖)。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import pit_financials as pf  # noqa: E402
import corporate_actions as ca  # noqa: E402
import delisting as dl  # noqa: E402


class TestPITFinancials(unittest.TestCase):
    def setUp(self):
        self.recs = [
            {"symbol": "G", "metric": "rev", "fiscal_period": "2025Q3", "value": 88, "available_at": "2025-10-29"},
            {"symbol": "G", "metric": "rev", "fiscal_period": "2025Q4", "value": 96, "available_at": "2026-02-04"},
        ]

    def test_no_lookahead_excludes_unpublished(self):
        # 2026-01-15：Q4(2/4披露)尚不可见，只见 Q3
        hit = pf.as_of(self.recs, "G", "rev", "2026-01-15")
        self.assertEqual(hit["fiscal_period"], "2025Q3")
        self.assertEqual(hit["value"], 88)

    def test_visible_after_publish(self):
        hit = pf.as_of(self.recs, "G", "rev", "2026-02-10")
        self.assertEqual(hit["fiscal_period"], "2025Q4")

    def test_has_lookahead_trap(self):
        trap = pf.has_lookahead(self.recs, "G", "rev", "2026-01-15")
        self.assertEqual(len(trap), 1)
        self.assertEqual(trap[0]["fiscal_period"], "2025Q4")

    def test_series_dedup_latest_revision(self):
        recs = self.recs + [
            {"symbol": "G", "metric": "rev", "fiscal_period": "2025Q4", "value": 97,
             "available_at": "2026-03-01"}]  # Q4 修订
        s = pf.series_as_of(recs, "G", "rev", "2026-03-15")
        q4 = [r for r in s if r["fiscal_period"] == "2025Q4"]
        self.assertEqual(len(q4), 1)              # 去重
        self.assertEqual(q4[0]["value"], 97)      # 取最新修订

    def test_empty_before_any(self):
        self.assertIsNone(pf.as_of(self.recs, "G", "rev", "2025-01-01"))


class TestCorporateActions(unittest.TestCase):
    def setUp(self):
        self.acts = [
            {"symbol": "NVDA", "type": "split", "date": "2024-06-10", "ratio": 10},
            {"symbol": "KO", "type": "dividend", "date": "2026-06-15", "amount": 0.5},
            {"symbol": "FB", "type": "rename", "date": "2022-06-09", "new_symbol": "META"},
        ]

    def test_split_price_factor(self):
        # 拆股后,拆股前的价格 ×(1/10) 才可比
        f = ca.price_adjust_factor(self.acts, "NVDA", "2024-01-01")
        self.assertAlmostEqual(f, 0.1, places=9)

    def test_split_after_action_no_effect(self):
        # 拆股日之后的日期,无需复权
        f = ca.price_adjust_factor(self.acts, "NVDA", "2024-12-01")
        self.assertAlmostEqual(f, 1.0, places=9)

    def test_share_factor(self):
        self.assertAlmostEqual(ca.share_adjust_factor(self.acts, "NVDA", "2024-01-01"), 10.0)
        self.assertAlmostEqual(ca.share_adjust_factor(self.acts, "NVDA", "2025-01-01"), 1.0)

    def test_dividend_price_factor(self):
        # 每股分红0.5、当时价50 → 前复权因子 ×(1-0.5/50)=0.99
        f = ca.price_adjust_factor(self.acts, "KO", "2026-06-01", price_ref=50)
        self.assertAlmostEqual(f, 0.99, places=9)

    def test_resolve_rename(self):
        self.assertEqual(ca.resolve_symbol(self.acts, "FB"), "META")
        self.assertEqual(ca.resolve_symbol(self.acts, "AAPL"), "AAPL")

    def test_total_dividends(self):
        self.assertAlmostEqual(ca.total_dividends(self.acts, "KO", "2026-01-01", "2026-12-31"), 0.5)
        self.assertAlmostEqual(ca.total_dividends(self.acts, "KO", "2027-01-01", "2027-12-31"), 0.0)


class TestDelisting(unittest.TestCase):
    def setUp(self):
        self.recs = [
            {"symbol": "LEHMQ", "name": "雷曼", "listed": "1994-05-01",
             "delisted": "2008-09-15", "reason": "bankruptcy", "terminal_return": -1.0},
        ]

    def test_was_listed_alive(self):
        self.assertTrue(dl.was_listed(self.recs[0], "2008-06-01"))   # 破产前在市

    def test_was_listed_after_delist(self):
        self.assertFalse(dl.was_listed(self.recs[0], "2009-01-01"))  # 退市后

    def test_was_listed_before_ipo(self):
        self.assertFalse(dl.was_listed(self.recs[0], "1990-01-01"))  # 上市前

    def test_universe_includes_then_live(self):
        u = dl.universe_as_of(self.recs, ["AAPL", "LEHMQ"], "2008-06-01")
        self.assertIn("LEHMQ", u)         # 当时在市,应含(防幸存者偏差)
        self.assertIn("AAPL", u)          # 不在退市库,默认存续

    def test_universe_excludes_after_delist(self):
        u = dl.universe_as_of(self.recs, ["AAPL", "LEHMQ"], "2009-06-01")
        self.assertNotIn("LEHMQ", u)      # 已退市,不在池

    def test_survivorship_gap(self):
        gap = dl.survivorship_gap(self.recs, "2008-06-01")
        self.assertEqual(len(gap), 1)     # 当时在市、如今已死 = 幸存者偏差漏样
        self.assertEqual(gap[0]["symbol"], "LEHMQ")


if __name__ == "__main__":
    unittest.main()
