"""fetcher.py 回归测试（stdlib unittest，零依赖，纯 retry/fallback）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import fetcher as fx  # noqa: E402


class TestRetry(unittest.TestCase):
    def test_succeeds_after_failures(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ValueError("transient")
            return "ok"
        self.assertEqual(fx.retry_call(flaky, retries=2, backoff=0), "ok")
        self.assertEqual(calls["n"], 3)              # 失败2次+成功1次

    def test_raises_after_exhaust(self):
        def always_fail():
            raise RuntimeError("down")
        with self.assertRaises(RuntimeError):
            fx.retry_call(always_fail, retries=2, backoff=0)

    def test_no_retry_on_success(self):
        calls = {"n": 0}

        def ok():
            calls["n"] += 1
            return 42
        self.assertEqual(fx.retry_call(ok, retries=3, backoff=0), 42)
        self.assertEqual(calls["n"], 1)              # 成功即返回，不重试


class TestFallback(unittest.TestCase):
    def test_first_success(self):
        r = fx.fallback([("primary", lambda: "A"), ("backup", lambda: "B")])
        self.assertEqual(r["source"], "primary")
        self.assertEqual(r["value"], "A")

    def test_fallback_to_second(self):
        def boom():
            raise ConnectionError("x")
        r = fx.fallback([("primary", boom), ("backup", lambda: "B")])
        self.assertEqual(r["source"], "backup")

    def test_skip_none(self):
        r = fx.fallback([("empty", lambda: None), ("real", lambda: "V")])
        self.assertEqual(r["source"], "real")        # None 视为失败，降级下一个

    def test_all_fail(self):
        with self.assertRaises(RuntimeError):
            fx.fallback([("a", lambda: None), ("b", lambda: (_ for _ in ()).throw(ValueError()))])


if __name__ == "__main__":
    unittest.main()
