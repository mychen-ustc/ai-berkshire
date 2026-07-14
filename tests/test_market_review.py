"""market_review.py 回归测试（stdlib unittest，零依赖，纯 _breadth_word/synthesize/_chg）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import market_review as mr  # noqa: E402


class TestBreadthWord(unittest.TestCase):
    def test_all_up(self):
        self.assertEqual(mr._breadth_word([{"chg": 1.2}, {"chg": 0.3}]), "普涨")

    def test_all_down(self):
        self.assertEqual(mr._breadth_word([{"chg": -0.6}, {"chg": -0.5}]), "普跌")

    def test_mixed(self):
        self.assertEqual(mr._breadth_word([{"chg": 1.0}, {"chg": -1.0}]), "涨跌分化")

    def test_empty(self):
        self.assertEqual(mr._breadth_word([]), "—")


class TestChg(unittest.TestCase):
    def test_fmt(self):
        self.assertEqual(mr._chg(1.234), "+1.23%")
        self.assertEqual(mr._chg(-0.5), "-0.50%")
        self.assertEqual(mr._chg(None), "—")


class TestSynthesize(unittest.TestCase):
    def test_summary_bits(self):
        out = {
            "indices": [{"market": "A股", "chg": -0.6}, {"market": "A股", "chg": -0.5},
                        {"market": "美股", "chg": -0.3}],
            "breadth": {"limit_up": 29, "limit_down": 172, "label": "情绪偏冷（跌停占优/恐慌）"},
            "sentiment": {"US": {"score": 75, "label": "极度贪婪"}, "A": {"score": 54, "label": "中性"}},
            "macro": {"regime": "复苏"},
            "sectors": {"sectors": [{"sector": "医药商业"}, {"sector": "化学原料"}]},
        }
        s = mr.synthesize(out)
        self.assertIn("A股普跌", s)
        self.assertIn("美股普跌", s)
        self.assertIn("涨停29/跌停172", s)
        self.assertIn("情绪偏热(US)", s)
        self.assertIn("宏观复苏", s)
        self.assertIn("主线:医药商业/化学原料", s)


if __name__ == "__main__":
    unittest.main()
