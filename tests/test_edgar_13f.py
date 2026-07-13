"""edgar_13f.py 回归测试（stdlib unittest，零依赖，纯 aggregate/classify_move）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import edgar_13f as ef  # noqa: E402


class TestAggregate(unittest.TestCase):
    def test_merge_by_cusip(self):
        holds = [{"issuer": "AAPL", "cusip": "037833100", "value": 100.0, "shares": 10},
                 {"issuer": "AAPL", "cusip": "037833100", "value": 50.0, "shares": 5},   # 同 cusip 合并
                 {"issuer": "KO", "cusip": "191216100", "value": 30.0, "shares": 3}]
        agg, total = ef.aggregate(holds)
        self.assertEqual(agg["037833100"]["value"], 150.0)
        self.assertEqual(agg["037833100"]["shares"], 15)
        self.assertEqual(total, 180.0)
        self.assertEqual(len(agg), 2)


class TestClassifyMove(unittest.TestCase):
    def test_moves(self):
        self.assertEqual(ef.classify_move(100, 0), "🟢新建")
        self.assertEqual(ef.classify_move(0, 100), "🔴清仓")
        self.assertEqual(ef.classify_move(120, 100), "➕加仓")
        self.assertEqual(ef.classify_move(80, 100), "➖减仓")
        self.assertEqual(ef.classify_move(101, 100), "持平")     # ±5% 内视为持平


if __name__ == "__main__":
    unittest.main()
