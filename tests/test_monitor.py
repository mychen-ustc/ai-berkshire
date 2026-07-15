"""monitor.py 回归测试（健康判定纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import monitor as mon  # noqa: E402


class TestFreshness(unittest.TestCase):
    def test_green_within_warn(self):
        self.assertEqual(mon.freshness_verdict(5, 24, 72)[0], "🟢")

    def test_yellow_between(self):
        self.assertEqual(mon.freshness_verdict(48, 24, 72)[0], "🟡")

    def test_red_over_crit(self):
        self.assertEqual(mon.freshness_verdict(100, 24, 72)[0], "🔴")

    def test_none_is_red(self):
        self.assertEqual(mon.freshness_verdict(None, 24, 72)[0], "🔴")


class TestDeadman(unittest.TestCase):
    def test_green_within_interval(self):
        self.assertEqual(mon.deadman_verdict(100, 168)[0], "🟢")   # 100h<168h(周)

    def test_yellow_slightly_over(self):
        self.assertEqual(mon.deadman_verdict(200, 168)[0], "🟡")   # 168~252

    def test_red_severely_over(self):
        self.assertEqual(mon.deadman_verdict(300, 168)[0], "🔴")   # >252

    def test_never_run_red(self):
        self.assertEqual(mon.deadman_verdict(None, 168)[0], "🔴")


class TestOverall(unittest.TestCase):
    def test_worst_wins(self):
        self.assertEqual(mon.overall_health(["🟢", "🟡", "🔴"]), "🔴")
        self.assertEqual(mon.overall_health(["🟢", "🟡"]), "🟡")
        self.assertEqual(mon.overall_health(["🟢", "🟢"]), "🟢")

    def test_empty_red(self):
        self.assertEqual(mon.overall_health([]), "🔴")


if __name__ == "__main__":
    unittest.main()
