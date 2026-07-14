"""error_library.py 回归测试（学习闭环纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import error_library as el  # noqa: E402


class TestFrequency(unittest.TestCase):
    def test_pattern_frequency(self):
        pms = [{"patterns": ["growth_trap", "moat_misjudge"]},
               {"patterns": ["growth_trap"]},
               {"patterns": ["anchoring"]}]
        freq = el.pattern_frequency(pms)
        self.assertEqual(freq["growth_trap"], 2)
        self.assertEqual(freq["moat_misjudge"], 1)
        self.assertEqual(freq["anchoring"], 1)

    def test_empty(self):
        self.assertEqual(el.pattern_frequency([]), {})


class TestCalibration(unittest.TestCase):
    def _d(self, conv, p, hit):
        return {"status": "resolved", "conviction": conv, "p_base": p,
                "resolved": {"hit": hit}}

    def test_overconfidence_gap_positive(self):
        # 预测均值 0.8，实际命中 0.5 → 过度自信 +0.3
        ds = [self._d(4, 0.8, True), self._d(4, 0.8, False),
              self._d(4, 0.8, True), self._d(4, 0.8, False)]
        gap = el.overconfidence_gap(ds)
        self.assertAlmostEqual(gap, 0.3, places=6)

    def test_overconfidence_none_when_empty(self):
        self.assertIsNone(el.overconfidence_gap([]))

    def test_overconfidence_ignores_open(self):
        ds = [{"status": "open", "p_base": 0.9}]
        self.assertIsNone(el.overconfidence_gap(ds))

    def test_category_bias_miss_rate(self):
        ds = [self._d(5, 0.9, False), self._d(5, 0.9, False), self._d(5, 0.9, True),
              self._d(3, 0.6, True)]
        cb = dict((c, (n, miss)) for c, n, miss in el.category_bias(ds))
        self.assertAlmostEqual(cb[5][1], 2 / 3, places=6)   # 信心5落空率 2/3
        self.assertAlmostEqual(cb[3][1], 0.0, places=6)     # 信心3落空率 0

    def test_seed_has_all_categories(self):
        cats = {p["category"] for p in el._seed()}
        for expected in ("估值", "竞争格局", "管理层", "宏观", "心理偏差", "组合"):
            self.assertIn(expected, cats)


if __name__ == "__main__":
    unittest.main()
