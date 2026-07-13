"""portfolio_scan.py 回归测试（stdlib unittest，零依赖，纯渲染）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import portfolio_scan as ps  # noqa: E402

DATA = {
    "source": "测试组合", "n": 2,
    "holdings": [
        {"symbol": "AAPL", "name": "AAPL", "market": "US", "weight": 60.0,
         "tech": "上升趋势 · MACD多头 · 逼近52周高位", "rs_pct": 2.1,
         "flow": "价量代理：资金净流入（吸筹为主）", "divergence": "量价基本同步",
         "senti": {"score": 82.4, "label": "极度贪婪 🤑（警惕）"},
         "consensus": {"stance": "乐观", "revision": "上修", "peg": 2.42}},
        {"symbol": "603986", "name": "兆易创新", "market": "A", "weight": 40.0,
         "tech": "偏多 · MACD空头 · 中低位", "rs_pct": 426.8,
         "flow": "价量代理：资金方向中性/分歧", "divergence": "量价基本同步",
         "senti": {"score": 53.9, "label": "中性"},
         "main_flow": "主力净流出·近5日 -134.90亿"},
    ],
    "portfolio": {
        "factor": {"n": 2, "n_eff": 1.8, "pc1_pct": 55.0, "verdict": "🟡 中度集中"},
        "market_sentiment": {"US": {"score": 76.3, "label": "极度贪婪"},
                             "A": {"score": 54.2, "label": "中性"}},
        "macro": {"regime": "复苏", "quadrant": "增长↑ 通胀↓", "icon": "🟢"},
    },
}


class TestRender(unittest.TestCase):
    def test_text(self):
        s = ps.render_text(DATA)
        self.assertIn("组合全景体检", s)
        self.assertIn("兆易创新", s)
        self.assertIn("有效独立因子 1.80/2", s)
        self.assertIn("复苏", s)

    def test_html(self):
        s = ps.render_html(DATA)
        self.assertTrue(s.startswith("<!DOCTYPE"))
        self.assertTrue(s.rstrip().endswith("</html>"))
        self.assertEqual(s.count('class="sym"'), 2)   # 两个持仓行(表头不含 sym)
        self.assertIn("兆易创新", s)
        self.assertIn("复苏", s)

    def test_html_handles_error_row(self):
        d = {"source": "x", "n": 1, "portfolio": {},
             "holdings": [{"symbol": "BAD", "weight": 100.0, "error": "取数失败"}]}
        s = ps.render_html(d)                       # 不应崩
        self.assertIn("取数失败", s)


if __name__ == "__main__":
    unittest.main()
