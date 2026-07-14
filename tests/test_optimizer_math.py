"""portfolio_optimizer 高级方法回归测试（矩阵求逆/最小方差/风险平价，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import portfolio_optimizer as po  # noqa: E402


class TestMatInverse(unittest.TestCase):
    def test_diagonal(self):
        inv = po.mat_inverse([[2.0, 0.0], [0.0, 4.0]])
        self.assertAlmostEqual(inv[0][0], 0.5, places=9)
        self.assertAlmostEqual(inv[1][1], 0.25, places=9)

    def test_inverse_identity(self):
        A = [[4.0, 2.0], [2.0, 3.0]]
        inv = po.mat_inverse(A)
        # A · A⁻¹ = I
        prod = [[sum(A[i][k] * inv[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
        self.assertAlmostEqual(prod[0][0], 1.0, places=9)
        self.assertAlmostEqual(prod[0][1], 0.0, places=9)

    def test_singular_raises(self):
        with self.assertRaises(ValueError):
            po.mat_inverse([[1.0, 1.0], [1.0, 1.0]])


class TestWeights(unittest.TestCase):
    def test_min_variance_favors_low_vol(self):
        w = po.min_variance_weights([[0.04, 0.0], [0.0, 0.01]])   # vol 20%/10%
        self.assertAlmostEqual(w[0], 0.2, places=6)               # Σ⁻¹1 归一
        self.assertAlmostEqual(w[1], 0.8, places=6)

    def test_risk_parity_diagonal_equals_inverse_vol(self):
        w = po.risk_parity_weights([[0.04, 0.0], [0.0, 0.01]])    # 对角→逆波动 1/0.2:1/0.1
        self.assertAlmostEqual(w[0], 1 / 3, places=4)
        self.assertAlmostEqual(w[1], 2 / 3, places=4)

    def test_risk_parity_equal_contribution(self):
        cov = [[0.04, 0.006], [0.006, 0.01]]
        w = po.risk_parity_weights(cov)
        mrc = [sum(cov[i][j] * w[j] for j in range(2)) for i in range(2)]
        rc = [w[i] * mrc[i] for i in range(2)]
        self.assertAlmostEqual(rc[0], rc[1], places=6)            # 等风险贡献

    def test_inverse_vol(self):
        w = po.inverse_vol_weights({"A": 0.2, "B": 0.1})
        self.assertAlmostEqual(w["A"], 1 / 3, places=6)


if __name__ == "__main__":
    unittest.main()
