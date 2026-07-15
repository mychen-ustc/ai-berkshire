"""edgar_financials.py 回归测试（年度点位去重纯函数，零依赖/无网络）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import edgar_financials as ef  # noqa: E402


class TestAnnualPoints(unittest.TestCase):
    def test_earliest_filing_kept(self):
        # 同一会计期(2024-09-28)在两次申报出现 → 取最早披露(首次可得,PIT)
        units = [
            {"form": "10-K", "fp": "FY", "end": "2024-09-28", "val": 93700, "filed": "2025-10-31", "fy": 2025},
            {"form": "10-K", "fp": "FY", "end": "2024-09-28", "val": 93700, "filed": "2024-11-01", "fy": 2024},
        ]
        pts = ef.annual_points(units)
        self.assertEqual(len(pts), 1)                      # 去重
        self.assertEqual(pts[0]["filed"], "2024-11-01")    # 取最早披露

    def test_only_10k_fy(self):
        # 季报(10-Q)/非FY 应被过滤
        units = [
            {"form": "10-Q", "fp": "Q3", "end": "2025-06-30", "val": 1, "filed": "2025-07-30"},
            {"form": "10-K", "fp": "FY", "end": "2025-09-27", "val": 112000, "filed": "2025-10-31", "fy": 2025},
        ]
        pts = ef.annual_points(units)
        self.assertEqual(len(pts), 1)
        self.assertEqual(pts[0]["end"], "2025-09-27")

    def test_sorted_by_end(self):
        units = [
            {"form": "10-K", "fp": "FY", "end": "2025-09-27", "val": 3, "filed": "2025-10-31"},
            {"form": "10-K", "fp": "FY", "end": "2023-09-30", "val": 1, "filed": "2023-11-03"},
            {"form": "10-K", "fp": "FY", "end": "2024-09-28", "val": 2, "filed": "2024-11-01"},
        ]
        ends = [p["end"] for p in ef.annual_points(units)]
        self.assertEqual(ends, ["2023-09-30", "2024-09-28", "2025-09-27"])

    def test_empty(self):
        self.assertEqual(ef.annual_points([]), [])

    def test_cik_map_has_core(self):
        for s in ("AAPL", "GOOGL", "AXP", "KO", "COST", "NDAQ"):
            self.assertIn(s, ef.CIK_MAP)


if __name__ == "__main__":
    unittest.main()
