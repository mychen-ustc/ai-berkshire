"""run_audit.py 回归测试（可重放审计纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import run_audit as ra  # noqa: E402


class TestStatusOf(unittest.TestCase):
    def test_success_fail(self):
        self.assertEqual(ra.status_of(0), "success")
        self.assertEqual(ra.status_of(1), "failed")
        self.assertEqual(ra.status_of(2), "failed")


class TestMakeRunId(unittest.TestCase):
    def test_shape(self):
        rid = ra.make_run_id("cron-ingest", "20260717T064500", "902ca297b144")
        self.assertEqual(rid, "cron-ingest-20260717T064500-902ca29")   # SHA 截 7

    def test_nogit(self):
        self.assertTrue(ra.make_run_id("ci", "20260717T000000", None).endswith("-nogit"))


class TestBuildRecord(unittest.TestCase):
    def test_fields_and_status(self):
        r = ra.build_record("rid", "ci", "python -m unittest", "abc123", False,
                            "t0", "t1", 12.5, 0, "3.11", "runner", extra={"note": "x"})
        self.assertEqual(r["status"], "success")
        self.assertEqual(r["run_id"], "rid")
        self.assertEqual(r["duration_s"], 12.5)
        self.assertEqual(r["extra"]["note"], "x")

    def test_failed_status(self):
        r = ra.build_record("rid", "ci", "c", "abc", True, "t0", "t1", 1.0, 1, "3.11", "h")
        self.assertEqual(r["status"], "failed")
        self.assertNotIn("extra", r)                    # 无 extra 不塞空键


class TestReplayHint(unittest.TestCase):
    def test_clean(self):
        h = ra.replay_hint({"git_sha": "abc123", "command": "python x.py", "git_dirty": False})
        self.assertIn("git checkout abc123", h)
        self.assertIn("python x.py", h)
        self.assertNotIn("未提交", h)

    def test_dirty_flagged(self):
        h = ra.replay_hint({"git_sha": "abc", "command": "c", "git_dirty": True})
        self.assertIn("未提交", h)


class TestFailureStreak(unittest.TestCase):
    def test_trailing_failures(self):
        recs = [{"status": "success"}, {"status": "failed"}, {"status": "failed"}]
        self.assertEqual(ra.failure_streak(recs), 2)

    def test_reset_by_success(self):
        recs = [{"status": "failed"}, {"status": "success"}]
        self.assertEqual(ra.failure_streak(recs), 0)

    def test_all_success(self):
        self.assertEqual(ra.failure_streak([{"status": "success"}] * 3), 0)


class TestSummarize(unittest.TestCase):
    def test_per_trigger(self):
        recs = [
            {"trigger": "cron-ingest", "started_at": "2026-07-01", "status": "success", "run_id": "a"},
            {"trigger": "cron-ingest", "started_at": "2026-07-08", "status": "failed", "run_id": "b"},
            {"trigger": "ci", "started_at": "2026-07-08", "status": "success", "run_id": "c"},
        ]
        s = ra.summarize(recs)
        self.assertEqual(s["cron-ingest"]["total"], 2)
        self.assertEqual(s["cron-ingest"]["last_status"], "failed")   # 取最新(started_at 大)
        self.assertEqual(s["cron-ingest"]["last_run_id"], "b")
        self.assertEqual(s["cron-ingest"]["failure_streak"], 1)
        self.assertEqual(s["ci"]["failure_streak"], 0)

    def test_empty(self):
        self.assertEqual(ra.summarize([]), {})


if __name__ == "__main__":
    unittest.main()
