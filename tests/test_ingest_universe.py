"""ingest_universe.py 回归测试（数据底座摄取纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import ingest_universe as iu  # noqa: E402


class TestIsTicker(unittest.TestCase):
    def test_real_tickers(self):
        for s in ("AAPL", "BRK.B", "603986", "9660.HK", "300209"):
            self.assertTrue(iu.is_ticker(s), s)

    def test_issuer_names_rejected(self):
        for s in ("ALPHABET INC", "PFIZER INC", "DELTA AIR LINES INC"):
            self.assertFalse(iu.is_ticker(s), s)

    def test_cash_tokens_rejected(self):
        for s in ("USD", "CNY", "HKD", "现金"):
            self.assertFalse(iu.is_ticker(s), s)

    def test_empty_rejected(self):
        self.assertFalse(iu.is_ticker(""))
        self.assertFalse(iu.is_ticker(None))


class TestParseUniverse(unittest.TestCase):
    def test_dedup_across_sources(self):
        uni, sk = iu.parse_universe(
            ledger_syms=["AAPL", "KO", "USD"],
            pool_recs=[{"symbol": "AAPL"}, {"symbol": "603986"}, {"symbol": "ALPHABET INC"}],
            watchlist_items=[{"symbol": "KO"}])
        syms = [u["symbol"] for u in uni]
        self.assertEqual(syms, ["603986", "AAPL", "KO"])              # 去重 + 排序
        aapl = [u for u in uni if u["symbol"] == "AAPL"][0]
        self.assertEqual(aapl["sources"], ["候选池", "持仓"])          # 多源合并
        skipped = {x["symbol"] for x in sk}
        self.assertIn("USD", skipped)                                # 币种记号
        self.assertIn("ALPHABET INC", skipped)                       # 13F issuer 名

    def test_empty_all(self):
        uni, sk = iu.parse_universe([], [], [])
        self.assertEqual(uni, [])
        self.assertEqual(sk, [])


class TestParseYahooEvents(unittest.TestCase):
    def test_split_and_dividend(self):
        # 2022-07-18 GOOGL 20:1 拆股 (ts=1658102400) + 一笔分红
        result = {"events": {
            "splits": {"1658102400": {"numerator": 20, "denominator": 1, "splitRatio": "20:1"}},
            "dividends": {"1700000000": {"amount": 0.20}},
        }}
        recs = iu.parse_yahoo_events(result, "GOOGL")
        self.assertEqual(len(recs), 2)
        split = [r for r in recs if r["type"] == "split"][0]
        self.assertEqual(split["ratio"], 20.0)                       # num/den
        self.assertEqual(split["symbol"], "GOOGL")
        div = [r for r in recs if r["type"] == "dividend"][0]
        self.assertEqual(div["amount"], 0.20)

    def test_empty_events(self):
        self.assertEqual(iu.parse_yahoo_events({"events": {}}, "AAPL"), [])
        self.assertEqual(iu.parse_yahoo_events({}, "AAPL"), [])

    def test_bad_split_skipped(self):
        # denominator=0 应被跳过(不 ZeroDivision、不产脏数据)
        result = {"events": {"splits": {"1": {"numerator": 4, "denominator": 0}}}}
        self.assertEqual(iu.parse_yahoo_events(result, "X"), [])


class TestMergeActions(unittest.TestCase):
    def test_dedup_by_key(self):
        existing = [{"symbol": "AAPL", "type": "split", "date": "2020-08-31", "ratio": 4}]
        incoming = [
            {"symbol": "AAPL", "type": "split", "date": "2020-08-31", "ratio": 4},   # 重复
            {"symbol": "AAPL", "type": "dividend", "date": "2026-05-10", "amount": 0.25},  # 新
        ]
        new = iu.merge_actions(existing, incoming)
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]["type"], "dividend")

    def test_ratio_vs_amount_no_collision(self):
        # 同标的同日 split(ratio) 与 dividend(amount) 不应被误判为同一条
        recs = [{"symbol": "X", "type": "split", "date": "2026-01-01", "ratio": 2},
                {"symbol": "X", "type": "dividend", "date": "2026-01-01", "amount": 2}]
        new = iu.merge_actions([], recs)
        self.assertEqual(len(new), 2)


if __name__ == "__main__":
    unittest.main()
