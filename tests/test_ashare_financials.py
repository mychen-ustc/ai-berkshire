"""ashare_financials.py 回归测试（A股点时财务摄取纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import ashare_financials as af  # noqa: E402


def _row(year, rd, notice, ni=1e9, rev=1e10, roe=4.14, eps=0.22, bps=5.45):
    return {"DATAYEAR": year, "REPORTDATE": rd, "NOTICE_DATE": notice,
            "PARENT_NETPROFIT": ni, "TOTAL_OPERATE_INCOME": rev,
            "WEIGHTAVG_ROE": roe, "BASIC_EPS": eps, "BPS": bps}


class TestNum(unittest.TestCase):
    def test_empty_variants(self):
        for v in ("", None, "-", "--"):
            self.assertIsNone(af._num(v))

    def test_numeric(self):
        self.assertEqual(af._num("4.14"), 4.14)
        self.assertEqual(af._num(710508576.43), 710508576.43)


class TestParseReport(unittest.TestCase):
    def test_annual_roe_to_ratio(self):
        p = af.parse_report(_row(2025, "2025-12-31 00:00:00", "2026-03-31 00:00:00", roe=4.14))
        self.assertTrue(p["is_annual"])
        self.assertEqual(p["year"], 2025)
        self.assertEqual(p["notice_date"], "2026-03-31")     # 公告日=available_at
        self.assertAlmostEqual(p["roe"], 0.0414)             # 百分数 4.14 → 比率 0.0414
        self.assertEqual(p["eps"], 0.22)

    def test_quarterly_flagged_not_annual(self):
        p = af.parse_report(_row(2026, "2026-03-31 00:00:00", "2026-04-29 00:00:00"))
        self.assertFalse(p["is_annual"])                     # Q1 非年报

    def test_missing_notice_returns_none(self):
        self.assertIsNone(af.parse_report(_row(2025, "2025-12-31", "")))

    def test_none_roe_kept_none(self):
        p = af.parse_report(_row(2025, "2025-12-31", "2026-03-31", roe=None))
        self.assertIsNone(p["roe"])


class TestAnnualPoints(unittest.TestCase):
    def test_filters_annual_and_sorts(self):
        rows = [
            _row(2024, "2024-12-31", "2025-03-30"),
            _row(2025, "2025-03-31", "2025-04-29"),          # 季报 → 剔除
            _row(2025, "2025-12-31", "2026-03-31"),
            _row(2023, "2023-12-31", "2024-03-28"),
        ]
        pts = af.annual_points(rows)
        self.assertEqual([p["year"] for p in pts], [2023, 2024, 2025])   # 只年报,按年升序

    def test_dedup_keeps_earliest_notice(self):
        # 同年两条(年报 + 修订),取最早公告(PIT)
        rows = [
            _row(2025, "2025-12-31", "2026-04-30"),          # 修订(晚)
            _row(2025, "2025-12-31", "2026-03-31"),          # 首次(早)
        ]
        pts = af.annual_points(rows)
        self.assertEqual(len(pts), 1)
        self.assertEqual(pts[0]["notice_date"], "2026-03-31")

    def test_limit(self):
        rows = [_row(y, f"{y}-12-31", f"{y+1}-03-31") for y in range(2015, 2026)]
        pts = af.annual_points(rows, limit=3)
        self.assertEqual([p["year"] for p in pts], [2023, 2024, 2025])   # 最近3年


if __name__ == "__main__":
    unittest.main()
