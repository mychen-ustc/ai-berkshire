"""quant_metrics.py 回归测试（五指标纯函数，零依赖）。"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import quant_metrics as qm  # noqa: E402


class TestBeta(unittest.TestCase):
    def test_beta_one_when_identical(self):
        b = [0.01, -0.02, 0.03, 0.00, 0.015]
        self.assertAlmostEqual(qm.beta(b, b), 1.0, places=9)

    def test_beta_two_when_double(self):
        bench = [0.01, -0.02, 0.03, -0.01, 0.02]
        port = [2 * x for x in bench]                 # 组合=2×市场 → β=2
        self.assertAlmostEqual(qm.beta(port, bench), 2.0, places=6)

    def test_beta_half(self):
        bench = [0.02, -0.01, 0.03, -0.02, 0.01]
        port = [0.5 * x for x in bench]
        self.assertAlmostEqual(qm.beta(port, bench), 0.5, places=6)


class TestAlpha(unittest.TestCase):
    def test_zero_alpha_when_beta_explains(self):
        # 组合=市场(β=1),rf=0 → α应≈0
        bench = [0.01, -0.02, 0.03, -0.01, 0.02]
        a = qm.alpha_annual(bench, bench, rf_annual=0.0, ppy=52)
        self.assertAlmostEqual(a, 0.0, places=6)

    def test_positive_alpha(self):
        # 组合每期比市场多赚 0.005(β=1) → 年化α≈0.005×52
        bench = [0.01, -0.02, 0.03, -0.01, 0.02]
        port = [x + 0.005 for x in bench]
        a = qm.alpha_annual(port, bench, rf_annual=0.0, ppy=52)
        self.assertAlmostEqual(a, 0.005 * 52, places=4)


class TestSharpe(unittest.TestCase):
    def test_sharpe_formula(self):
        rets = [0.01, 0.02, 0.015, 0.005, 0.01]
        m = qm._mean(rets)
        sd = qm._std(rets)
        expected = (m - 0.04 / 52) / sd * math.sqrt(52)
        self.assertAlmostEqual(qm.sharpe(rets, 0.04, 52), expected, places=9)

    def test_none_zero_vol(self):
        self.assertIsNone(qm.sharpe([0.01, 0.01, 0.01], 0.04, 52))


class TestMaxDrawdown(unittest.TestCase):
    def test_known_drawdown(self):
        # +10% 然后 -50% → 从峰值(1.1)跌到 0.55 → -50%
        mdd = qm.max_drawdown([0.10, -0.50])
        self.assertAlmostEqual(mdd, 0.55 / 1.10 - 1, places=9)

    def test_no_drawdown_when_monotone(self):
        self.assertAlmostEqual(qm.max_drawdown([0.01, 0.02, 0.03]), 0.0, places=9)


class TestInformationRatio(unittest.TestCase):
    def test_ir_positive(self):
        bench = [0.01, -0.02, 0.03, -0.01, 0.02]
        port = [x + 0.005 for x in bench]           # 恒定正超额 → 跟踪误差≈0 → IR极大
        ir = qm.information_ratio(port, bench, 52)
        self.assertIsNone(ir) if ir is None else self.assertGreater(ir, 0)

    def test_ir_zero_when_identical(self):
        b = [0.01, -0.02, 0.03]
        self.assertIsNone(qm.information_ratio(b, b, 52))   # 无主动收益→跟踪误差0→None

    def test_tracking_error(self):
        bench = [0.01, -0.02, 0.03, -0.01]
        port = [0.02, -0.01, 0.04, 0.00]            # active = +0.01 每期(恒定)
        te = qm.tracking_error(port, bench, 52)
        self.assertAlmostEqual(te, 0.0, places=9)   # 恒定超额→跟踪误差0


class TestEvaluate(unittest.TestCase):
    def test_evaluate_keys_and_verdicts(self):
        bench = [0.01, -0.02, 0.03, -0.01, 0.02, 0.01, -0.015, 0.025]
        port = [1.2 * x + 0.003 for x in bench]
        res = qm.evaluate(port, bench, rf_annual=0.04, ppy=52)
        for k in ("beta", "alpha_annual", "sharpe", "max_drawdown", "information_ratio"):
            self.assertIn(k, res)
            self.assertIn(k if k != "alpha_annual" else "alpha", res["verdicts"])
        self.assertGreater(res["beta"], 1.0)         # 1.2×市场

    def test_defensive_verdict(self):
        self.assertIn("防御", qm._v_beta(0.7))
        self.assertIn("进攻", qm._v_beta(1.3))


if __name__ == "__main__":
    unittest.main()
