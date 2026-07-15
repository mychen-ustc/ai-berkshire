"""statement_model 勾稽校验 + pipeline 去重 纯函数测试(零依赖)。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import statement_model as sm  # noqa: E402
import pipeline as pl  # noqa: E402


class TestEquityRollforward(unittest.TestCase):
    def test_buyback_payout_over_100(self):
        # 净利100,权益反降10(-10) → 隐含返还=100-(-10)=110 → 返还率110%(回购型)
        r = sm.equity_rollforward(500, 490, 100)
        self.assertAlmostEqual(r["delta_equity"], -10)
        self.assertAlmostEqual(r["implied_capital_return"], 110)
        self.assertAlmostEqual(r["payout_ratio"], 1.1, places=6)

    def test_retained_growth(self):
        # 净利100,权益+70 → 返还30 → 返还率30%(留存成长)
        r = sm.equity_rollforward(500, 570, 100)
        self.assertAlmostEqual(r["implied_capital_return"], 30)
        self.assertAlmostEqual(r["payout_ratio"], 0.3, places=6)


class TestRoeConsistency(unittest.TestCase):
    def test_consistent(self):
        ok, recomp, dev = sm.roe_consistency(30, 100, 0.30)
        self.assertTrue(ok)
        self.assertAlmostEqual(recomp, 0.30)

    def test_inconsistent_flagged(self):
        ok, recomp, dev = sm.roe_consistency(30, 100, 0.50)   # 报0.5但重算0.3
        self.assertFalse(ok)
        self.assertAlmostEqual(dev, 0.20, places=6)

    def test_none_equity(self):
        ok, _, _ = sm.roe_consistency(30, 0, 0.3)
        self.assertIsNone(ok)


class TestCanonSymbol(unittest.TestCase):
    def test_issuer_to_ticker(self):
        self.assertEqual(pl.canon_symbol("ALPHABET INC"), "GOOGL")
        self.assertEqual(pl.canon_symbol("APPLE INC"), "AAPL")
        self.assertEqual(pl.canon_symbol("BERKSHIRE HATHAWAY"), "BRK.B")

    def test_passthrough(self):
        self.assertEqual(pl.canon_symbol("603065"), "603065")
        self.assertEqual(pl.canon_symbol("09999.HK"), "09999.HK")


if __name__ == "__main__":
    unittest.main()
