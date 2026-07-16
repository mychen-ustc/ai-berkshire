"""notify.py 回归测试（结果通知纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import notify  # noqa: E402


class TestLevels(unittest.TestCase):
    def test_rank_order(self):
        self.assertLess(notify.level_rank("info"), notify.level_rank("warn"))
        self.assertLess(notify.level_rank("warn"), notify.level_rank("crit"))

    def test_should_notify(self):
        self.assertTrue(notify.should_notify("crit", "warn"))
        self.assertTrue(notify.should_notify("warn", "warn"))
        self.assertFalse(notify.should_notify("info", "warn"))
        self.assertFalse(notify.should_notify("warn", "crit"))


class TestFormatLine(unittest.TestCase):
    def test_contains_tag_and_fields(self):
        line = notify.format_line("数据陈旧", "点时库 72h 未更新", "crit", ts="2026-07-16 07:15:00")
        self.assertIn("CRIT", line)
        self.assertIn("数据陈旧", line)
        self.assertIn("点时库 72h 未更新", line)
        self.assertIn("2026-07-16", line)


class TestWebhookPayload(unittest.TestCase):
    def test_feishu_shape(self):
        p = notify.webhook_payload("feishu", "标题", "正文", "crit")
        self.assertEqual(p["msg_type"], "text")
        self.assertIn("标题", p["content"]["text"])
        self.assertIn("🔴", p["content"]["text"])

    def test_slack_shape(self):
        p = notify.webhook_payload("slack", "标题", "正文", "warn")
        self.assertIn("text", p)
        self.assertIn("标题", p["text"])
        self.assertNotIn("msg_type", p)

    def test_unknown_kind_defaults_feishu(self):
        p = notify.webhook_payload("whatever", "t", "m", "info")
        self.assertEqual(p["msg_type"], "text")


class TestResolveChannels(unittest.TestCase):
    def test_log_always(self):
        self.assertIn("log", notify.resolve_channels(False, "win32", False))

    def test_desktop_when_available(self):
        ch = notify.resolve_channels(False, "darwin", True)
        self.assertIn("desktop", ch)

    def test_webhook_when_configured(self):
        ch = notify.resolve_channels(True, "linux", True)
        self.assertEqual(set(ch), {"log", "desktop", "webhook"})

    def test_no_desktop_on_unknown_platform(self):
        self.assertNotIn("desktop", notify.resolve_channels(True, "win32", True))


class TestSendMinLevelGate(unittest.TestCase):
    def test_below_min_skips(self):
        res = notify.send("t", "m", level="info", min_level="crit")
        self.assertTrue(res.get("skipped"))


if __name__ == "__main__":
    unittest.main()
