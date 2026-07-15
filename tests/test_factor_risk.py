"""factor_risk.py 回归测试（因子风险分解纯函数，合成数据，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import factor_risk as fr  # noqa: E402


class TestOLS(unittest.TestCase):
    def test_exact_recovery(self):
        # r = X·f_true 精确 → OLS 应还原 f_true,残差≈0
        X = [[1, 0], [0, 1], [1, 1]]
        f_true = [0.02, -0.01]
        r = [sum(X[i][k] * f_true[k] for k in range(2)) for i in range(3)]
        f, resid = fr.ols_factor_returns(X, r)
        self.assertAlmostEqual(f[0], 0.02, places=6)
        self.assertAlmostEqual(f[1], -0.01, places=6)
        self.assertTrue(all(abs(x) < 1e-9 for x in resid))


class TestCov(unittest.TestCase):
    def test_diagonal(self):
        # 两因子独立:第一列方差大、第二列小,协方差≈0
        series = [[1.0, 0.1], [-1.0, -0.1], [1.0, 0.1], [-1.0, -0.1]]
        cov = fr.cov_matrix(series)
        self.assertGreater(cov[0][0], cov[1][1])
        self.assertAlmostEqual(cov[0][1], cov[1][0], places=9)   # 对称


class TestDecompose(unittest.TestCase):
    def test_split(self):
        # e=[1,0], F=diag(0.04,0.01), w=[0.5,0.5], spec=[0.02,0.02], ann=1
        d = fr.decompose([1.0, 0.0], [[0.04, 0.0], [0.0, 0.01]], [0.5, 0.5], [0.02, 0.02], ann=1)
        self.assertAlmostEqual(d["factor_var"], 0.04, places=9)       # e'Fe
        self.assertAlmostEqual(d["specific_var"], 0.25 * 0.02 * 2, places=9)  # Σw²D = 0.01
        self.assertAlmostEqual(d["total_var"], 0.05, places=9)
        self.assertAlmostEqual(d["factor_pct"], 0.8, places=6)

    def test_per_factor_sums_to_factor_var(self):
        d = fr.decompose([0.5, 0.3], [[0.04, 0.01], [0.01, 0.02]], [1.0], [0.0], ann=1)
        self.assertAlmostEqual(sum(d["per_factor"]), d["factor_var"], places=9)

    def test_zero_total_safe(self):
        d = fr.decompose([0.0, 0.0], [[0.04, 0], [0, 0.01]], [1.0], [0.0], ann=1)
        self.assertIsNone(d["factor_pct"])


if __name__ == "__main__":
    unittest.main()
