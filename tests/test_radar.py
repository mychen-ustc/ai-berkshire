"""radar.py 回归测试（stdlib unittest，零依赖，纯 _norm_code/merge_leads）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import radar as rad  # noqa: E402


class TestNormCode(unittest.TestCase):
    def test_a_share(self):
        self.assertEqual(rad._norm_code("603986"), "603986")
        self.assertEqual(rad._norm_code("SH600519"), "600519")
        self.assertEqual(rad._norm_code("sz000858"), "000858")

    def test_non_a(self):
        self.assertEqual(rad._norm_code("9660.HK"), "9660.HK")   # 港股不与A股6位撞
        self.assertEqual(rad._norm_code("AAPL"), "AAPL")


class TestMergeLeads(unittest.TestCase):
    DRAGON = [{"code": "688072", "name": "拓荆科技", "change": 1.6, "explain": "4家机构买入，成功率42%"},
              {"code": "603986", "name": "兆易创新", "change": 5.0, "explain": "2家机构买入"}]
    LIMITUP = [{"code": "300001", "name": "题材股", "lbc": 3, "sector": "半导体", "turnover": 25.0, "zdp": 20.0},
               {"code": "688072", "name": "拓荆科技", "lbc": 1, "sector": "半导体设备", "turnover": 8.0, "zdp": 1.6},
               {"code": "600001", "name": "单板股", "lbc": 1, "sector": "银行", "turnover": 5.0, "zdp": 10.0}]

    def test_merge_and_exclude(self):
        leads = rad.merge_leads(self.DRAGON, self.LIMITUP, exclude={"603986"})
        codes = [x["code"] for x in leads]
        self.assertIn("688072", codes)           # 龙虎榜机构买入(强)
        self.assertNotIn("603986", codes)         # 被 exclude(已持有)
        self.assertIn("300001", codes)            # 3连板题材(弱)
        self.assertNotIn("600001", codes)         # 仅1连板,不入选

    def test_strength_order_and_sector_lookup(self):
        leads = rad.merge_leads(self.DRAGON, self.LIMITUP, exclude=set())
        self.assertEqual(leads[0]["code"], "688072")      # strength 3 排最前
        self.assertEqual(leads[0]["strength"], 3)
        self.assertEqual(leads[0]["sector"], "半导体设备")  # 从涨停池补板块
        # 兆易(龙虎榜,强) 也在;题材股 strength 1 靠后
        self.assertTrue(leads[-1]["strength"] <= leads[0]["strength"])

    def test_no_double_count(self):
        leads = rad.merge_leads(self.DRAGON, self.LIMITUP, exclude=set())
        codes = [x["code"] for x in leads]
        self.assertEqual(codes.count("688072"), 1)        # 龙虎榜+涨停都有,只计一次


if __name__ == "__main__":
    unittest.main()
