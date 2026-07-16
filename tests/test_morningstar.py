"""morningstar_fair_value.py 回归测试（纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import morningstar_fair_value as ms  # noqa: E402


class TestExtractTicker(unittest.TestCase):
    def test_tenforeid_with_exchange(self):
        # "0P0000..." 无交易所 → 原样;"126.1.AAPL" → 取尾段
        self.assertEqual(ms.extract_ticker("126.1.AAPL"), "AAPL")
        self.assertEqual(ms.extract_ticker("EX.SUB.MSFT"), "MSFT")

    def test_short_or_empty(self):
        self.assertEqual(ms.extract_ticker(""), "")
        self.assertEqual(ms.extract_ticker("AAPL"), "AAPL")     # 无点,原样


class TestUpsidePct(unittest.TestCase):
    def test_undervalued_positive(self):
        # 公允价值 120、现价 100 → +20%
        self.assertAlmostEqual(ms.upside_pct(120.0, 100.0), 20.0)

    def test_overvalued_negative(self):
        self.assertAlmostEqual(ms.upside_pct(80.0, 100.0), -20.0)

    def test_guards(self):
        self.assertIsNone(ms.upside_pct(120.0, 0))             # 现价<=0
        self.assertIsNone(ms.upside_pct(None, 100.0))          # 无公允价值
        self.assertIsNone(ms.upside_pct(120.0, -5))


if __name__ == "__main__":
    unittest.main()
