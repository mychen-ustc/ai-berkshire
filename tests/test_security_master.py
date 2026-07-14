"""security_master.py 回归测试（stdlib unittest，零依赖，纯函数）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import security_master as sm  # noqa: E402
import datalayer as dl  # noqa: E402


class TestIds(unittest.TestCase):
    def test_internal_id(self):
        self.assertEqual(sm.internal_id("A", "600519.SH"), "A-600519.SH")
        self.assertEqual(sm.internal_id("US", "AAPL"), "US-AAPL")

    def test_exchange_of(self):
        self.assertEqual(sm.exchange_of(dl.detect("600519")), "SSE")     # 沪
        self.assertEqual(sm.exchange_of(dl.detect("000858")), "SZSE")    # 深
        self.assertEqual(sm.exchange_of(dl.detect("0700.HK")), "HKEX")
        self.assertEqual(sm.exchange_of(dl.detect("AAPL")), "US")


class TestPointInTime(unittest.TestCase):
    SNAPS = [{"as_of": "2026-06-01", "fields": {"price": 100, "pe": 20}},
             {"as_of": "2026-07-01", "fields": {"price": 120, "pe": 18}}]

    def test_no_lookahead_before_any(self):
        r = sm.pit_latest(self.SNAPS, "2026-05-01")     # 早于所有快照
        self.assertEqual(r["fields"], {})
        self.assertIsNone(r["as_of_effective"])
        self.assertEqual(r["n_snapshots"], 0)

    def test_only_past_visible(self):
        r = sm.pit_latest(self.SNAPS, "2026-06-15")     # 只有 06-01 可见
        self.assertEqual(r["fields"]["price"], 100)
        self.assertEqual(r["as_of_effective"], "2026-06-01")

    def test_latest_wins(self):
        r = sm.pit_latest(self.SNAPS, "2026-07-14")     # 两条都可见,晚者覆盖
        self.assertEqual(r["fields"]["price"], 120)
        self.assertEqual(r["fields"]["pe"], 18)
        self.assertEqual(r["n_snapshots"], 2)


if __name__ == "__main__":
    unittest.main()
