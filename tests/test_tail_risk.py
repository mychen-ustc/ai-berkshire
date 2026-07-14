"""tail_risk.py 回归测试（stdlib unittest，零依赖，golden case）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import tail_risk as tr  # noqa: E402


class TestNormPpf(unittest.TestCase):
    def test_known(self):
        self.assertAlmostEqual(tr.norm_ppf(0.95), 1.6449, places=3)
        self.assertAlmostEqual(tr.norm_ppf(0.975), 1.9600, places=3)
        self.assertAlmostEqual(tr.norm_ppf(0.99), 2.3263, places=3)
        self.assertAlmostEqual(tr.norm_ppf(0.5), 0.0, places=6)


class TestVarCvar(unittest.TestCase):
    def test_var_cvar(self):
        # 20 个收益：-10%..+9%（每档 1%）
        rets = [(-10 + i) / 100 for i in range(20)]      # -0.10,-0.09,...,0.09
        v = tr.var_cvar(rets, 0.95)
        # 95%：下尾 5% → floor(0.05*20)-1 = 0 → sr[0]=-0.10 → hist_var=0.10
        self.assertAlmostEqual(v["hist_var"], 0.10, places=6)
        self.assertAlmostEqual(v["hist_cvar"], 0.10, places=6)   # 尾部仅 1 个=-0.10
        self.assertGreater(v["param_var"], 0)

    def test_too_short(self):
        self.assertIsNone(tr.var_cvar([0.01, -0.01], 0.95))


class TestStress(unittest.TestCase):
    def test_stress_market(self):
        s = tr.stress_market(0.8, shocks=(-0.10, -0.20))
        self.assertAlmostEqual(s[0]["port_impact"], -0.08, places=6)
        self.assertAlmostEqual(s[1]["port_impact"], -0.16, places=6)

    def test_reverse_stress(self):
        r = tr.reverse_stress(0.8, loss_targets=(-0.16,))
        self.assertAlmostEqual(r[0]["implied_market"], -0.20, places=6)   # -0.16/0.8

    def test_single_name(self):
        s = tr.single_name_shock({"AAPL": 0.4, "KO": 0.2}, drops=(-1.0,))
        self.assertEqual(s[0]["name"], "AAPL")                            # 最大权重
        self.assertAlmostEqual(s[0]["port_impact"], -0.4, places=6)       # 归零 → -40%

    def test_days_to_liquidate(self):
        # 持仓 1000万，日均额 1亿，20%参与 → 1000万/(0.2*1亿)=0.5天
        self.assertAlmostEqual(tr.days_to_liquidate(1e7, 1e8, 0.2), 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
