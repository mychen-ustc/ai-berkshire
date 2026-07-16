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
        # 同标的同日 split 与 dividend 不应被误判为同一条(类型不同)
        recs = [{"symbol": "X", "type": "split", "date": "2026-01-01", "ratio": 2},
                {"symbol": "X", "type": "dividend", "date": "2026-01-01", "amount": 2}]
        new = iu.merge_actions([], recs)
        self.assertEqual(len(new), 2)

    def test_float_jitter_deduped(self):
        # 同一(标的,类型,除息日)的分红,源返回微小浮点抖动(~1e-5),必须视为同一条(否则每次摄取膨胀)
        existing = [{"symbol": "09999.HK", "type": "dividend", "date": "2020-06-11", "amount": 0.3637593}]
        incoming = [{"symbol": "09999.HK", "type": "dividend", "date": "2020-06-11", "amount": 0.36373422}]
        self.assertEqual(iu.merge_actions(existing, incoming), [])   # 抖动值不产生新记录


class TestParseAshareBonus(unittest.TestCase):
    def test_dividend_per_ten_to_per_share(self):
        # 东财"10派0.22元"→ PRETAX_BONUS_RMB=0.22(每10股)→ 每股 0.022
        rows = [{"EX_DIVIDEND_DATE": "2026-06-10 00:00:00", "PRETAX_BONUS_RMB": 0.22}]
        out = iu.parse_ashare_bonus(rows, "002185.SZ")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["type"], "dividend")
        self.assertAlmostEqual(out[0]["amount"], 0.022)
        self.assertEqual(out[0]["date"], "2026-06-10")             # 除权除息日

    def test_song_zhuan_to_split_ratio(self):
        # 10送5转3 → split ratio = (10+5+3)/10 = 1.8
        rows = [{"EX_DIVIDEND_DATE": "2012-07-12", "BONUS_RATIO": 5, "IT_RATIO": 3}]
        out = iu.parse_ashare_bonus(rows, "002185.SZ")
        split = [r for r in out if r["type"] == "split"][0]
        self.assertAlmostEqual(split["ratio"], 1.8)

    def test_dividend_and_split_same_date(self):
        rows = [{"EX_DIVIDEND_DATE": "2012-07-12", "PRETAX_BONUS_RMB": 1.0,
                 "BONUS_RATIO": 6, "IT_RATIO": 0}]
        out = iu.parse_ashare_bonus(rows, "X.SZ")
        self.assertEqual({r["type"] for r in out}, {"dividend", "split"})

    def test_no_ex_date_skipped(self):
        # 预案未实施(无除息日)→ 跳过,不产脏记录
        rows = [{"EX_DIVIDEND_DATE": "", "PRETAX_BONUS_RMB": 0.5},
                {"EX_DIVIDEND_DATE": None, "BONUS_RATIO": 10}]
        self.assertEqual(iu.parse_ashare_bonus(rows, "X.SZ"), [])


if __name__ == "__main__":
    unittest.main()
