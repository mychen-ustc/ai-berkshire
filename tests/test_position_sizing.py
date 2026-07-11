"""position_sizing.py 回归测试（stdlib unittest，零依赖）。"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import position_sizing as ps  # noqa: E402


class TestKelly(unittest.TestCase):
    def test_standard(self):
        # 0.6 - 0.4/3
        self.assertAlmostEqual(ps.kelly_fraction(0.6, 3), 0.6 - 0.4 / 3, places=10)

    def test_zero_edge(self):
        self.assertAlmostEqual(ps.kelly_fraction(0.5, 1), 0.0, places=10)

    def test_certain_win(self):
        self.assertAlmostEqual(ps.kelly_fraction(1.0, 1), 1.0, places=10)

    def test_negative_edge_clamped(self):
        self.assertEqual(ps.kelly_fraction(0.4, 1), 0.0)  # 会是 -0.2 → 夹到 0

    def test_bad_odds(self):
        self.assertEqual(ps.kelly_fraction(0.6, 0), 0.0)


class TestRecommendWithIPS(unittest.TestCase):
    def test_capped_by_ips(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"position_limits": {"single_name_max_pct": 10}, "status": "test"}, f)
            path = f.name
        try:
            r = ps.recommend(0.6, 3, fraction=0.5, policy_path=path)
            self.assertAlmostEqual(r["full_kelly"], 0.6 - 0.4 / 3, places=10)
            self.assertAlmostEqual(r["fractional"], (0.6 - 0.4 / 3) * 0.5, places=10)
            self.assertAlmostEqual(r["ips_cap"], 0.10, places=10)
            self.assertAlmostEqual(r["recommended"], 0.10, places=10)  # 半凯利23% > 10% 上限
            self.assertTrue(r["capped_by_ips"])
        finally:
            os.unlink(path)

    def test_no_policy_no_cap(self):
        r = ps.recommend(0.6, 3, fraction=0.5, policy_path="/nonexistent.json")
        self.assertIsNone(r["ips_cap"])
        self.assertAlmostEqual(r["recommended"], r["fractional"], places=10)
        self.assertFalse(r["capped_by_ips"])


if __name__ == "__main__":
    unittest.main()
