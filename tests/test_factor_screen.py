import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import factor_screen as fs  # noqa: E402


class TestFamilyFDR(unittest.TestCase):
    def test_strong_survives_weak_rejected(self):
        # 家族:一个强 p 一个弱 p;BH-FDR 后强的应存活
        out = fs.apply_family_fdr({"a": 0.001, "b": 0.9}, alpha=0.10)
        self.assertTrue(out["a"]["survives"])
        self.assertFalse(out["b"]["survives"])

    def test_all_weak_none_survive(self):
        out = fs.apply_family_fdr({"a": 0.4, "b": 0.6, "c": 0.8}, alpha=0.10)
        self.assertFalse(any(v["survives"] for v in out.values()))

    def test_none_pvalue_marked_unsurvived(self):
        out = fs.apply_family_fdr({"a": 0.01, "b": None}, alpha=0.10)
        self.assertFalse(out["b"]["survives"])
        self.assertIn("reason", out["b"])

    def test_empty(self):
        out = fs.apply_family_fdr({}, alpha=0.10)
        self.assertEqual(out, {})


class TestDoubleGate(unittest.TestCase):
    def test_all_gates_pass(self):
        v = fs.double_gate_verdict("quality", oos_cagr=0.20, oos_p=0.01,
                                   net_excess=0.05, fdr_survives=True, power=0.8,
                                   min_material=0.03)
        self.assertTrue(v["pass"])
        self.assertTrue(all(v["gates"].values()))

    def test_fails_on_negative_net_excess(self):
        # 跑赢门槛但跑输基准 → 净超额门拒(揭穿"搭大盘便车")
        v = fs.double_gate_verdict("quality", oos_cagr=0.15, oos_p=0.01,
                                   net_excess=-0.01, fdr_survives=True, power=0.8)
        self.assertFalse(v["pass"])
        self.assertFalse(v["gates"]["net_excess"])

    def test_fails_on_fdr(self):
        v = fs.double_gate_verdict("size", oos_cagr=0.15, oos_p=0.20,
                                   net_excess=0.05, fdr_survives=False, power=0.8)
        self.assertFalse(v["pass"])
        self.assertFalse(v["gates"]["alpha_fdr"])

    def test_fails_on_power(self):
        v = fs.double_gate_verdict("lowvol", oos_cagr=0.15, oos_p=0.01,
                                   net_excess=0.05, fdr_survives=True, power=0.15)
        self.assertFalse(v["pass"])
        self.assertFalse(v["gates"]["power"])

    def test_fails_on_material(self):
        v = fs.double_gate_verdict("momentum", oos_cagr=0.01, oos_p=0.01,
                                   net_excess=0.05, fdr_survives=True, power=0.8,
                                   min_material=0.03)
        self.assertFalse(v["pass"])
        self.assertFalse(v["gates"]["material"])

    def test_none_inputs_safe(self):
        v = fs.double_gate_verdict("x", None, None, None, False, None)
        self.assertFalse(v["pass"])


if __name__ == "__main__":
    unittest.main()
