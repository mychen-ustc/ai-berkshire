"""moneyflow.py 回归测试（stdlib unittest，零依赖，golden case 可手算）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import moneyflow as mf  # noqa: E402


def _bar(h, l, c, v):
    return {"high": h, "low": l, "close": c, "volume": v}


class TestUniversal(unittest.TestCase):
    def test_typical_price(self):
        self.assertEqual(mf.typical_price(_bar(12, 8, 10, 100)), 10.0)

    def test_mfi_bounds(self):
        up = [_bar(i + 1, i - 1, float(i), 100) for i in range(1, 10)]     # TP 递增
        down = [_bar(i + 1, i - 1, float(i), 100) for i in range(9, 0, -1)]
        self.assertEqual(mf.mfi(up, n=3), 100.0)
        self.assertEqual(mf.mfi(down, n=3), 0.0)

    def test_obv(self):
        bars = [_bar(10, 10, 10, 0), _bar(11, 11, 11, 100),
                _bar(10, 10, 10, 50), _bar(12, 12, 12, 80)]
        self.assertEqual(mf.obv(bars), [0.0, 100.0, 50.0, 130.0])

    def test_mfv(self):
        self.assertAlmostEqual(mf._mfv(_bar(10, 0, 10, 100)), 100.0, places=9)   # 收在最高→满流入
        self.assertAlmostEqual(mf._mfv(_bar(10, 0, 0, 100)), -100.0, places=9)   # 收在最低→满流出
        self.assertEqual(mf._mfv(_bar(10, 10, 10, 100)), 0.0)                    # high==low→0

    def test_cmf(self):
        top = [_bar(10, 5, 10, 100), _bar(12, 6, 12, 200)]   # 均收最高
        bot = [_bar(10, 5, 5, 100), _bar(12, 6, 6, 200)]     # 均收最低
        self.assertAlmostEqual(mf.cmf(top, n=2), 1.0, places=9)
        self.assertAlmostEqual(mf.cmf(bot, n=2), -1.0, places=9)

    def test_ad_line(self):
        bars = [_bar(10, 10, 10, 0), _bar(10, 0, 10, 100)]   # mfv(b1)=+100
        self.assertEqual(mf.ad_line(bars), [0.0, 100.0])

    def test_divergence_top(self):
        # 价创新高(末13为最高)但 OBV 未创新高 → 顶背离
        bars = [_bar(10, 10, 10, 0), _bar(12, 12, 12, 100),
                _bar(11, 11, 11, 200), _bar(11.5, 11.5, 11.5, 10), _bar(13, 13, 13, 10)]
        self.assertIn("顶背离", mf.divergence(bars))

    def test_compute_universal_inflow(self):
        # 稳定收在最高 + 放量上行 → 资金净流入
        bars = [_bar(i + 1, i - 1, float(i + 1), 1000) for i in range(1, 40)]
        r = mf.compute_universal(bars)
        self.assertIn("净流入", r["posture"])


class TestMainFlow(unittest.TestCase):
    def _rows(self):
        def row(main, xl, lg, sm, md, close):
            return {"main": main, "small": sm, "medium": md, "large": lg, "xlarge": xl,
                    "main_pct": 3.0, "small_pct": 0.0, "medium_pct": 0.0,
                    "large_pct": 0.0, "xlarge_pct": 0.0, "close": close, "change_pct": 1.0}
        return [row(2e8, 1.2e8, 0.8e8, -1e8, -1e8, 10.0),
                row(1e8, 0.5e8, 0.5e8, 0.0, -1e8, 10.1),
                row(3e8, 2e8, 1e8, -2e8, -1e8, 10.2)]

    def test_analyze_main_flow(self):
        r = mf.analyze_main_flow(self._rows())
        self.assertAlmostEqual(r["cum_main"], 6e8, places=2)
        self.assertAlmostEqual(r["main_1d"], 3e8, places=2)
        self.assertAlmostEqual(r["main_5d"], 6e8, places=2)     # 仅3日，全计入
        self.assertEqual(r["streak_days"], 3)
        self.assertEqual(r["streak_dir"], "净流入")
        self.assertIn("主力净流入", r["posture"])

    def test_streak_breaks_on_sign_flip(self):
        rows = self._rows()
        rows[-1]["main"] = -1e8   # 末日转净流出
        r = mf.analyze_main_flow(rows)
        self.assertEqual(r["streak_days"], 1)
        self.assertEqual(r["streak_dir"], "净流出")


if __name__ == "__main__":
    unittest.main()
