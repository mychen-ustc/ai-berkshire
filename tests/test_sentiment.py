"""sentiment.py 回归测试（stdlib unittest，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import sentiment as st  # noqa: E402


class TestScoreUtils(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(st.clamp(150), 100.0)
        self.assertEqual(st.clamp(-5), 0.0)
        self.assertEqual(st.clamp(50), 50.0)

    def test_label_boundaries(self):
        self.assertIn("极度贪婪", st._label(80))
        self.assertEqual(st._label(65), "贪婪")
        self.assertEqual(st._label(50), "中性")
        self.assertEqual(st._label(30), "恐惧")
        self.assertIn("极度恐惧", st._label(10))

    def test_composite_ignores_none(self):
        self.assertEqual(st._composite({"a": 100, "b": None, "c": 0}), 50.0)
        self.assertIsNone(st._composite({"a": None}))


class TestTextSentiment(unittest.TestCase):
    def test_positive(self):
        r = st.text_sentiment("业绩超预期，公司回购增持创新高")
        self.assertGreater(r["score"], 0.2)
        self.assertEqual(r["label"], "正面")
        self.assertGreater(r["pos"], 0)

    def test_negative(self):
        r = st.text_sentiment("业绩暴跌不及预期，遭立案调查，商誉减值爆雷")
        self.assertLess(r["score"], -0.2)
        self.assertEqual(r["label"], "负面")

    def test_negation_flip(self):
        r = st.text_sentiment("公司未减持")           # 减持(负) 经否定 → 正面计数
        self.assertGreaterEqual(r["pos"], 1)
        self.assertEqual(r["neg"], 0)

    def test_empty(self):
        r = st.text_sentiment("今天天气不错")
        self.assertEqual(r["score"], 0.0)
        self.assertEqual(r["label"], "无情感词")


if __name__ == "__main__":
    unittest.main()
