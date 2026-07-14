"""model_registry.py 回归测试（治理纯函数，零依赖）。"""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import model_registry as mr  # noqa: E402


class TestRevalidation(unittest.TestCase):
    def _e(self, **kw):
        base = {"id": "x", "status": "validated", "validated_on": "2026-01-01",
                "revalidate_every_days": 180, "tests": ["t.py"]}
        base.update(kw)
        return base

    def test_days_since(self):
        self.assertEqual(mr.days_since_validation(self._e(), date(2026, 1, 31)), 30)

    def test_within_period_ok(self):
        self.assertFalse(mr.needs_revalidation(self._e(), date(2026, 3, 1)))  # 59天 < 180

    def test_overdue(self):
        self.assertTrue(mr.needs_revalidation(self._e(), date(2026, 12, 1)))  # >180天

    def test_never_validated_needs(self):
        self.assertTrue(mr.needs_revalidation(self._e(validated_on=None), date(2026, 6, 1)))

    def test_deprecated_never_needs(self):
        self.assertFalse(mr.needs_revalidation(
            self._e(status="deprecated", validated_on="2020-01-01"), date(2026, 6, 1)))


class TestAudit(unittest.TestCase):
    def test_findings_partition(self):
        entries = [
            {"id": "a", "status": "validated", "validated_on": "2026-07-01",
             "revalidate_every_days": 180, "tests": ["t.py"]},
            {"id": "b", "status": "experimental", "validated_on": "2026-07-01",
             "revalidate_every_days": 180, "tests": ["t.py"]},
            {"id": "c", "status": "validated", "validated_on": "2020-01-01",
             "revalidate_every_days": 180, "tests": []},
        ]
        f = mr.audit_findings(entries, date(2026, 7, 14))
        self.assertEqual([e["id"] for e in f["overdue"]], ["c"])         # 过期
        self.assertEqual([e["id"] for e in f["experimental"]], ["b"])   # 实验中
        self.assertEqual([e["id"] for e in f["untested"]], ["c"])       # 无测试

    def test_seed_is_healthy_today(self):
        # 播种数据在播种当日应全部健康（无过期）
        f = mr.audit_findings(mr._seed(), date(2026, 7, 14))
        self.assertEqual(f["overdue"], [])
        self.assertEqual(f["untested"], [])


if __name__ == "__main__":
    unittest.main()
