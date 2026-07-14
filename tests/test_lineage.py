"""lineage.py 回归测试（T2-4 可复现签名与血缘纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import lineage as lg  # noqa: E402


class TestSignature(unittest.TestCase):
    def test_deterministic(self):
        inp = [{"symbol": "VOO", "source": "yahoo", "as_of": "2026-07-14"}]
        s1 = lg.signature(inp, {"method": "risk-parity"}, "0.3")
        s2 = lg.signature(inp, {"method": "risk-parity"}, "0.3")
        self.assertEqual(s1, s2)                    # 确定性

    def test_order_independent(self):
        # 输入顺序不影响签名(内部排序)
        a = [{"symbol": "VOO", "source": "yahoo", "as_of": "d1"},
             {"symbol": "GOOGL", "source": "yahoo", "as_of": "d1"}]
        b = list(reversed(a))
        self.assertEqual(lg.signature(a, {}, "1"), lg.signature(b, {}, "1"))

    def test_changes_with_input(self):
        inp1 = [{"symbol": "VOO", "source": "yahoo", "as_of": "2026-07-14"}]
        inp2 = [{"symbol": "VOO", "source": "yahoo", "as_of": "2026-07-20"}]  # 数据修订
        self.assertNotEqual(lg.signature(inp1, {}, "0.3"), lg.signature(inp2, {}, "0.3"))

    def test_changes_with_version(self):
        inp = [{"symbol": "VOO", "source": "yahoo", "as_of": "d"}]
        self.assertNotEqual(lg.signature(inp, {}, "0.3"), lg.signature(inp, {}, "0.4"))


class TestReproducibility(unittest.TestCase):
    def setUp(self):
        self.inp = [{"symbol": "VOO", "source": "yahoo", "as_of": "2026-07-14"}]
        self.rec = lg.build_record("out1", "portfolio_optimizer", "0.3", self.inp,
                                   {"method": "risk-parity", "period": "2y"},
                                   "年化+24.6%", "2026-07-14 21:00:00")

    def test_same_reproducible(self):
        d = lg.diff_reproducibility(self.rec, self.inp,
                                    {"method": "risk-parity", "period": "2y"}, "0.3")
        self.assertTrue(d["reproducible"])
        self.assertEqual(d["changes"], [])

    def test_input_revision_breaks(self):
        new_inp = [{"symbol": "VOO", "source": "yahoo", "as_of": "2026-07-20"}]
        d = lg.diff_reproducibility(self.rec, new_inp,
                                    {"method": "risk-parity", "period": "2y"}, "0.3")
        self.assertFalse(d["reproducible"])
        self.assertTrue(any("VOO" in c for c in d["changes"]))

    def test_version_and_param_changes_listed(self):
        d = lg.diff_reproducibility(self.rec, self.inp,
                                    {"method": "risk-parity", "period": "5y"}, "0.4")
        self.assertFalse(d["reproducible"])
        self.assertTrue(any("版本" in c for c in d["changes"]))
        self.assertTrue(any("period" in c for c in d["changes"]))


class TestFind(unittest.TestCase):
    def test_latest_by_time(self):
        recs = [
            lg.build_record("o", "t", "1", [], {}, "r1", "2026-07-01 10:00:00"),
            lg.build_record("o", "t", "2", [], {}, "r2", "2026-07-14 10:00:00"),
        ]
        self.assertEqual(lg.find(recs, "o")["result_summary"], "r2")

    def test_none_when_absent(self):
        self.assertIsNone(lg.find([], "x"))


if __name__ == "__main__":
    unittest.main()
