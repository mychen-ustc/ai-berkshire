"""datalayer.py 回归测试（stdlib unittest，零依赖，全离线用 fixture）。"""
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import datalayer as dl  # noqa: E402

# A股为 14 位紧凑时间戳(真实格式)，港股为斜杠格式——两种都要能解析
TENCENT_A = ('v_sh600519="1~贵州茅台~600519~1204.98~1182.19~1182.20~52213~0~0~0~'
             '20260710161445~22.79~1.93~1208.00~1180.00~x~y";')
TENCENT_HK = ('v_hk00700="100~腾讯控股~00700~460.200~469.600~472.800~40440298.0~0~0~460.2~0~0~'
              '2026/07/10 16:08:46~-9.400~-2.00~473.600~458.800~x";')
YAHOO = ('{"chart":{"result":[{"meta":{"currency":"USD","symbol":"AAPL",'
         '"regularMarketPrice":250.5,"chartPreviousClose":248.0,"regularMarketTime":1783713601,'
         '"regularMarketDayHigh":252.0,"regularMarketDayLow":249.0,"regularMarketDayOpen":249.5,'
         '"fullExchangeName":"NasdaqGS","shortName":"Apple Inc."},'
         '"indicators":{"quote":[{"close":[248,249,250.5]}]}}]}}')
SINA_A = 'var hq_str_sh600519="贵州茅台,1182.200,1182.190,1204.980,1208.0,1180.0,z";'
SINA_HK = 'var hq_str_hk00700="TENCENT,腾讯控股,472.800,469.600,473.600,458.800,460.200,z";'
STOOQ = "Symbol,Date,Time,Open,High,Low,Close,Volume\nAAPL.US,2026-07-10,22:00:00,249.5,252.0,249.0,250.4,50000000"


class TestDetect(unittest.TestCase):
    def test_a_share_sh(self):
        d = dl.detect("600519")
        self.assertEqual((d["market"], d["symbol"], d["tencent"], d["yahoo"], d["currency"]),
                         ("A", "600519.SH", "sh600519", "600519.SS", "CNY"))

    def test_a_share_sz(self):
        self.assertEqual(dl.detect("000001")["tencent"], "sz000001")

    def test_a_share_bj(self):
        self.assertEqual(dl.detect("830799")["symbol"], "830799.BJ")

    def test_a_share_with_suffix(self):
        self.assertEqual(dl.detect("600519.SS")["tencent"], "sh600519")
        self.assertEqual(dl.detect("sz000001")["market"], "A")

    def test_hk(self):
        d = dl.detect("0700.HK")
        self.assertEqual((d["market"], d["symbol"], d["tencent"], d["yahoo"], d["currency"]),
                         ("HK", "0700.HK", "hk00700", "0700.HK", "HKD"))

    def test_us(self):
        d = dl.detect("AAPL")
        self.assertEqual((d["market"], d["symbol"], d["stooq"], d["currency"]),
                         ("US", "AAPL", "aapl.us", "USD"))


class TestParsers(unittest.TestCase):
    def test_tencent_a(self):
        p = dl.parse_tencent(TENCENT_A)
        self.assertEqual(p["name"], "贵州茅台")
        self.assertEqual(p["price"], 1204.98)
        self.assertEqual(p["prev_close"], 1182.19)
        self.assertEqual(p["high"], 1208.00)
        self.assertEqual(p["low"], 1180.00)
        self.assertEqual(p["as_of"], "2026-07-10 16:14:45")  # 14位紧凑→ISO

    def test_tencent_hk(self):
        p = dl.parse_tencent(TENCENT_HK)
        self.assertEqual(p["name"], "腾讯控股")
        self.assertEqual(p["price"], 460.20)
        self.assertEqual(p["prev_close"], 469.60)
        self.assertEqual(p["low"], 458.80)

    def test_yahoo(self):
        p = dl.parse_yahoo(YAHOO)
        self.assertEqual(p["price"], 250.5)
        self.assertEqual(p["currency"], "USD")
        self.assertEqual(p["prev_close"], 248.0)
        self.assertTrue(p["as_of"].startswith("2026-"))

    def test_sina_a(self):
        self.assertEqual(dl.parse_sina(SINA_A, "A"), 1204.98)

    def test_sina_hk(self):
        self.assertEqual(dl.parse_sina(SINA_HK, "HK"), 460.20)

    def test_stooq(self):
        self.assertEqual(dl.parse_stooq(STOOQ), 250.4)

    def test_em_kline(self):
        text = ('{"data":{"code":"600519","market":1,"name":"贵州茅台","klines":['
                '"2026-06-26,1186.29,1168.63,1235.98,1168.10,260104,3.1e10",'
                '"2026-07-10,1186.00,1204.98,1215.00,1170.28,180420,2.1e10"]}}')
        name, pts = dl.parse_em_kline(text)
        self.assertEqual(name, "贵州茅台")
        self.assertEqual(pts, [("2026-06-26", 1168.63), ("2026-07-10", 1204.98)])  # 取 close

    def test_yahoo_history_prefers_adjclose(self):
        text = ('{"chart":{"result":[{"timestamp":[1625011200,1625616000],'
                '"indicators":{"quote":[{"close":[140.0,142.0]}],'
                '"adjclose":[{"adjclose":[138.5,141.0]}]}}]}}')
        pts = dl.parse_yahoo_history(text)
        self.assertEqual([p[1] for p in pts], [138.5, 141.0])  # 用前复权 adjclose 而非 close


class TestCrossCheck(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(dl.cross_check(100, 100.5)["status"], "ok")

    def test_conflict(self):
        cc = dl.cross_check(100, 102)
        self.assertEqual(cc["status"], "conflict")
        self.assertAlmostEqual(cc["divergence_pct"], 2.0, places=6)

    def test_single_source(self):
        self.assertEqual(dl.cross_check(100, None)["status"], "single-source")


class TestQualityGate(unittest.TestCase):
    def test_ok(self):
        env = {"price": 100, "as_of": "2026-07-11 10:00:00", "cross_check": {"status": "ok"}}
        self.assertEqual(dl.assess_quality(env, now=datetime(2026, 7, 11))["status"], "ok")

    def test_missing_price_warn(self):
        env = {"price": None, "as_of": "2026-07-11", "cross_check": {"status": "ok"}}
        q = dl.assess_quality(env, now=datetime(2026, 7, 11))
        self.assertEqual(q["status"], "warn")

    def test_stale(self):
        env = {"price": 100, "as_of": "2026-06-01", "cross_check": {"status": "ok"}}
        self.assertEqual(dl.assess_quality(env, now=datetime(2026, 7, 11))["status"], "stale")

    def test_conflict_warn(self):
        env = {"price": 100, "as_of": "2026-07-11",
               "cross_check": {"status": "conflict", "divergence_pct": 3.0}}
        self.assertEqual(dl.assess_quality(env, now=datetime(2026, 7, 11))["status"], "warn")


class TestSnapshotCache(unittest.TestCase):
    def test_round_trip(self):
        env = {"symbol": "600519.SH", "price": 1204.98, "market": "A", "quality": {"status": "ok"}}
        with tempfile.TemporaryDirectory() as tmp:
            orig = dl.CACHE_DIR
            dl.CACHE_DIR = tmp
            try:
                dl.save_snapshot(env)
                loaded = dl.load_snapshot("600519")
            finally:
                dl.CACHE_DIR = orig
        self.assertEqual(loaded["price"], 1204.98)
        self.assertEqual(loaded["symbol"], "600519.SH")


if __name__ == "__main__":
    unittest.main()
