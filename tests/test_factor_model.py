"""factor_model.py 回归测试（stdlib unittest，零依赖，golden case 可手算）。"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import factor_model as fm  # noqa: E402


class TestJacobi(unittest.TestCase):
    def test_diagonal(self):
        eig, _ = fm.jacobi_eigen([[2.0, 0.0], [0.0, 1.0]])
        self.assertAlmostEqual(eig[0], 2.0, places=9)
        self.assertAlmostEqual(eig[1], 1.0, places=9)

    def test_correlation_2x2(self):
        eig, _ = fm.jacobi_eigen([[1.0, 0.8], [0.8, 1.0]])   # 特征值 1.8, 0.2
        self.assertAlmostEqual(eig[0], 1.8, places=6)
        self.assertAlmostEqual(eig[1], 0.2, places=6)

    def test_identity_3x3(self):
        eig, _ = fm.jacobi_eigen([[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]])
        for e in eig:
            self.assertAlmostEqual(e, 1.0, places=9)

    def test_eigenvector_orthonormal(self):
        eig, vecs = fm.jacobi_eigen([[2.0, 1.0], [1.0, 2.0]])  # 特征值 3,1
        self.assertAlmostEqual(eig[0], 3.0, places=6)
        # 特征向量应单位化正交
        v0, v1 = vecs[0], vecs[1]
        self.assertAlmostEqual(v0[0] ** 2 + v0[1] ** 2, 1.0, places=6)
        self.assertAlmostEqual(v0[0] * v1[0] + v0[1] * v1[1], 0.0, places=6)


class TestPCA(unittest.TestCase):
    def test_neff_high_correlation(self):
        m = fm.pca_metrics([[1.0, 0.8], [0.8, 1.0]])
        # N_eff = (Σλ)² / Σλ² = 4 / (1.8²+0.2²) = 4/3.28
        self.assertAlmostEqual(m["n_eff"], 4 / 3.28, places=4)
        self.assertAlmostEqual(m["var_ratio"][0], 0.9, places=6)   # 1.8/2

    def test_neff_independent(self):
        m = fm.pca_metrics([[1.0, 0.0], [0.0, 1.0]])
        self.assertAlmostEqual(m["n_eff"], 2.0, places=6)          # 完全独立→N_eff=名义数

    def test_sign_align(self):
        self.assertEqual(fm.sign_align([-1.0, -1.0, 0.5]), [1.0, 1.0, -0.5])  # 多数负→翻正
        self.assertEqual(fm.sign_align([1.0, 1.0, -0.5]), [1.0, 1.0, -0.5])   # 多数正→不变


class TestCharacteristics(unittest.TestCase):
    def test_zscores(self):
        z = fm.zscores([1, 2, 3])
        self.assertAlmostEqual(z[1], 0.0, places=9)
        self.assertAlmostEqual(z[0], -1.224744871, places=6)
        self.assertAlmostEqual(z[2], 1.224744871, places=6)

    def test_zscores_handles_none(self):
        z = fm.zscores([None, 2, 4])
        self.assertEqual(z[0], 0.0)   # None → 0

    def test_momentum_sign(self):
        up = list(range(1, 101))
        self.assertGreater(fm.momentum_12_1(up), 0)          # 单调涨→正动量
        self.assertLess(fm.momentum_12_1(up[::-1]), 0)       # 单调跌→负动量
        self.assertIsNone(fm.momentum_12_1([1, 2, 3]))       # 数据不足


if __name__ == "__main__":
    unittest.main()
