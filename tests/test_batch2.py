"""批次2 工具回归测试（watchlist/catalysts/scenario/statement_model/industry_valuation）。

stdlib unittest，零依赖，纯逻辑 golden case。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import watchlist as wl  # noqa: E402
import catalysts as cal  # noqa: E402
import scenario as sc  # noqa: E402
import statement_model as sm  # noqa: E402
import industry_valuation as iv  # noqa: E402


class TestWatchlist(unittest.TestCase):
    def test_state_transitions(self):
        self.assertEqual(wl.next_state("candidate"), "holding")
        self.assertEqual(wl.prev_state("candidate"), "researching")
        self.assertEqual(wl.next_state("archived"), "archived")     # 末态封顶
        self.assertEqual(wl.prev_state("discovered"), "discovered")  # 首态封底

    def test_is_due(self):
        self.assertTrue(wl.is_due("2026-07-10", "2026-07-13"))
        self.assertFalse(wl.is_due("2026-08-01", "2026-07-13"))
        self.assertFalse(wl.is_due(None, "2026-07-13"))

    def test_transition_note(self):
        self.assertEqual(wl.transition_note("candidate", "holding"), "ok")
        self.assertIn("跳进", wl.transition_note("discovered", "holding"))
        self.assertIn("回退", wl.transition_note("holding", "screening"))


class TestCatalysts(unittest.TestCase):
    def test_days_between(self):
        self.assertEqual(cal._days_between("2026-07-13", "2026-07-22"), 9)

    def test_build_timeline(self):
        ev = [{"date": "2026-07-22", "symbol": "A", "type": "财报"},
              {"date": "2026-06-01", "symbol": "B", "type": "财报"},   # 过去,剔除
              {"date": "2027-01-01", "symbol": "C", "type": "财报"}]   # 太远,剔除
        tl = cal.build_timeline(ev, days=90, as_of="2026-07-13")
        self.assertEqual(len(tl), 1)
        self.assertEqual(tl[0]["symbol"], "A")
        self.assertTrue(tl[0]["imminent"])       # 9<=14


class TestScenario(unittest.TestCase):
    def test_analyze(self):
        r = sc.analyze([{"name": "bull", "prob": 0.3, "value": 160},
                        {"name": "base", "prob": 0.5, "value": 110},
                        {"name": "bear", "prob": 0.2, "value": 60}], price=100)
        self.assertAlmostEqual(r["ev"], 115.0, places=6)            # 48+55+12
        self.assertAlmostEqual(r["expected_return"], 0.15, places=6)
        self.assertAlmostEqual(r["p_loss"], 0.2, places=6)         # 仅 bear<100
        self.assertAlmostEqual(r["best_return"], 0.6, places=6)

    def test_normalizes_probs(self):
        r = sc.analyze([{"name": "a", "prob": 2, "value": 120},
                        {"name": "b", "prob": 2, "value": 80}], price=100)
        self.assertAlmostEqual(r["ev"], 100.0, places=6)           # 归一化后 0.5/0.5


class TestStatementModel(unittest.TestCase):
    def test_project_year1(self):
        r = sm.project(1000, 1, 0.15, 0.60, 0.35, 0.25, 0.04, 0.06, 0.10)[0]
        self.assertAlmostEqual(r["revenue"], 1150.0, places=6)
        self.assertAlmostEqual(r["ebit"], 287.5, places=6)          # 1150*(0.6-0.35)
        self.assertAlmostEqual(r["nopat"], 215.625, places=6)       # *0.75
        self.assertAlmostEqual(r["fcf"], 177.625, places=6)         # 215.625+46-69-15


class TestIndustryValuation(unittest.TestCase):
    def test_bank(self):
        r = iv.bank(0.15, 0.10, 0.03, bvps=20)
        self.assertAlmostEqual(r["justified_pb"], 12 / 7, places=6)  # (.15-.03)/(.10-.03)
        self.assertAlmostEqual(r["fair_value"], 12 / 7 * 20, places=6)

    def test_bank_diverges(self):
        with self.assertRaises(SystemExit):
            iv.bank(0.15, 0.02, 0.03)                                # COE<=g

    def test_saas(self):
        r = iv.saas(0.30, 0.15, ev_s=12)
        self.assertAlmostEqual(r["rule_of_40"], 45.0, places=6)
        self.assertIn("达标", r["health"])
        self.assertEqual(r["verdict"], "大致合理")                    # 12 in [9,13.5]

    def test_property_and_insurance(self):
        p = iv.property_nav(100, 70)
        self.assertAlmostEqual(p["premium_discount_pct"], -30.0, places=1)
        self.assertEqual(p["verdict"], "折价")
        ins = iv.insurance(50, 6, 45, nbv_multiple=10)
        self.assertAlmostEqual(ins["appraisal_value"], 110.0, places=6)
        self.assertAlmostEqual(ins["p_ev"], 0.9, places=6)


if __name__ == "__main__":
    unittest.main()
