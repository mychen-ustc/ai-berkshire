"""review.py 回归测试（stdlib unittest，零依赖，纯 holding_flags/build_actions）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import review as rv  # noqa: E402


class TestFlags(unittest.TestCase):
    def test_main_flow_distribution_red(self):
        h = {"tech": "偏多 · MACD空头 · 中低位", "main_flow": "主力净流出·近5日 -139.6亿（派发）",
             "senti": {"score": 54}}
        flags = rv.holding_flags(h)
        self.assertTrue(any(lv == "🔴" and "派发" in msg for lv, msg in flags))

    def test_extreme_greed_yellow(self):
        flags = rv.holding_flags({"tech": "上升趋势", "senti": {"score": 84}})
        self.assertTrue(any(lv == "🟡" for lv, _ in flags))

    def test_extreme_fear_green(self):
        flags = rv.holding_flags({"tech": "偏空 · 深跌", "senti": {"score": 15}})
        levels = [lv for lv, _ in flags]
        self.assertIn("🟢", levels)      # 极度恐惧
        self.assertIn("🔴", levels)      # 同时技术转弱

    def test_revision_cut_red(self):
        flags = rv.holding_flags({"tech": "震荡", "consensus": {"revision": "下修"}, "senti": {"score": 50}})
        self.assertTrue(any("下修" in msg for _, msg in flags))

    def test_normal_no_flags(self):
        self.assertEqual(rv.holding_flags({"tech": "上升趋势 · MACD多头", "senti": {"score": 55}}), [])


class TestActions(unittest.TestCase):
    def test_build_actions(self):
        holdings = [{"symbol": "603986", "name": "兆易创新",
                     "tech": "偏多", "main_flow": "主力净流出（派发）", "senti": {"score": 54}}]
        due = [{"symbol": "AAPL", "name": "苹果", "review_date": "2026-07-13"}]
        imminent = [{"date": "2026-07-22", "symbol": "GOOGL", "detail": "Q2财报"}]
        acts = rv.build_actions(holdings, due, imminent)
        self.assertTrue(any("复审到期" in a and "AAPL" in a for a in acts))
        self.assertTrue(any("临近催化剂" in a and "GOOGL" in a for a in acts))
        self.assertTrue(any("红线关注" in a and "603986" in a for a in acts))

    def test_empty_actions(self):
        holdings = [{"symbol": "VOO", "tech": "上升趋势", "senti": {"score": 55}}]
        self.assertEqual(rv.build_actions(holdings, [], []), [])


if __name__ == "__main__":
    unittest.main()
