"""news_engine.py 回归测试（stdlib unittest，零依赖，离线 fixture）。"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import news_engine as ne  # noqa: E402


class TestClassify(unittest.TestCase):
    def test_buyback_bullish(self):
        r = ne.classify("公司关于回购股份的公告")
        self.assertIn("回购", r["tags"])
        self.assertFalse(r["material"])
        self.assertEqual(r["direction"], "利好")

    def test_regulatory_material_bearish(self):
        r = ne.classify("公司收到中国证监会立案调查通知书")
        self.assertIn("监管处罚", r["tags"])
        self.assertTrue(r["material"])
        self.assertEqual(r["direction"], "利空")

    def test_ma_material(self):
        r = ne.classify("关于重大资产重组的进展公告")
        self.assertIn("并购重组", r["tags"])
        self.assertTrue(r["material"])

    def test_earnings_tag(self):
        r = ne.classify("2026年半年度业绩预增公告")
        self.assertIn("业绩", r["tags"])

    def test_other_when_no_match(self):
        r = ne.classify("关于完成工商变更登记的公告")
        self.assertEqual(r["tags"], ["其他"])


class TestParseAndSummarize(unittest.TestCase):
    FIXTURE = json.dumps({"data": {"list": [
        {"title_ch": "某公司关于回购股份的公告", "notice_date": "2026-07-01 00:00:00",
         "columns": [{"column_name": "股份回购"}], "art_code": "AN1"},
        {"title_ch": "某公司收到证监会立案调查通知书", "notice_date": "2026-06-20 00:00:00",
         "columns": [{"column_name": "风险提示"}], "art_code": "AN2"},
    ]}})

    def test_parse(self):
        anns = ne.parse_em_announcements(self.FIXTURE)
        self.assertEqual(len(anns), 2)
        self.assertEqual(anns[0]["date"], "2026-07-01")
        self.assertEqual(anns[0]["official_type"], "股份回购")

    def test_summarize(self):
        anns = ne.parse_em_announcements(self.FIXTURE)
        for a in anns:
            a.update(ne.classify(a["title"]))
        s = ne.summarize(anns)
        self.assertEqual(s["n"], 2)
        self.assertEqual(s["material"], 1)   # 立案调查=重大
        self.assertEqual(s["pos"], 1)        # 回购=利好
        self.assertEqual(s["neg"], 1)        # 立案=利空


if __name__ == "__main__":
    unittest.main()
