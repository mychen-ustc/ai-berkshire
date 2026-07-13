"""macro_regime.py 回归测试（stdlib unittest，零依赖，纯 classify）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import macro_regime as mr  # noqa: E402


def pmi(make):
    return {"make": make, "make_prev": 50.0, "nmake": 50.0, "time": "T"}


def cpi(yoy, prev):
    return {"yoy": yoy, "yoy_prev": prev, "mom": 0.0, "time": "T"}


class TestClassify(unittest.TestCase):
    def test_recovery(self):        # 增长↑(PMI≥50) 通胀↓(CPI回落)
        r, _, _, _ = mr.classify(pmi(52), cpi(1.0, 1.5))
        self.assertEqual(r, "复苏")

    def test_overheat(self):        # 增长↑ 通胀↑
        r, _, _, _ = mr.classify(pmi(52), cpi(2.0, 1.5))
        self.assertEqual(r, "过热")

    def test_stagflation(self):     # 增长↓(PMI<50) 通胀↑
        r, _, _, _ = mr.classify(pmi(48), cpi(2.0, 1.5))
        self.assertEqual(r, "滞胀")

    def test_recession(self):       # 增长↓ 通胀↓
        r, _, _, _ = mr.classify(pmi(48), cpi(1.0, 1.5))
        self.assertEqual(r, "衰退")


if __name__ == "__main__":
    unittest.main()
