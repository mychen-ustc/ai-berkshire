"""decision_journal.py 回归测试（stdlib unittest，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import decision_journal as dj  # noqa: E402


class TestBrier(unittest.TestCase):
    def test_perfect(self):
        self.assertEqual(dj.brier_score([(1.0, 1), (0.0, 0)]), 0.0)

    def test_coin_flip(self):
        self.assertEqual(dj.brier_score([(0.5, 1), (0.5, 0)]), 0.25)

    def test_mixed(self):
        # (0.09 + 0.09 + 0.49)/3
        self.assertAlmostEqual(dj.brier_score([(0.7, 1), (0.7, 1), (0.7, 0)]), 0.67 / 3, places=9)

    def test_empty(self):
        self.assertIsNone(dj.brier_score([]))


class TestCalibrationBuckets(unittest.TestCase):
    def test_bucketing(self):
        preds = [(0.1, 0), (0.15, 0), (0.7, 1), (0.7, 0)]
        buckets = dict((b[0], b) for b in dj.calibration_buckets(preds))
        # 0-20% 桶: 2 个, 预测均值 0.125, 实际命中 0
        self.assertIn("0%-20%", buckets)
        self.assertEqual(buckets["0%-20%"][1], 2)
        self.assertAlmostEqual(buckets["0%-20%"][3], 0.0)
        # 60-80% 桶: 2 个, 实际命中 0.5
        self.assertAlmostEqual(buckets["60%-80%"][3], 0.5)


if __name__ == "__main__":
    unittest.main()
