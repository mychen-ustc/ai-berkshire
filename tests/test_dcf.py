"""dcf.py 回归测试（stdlib unittest，零依赖）。"""
import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import dcf  # noqa: E402


class TestDCF(unittest.TestCase):
    def test_flat_perpetuity(self):
        # fcf0=100, 1年零增长, wacc10%, 永续0% → (100+1000)/1.1 = 1000
        r = dcf.dcf_value(100, [0.0], 0.10, 0.0, shares=1)
        self.assertAlmostEqual(float(r["per_share"]), 1000.0, places=4)

    def test_one_year_growth(self):
        # fcf1=110, PV1=100, TV=1100, PV_TV=1000 → EV=1100
        r = dcf.dcf_value(100, [0.10], 0.10, 0.0, shares=1)
        self.assertAlmostEqual(float(r["per_share"]), 1100.0, places=4)

    def test_net_cash_adds_value(self):
        r0 = dcf.dcf_value(100, [0.0], 0.10, 0.0, shares=1, net_debt=0)
        r1 = dcf.dcf_value(100, [0.0], 0.10, 0.0, shares=1, net_debt=-50)  # 净现金50
        self.assertAlmostEqual(float(r1["per_share"] - r0["per_share"]), 50.0, places=4)

    def test_wacc_le_terminal_raises(self):
        with self.assertRaises(ValueError):
            dcf.dcf_value(100, [0.0], 0.03, 0.05, shares=1)

    def test_terminal_pct(self):
        r = dcf.dcf_value(100, [0.0], 0.10, 0.0, shares=1)
        self.assertAlmostEqual(float(r["terminal_pct"]), 1000 / 1100, places=6)


class TestReverseDCF(unittest.TestCase):
    def test_round_trip(self):
        price = dcf.dcf_value(20, [0.10] * 10, 0.10, 0.03, shares=1)["per_share"]
        g = dcf.reverse_dcf(price, 20, 0.10, 0.03, shares=1, years=10)
        self.assertAlmostEqual(float(g), 0.10, places=4)


class TestSOTP(unittest.TestCase):
    def test_basic(self):
        r = dcf.sotp({"A": 1000, "B": 500}, shares=10, net_cash=100,
                     investments=400, holdco_discount=0.5)
        self.assertEqual(r["core"], Decimal("1500"))
        self.assertEqual(r["investments_adj"], Decimal("200.0"))
        self.assertEqual(r["equity"], Decimal("1800.0"))
        self.assertEqual(r["per_share"], Decimal("180"))


if __name__ == "__main__":
    unittest.main()
