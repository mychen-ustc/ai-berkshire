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
        self.assertFalse(v["gates"]["net_excess_ew"])

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


class TestScreenVerdictThreeWay(unittest.TestCase):
    def test_low_power_is_inconclusive_not_reject(self):
        # 评审#功效核心修正:功效不足 → ⚪不可判定(非🔴拒),即便净超额为负
        v = fs.screen_verdict("q", oos_cagr=0.15, oos_p_excess=0.5, net_excess_ew=-0.03,
                              fdr_survives=False, power=0.08, mde=0.25, holdings=5)
        self.assertEqual(v["status"], "inconclusive")

    def test_powered_negative_excess_is_reject(self):
        # 功效够 + 相对同池等权跑输 → 才是真🔴拒
        v = fs.screen_verdict("q", oos_cagr=0.15, oos_p_excess=0.5, net_excess_ew=-0.03,
                              fdr_survives=False, power=0.9, mde=0.05, holdings=5)
        self.assertEqual(v["status"], "reject")
        self.assertFalse(v["econ_gates"]["net_excess_ew"])

    def test_powered_all_pass(self):
        v = fs.screen_verdict("q", oos_cagr=0.15, oos_p_excess=0.01, net_excess_ew=0.05,
                              fdr_survives=True, power=0.9, mde=0.05, holdings=8)
        self.assertEqual(v["status"], "pass")

    def test_thin_holdings_flagged(self):
        v = fs.screen_verdict("q", oos_cagr=0.15, oos_p_excess=0.5, net_excess_ew=0.01,
                              fdr_survives=True, power=0.08, mde=0.2, holdings=2)
        self.assertTrue(any("持仓仅 2" in r for r in v["reasons"]))


class TestSameOpportunityBenchmark(unittest.TestCase):
    def test_universe_ew_periods(self):
        prices = {"A": {"d0": 100.0, "d1": 110.0}, "B": {"d0": 100.0, "d1": 90.0}}
        ew = fs.universe_ew_periods(prices, ["A", "B"], ["d0", "d1"])
        self.assertEqual(len(ew), 1)
        self.assertAlmostEqual(ew[0]["net"], 0.0, places=6)   # +10% 与 −10% 等权=0

    def test_ew_skips_missing(self):
        prices = {"A": {"d0": 100.0, "d1": 110.0}, "B": {"d0": 100.0}}
        ew = fs.universe_ew_periods(prices, ["A", "B"], ["d0", "d1"])
        self.assertAlmostEqual(ew[0]["net"], 0.10, places=6)  # 只有 A 可用

    def test_paired_excess(self):
        fac = [{"d0": "d0", "net": 0.05}, {"d0": "d1", "net": 0.02}]
        bench = [{"d0": "d0", "net": 0.03}, {"d0": "d1", "net": 0.04}]
        ex = fs.paired_excess(fac, bench)
        self.assertAlmostEqual(ex[0], 0.02, places=6)
        self.assertAlmostEqual(ex[1], -0.02, places=6)


if __name__ == "__main__":
    unittest.main()
