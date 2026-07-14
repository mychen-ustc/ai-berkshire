"""factor_library.py 回归测试（横截面因子标准化纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import factor_library as fl  # noqa: E402


class TestZScore(unittest.TestCase):
    def test_mean0_std1(self):
        z = fl.zscore([1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertAlmostEqual(sum(z) / len(z), 0.0, places=9)
        # 样本标准差归一
        mu = sum(z) / len(z)
        var = sum((x - mu) ** 2 for x in z) / (len(z) - 1)
        self.assertAlmostEqual(var, 1.0, places=6)

    def test_none_preserved(self):
        z = fl.zscore([1.0, None, 3.0])
        self.assertIsNone(z[1])
        self.assertEqual(len(z), 3)

    def test_zero_std(self):
        z = fl.zscore([5.0, 5.0, 5.0])
        self.assertEqual(z, [0.0, 0.0, 0.0])

    def test_higher_raw_higher_z(self):
        z = fl.zscore([10.0, 20.0, 30.0])
        self.assertLess(z[0], z[1])
        self.assertLess(z[1], z[2])


class TestWinsorize(unittest.TestCase):
    def test_clips_outlier(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0, 100.0]    # 100 是极端值; MAD>0
        w = fl.winsorize(vals, n_mad=3.0)
        self.assertLess(w[-1], 100.0)              # 被截断
        self.assertGreaterEqual(w[-1], 5.0)        # 但不低于正常上界

    def test_none_preserved(self):
        w = fl.winsorize([1.0, None, 2.0, 3.0, 4.0])
        self.assertIsNone(w[1])

    def test_small_sample_untouched(self):
        self.assertEqual(fl.winsorize([1.0, 2.0]), [1.0, 2.0])


class TestPortfolioExposure(unittest.TestCase):
    def test_weighted_sum(self):
        z = {"value": [1.0, -1.0], "growth": [2.0, 0.0]}
        exp = fl.portfolio_exposure(z, [0.5, 0.5])
        self.assertAlmostEqual(exp["value"], 0.0, places=9)   # (1-1)/2
        self.assertAlmostEqual(exp["growth"], 1.0, places=9)  # (2+0)/2

    def test_none_reweighted(self):
        # 一只在 value 上缺失 → 只按有效权重归一
        z = {"value": [2.0, None]}
        exp = fl.portfolio_exposure(z, [0.4, 0.6])
        self.assertAlmostEqual(exp["value"], 2.0, places=9)   # 只剩第一只,权重归一

    def test_all_none(self):
        exp = fl.portfolio_exposure({"value": [None, None]}, [0.5, 0.5])
        self.assertIsNone(exp["value"])


class TestComposite(unittest.TestCase):
    def test_weighted_factors(self):
        z = {"value": [1.0, 0.0], "growth": [0.0, 2.0]}
        sc = fl.composite_score(z, {"value": 1.0, "growth": 1.0})
        self.assertAlmostEqual(sc[0], 0.5, places=9)   # (1+0)/2
        self.assertAlmostEqual(sc[1], 1.0, places=9)   # (0+2)/2


class TestFactorCorr(unittest.TestCase):
    def test_perfect_correlation(self):
        z = {"a": [1.0, 2.0, 3.0], "b": [2.0, 4.0, 6.0]}   # b=2a → corr +1
        cor = fl.factor_correlation(z)
        self.assertAlmostEqual(cor[("a", "b")], 1.0, places=6)

    def test_standardize_pipeline(self):
        # 去极值+标准化联动：极端值不应主导 z 分
        z = fl.standardize_factor([1.0, 2.0, 3.0, 4.0, 1000.0])
        self.assertIsNotNone(z[-1])
        self.assertLess(z[-1], 5.0)   # 极端值被 winsorize 后 z 分有界


if __name__ == "__main__":
    unittest.main()
