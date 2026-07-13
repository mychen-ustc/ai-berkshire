"""review.py 回归测试（stdlib unittest，零依赖，纯 holding_flags/build_actions）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import review as rv  # noqa: E402


class TestFlags(unittest.TestCase):
    def test_main_flow_distribution_red(self):
        h = {"tech": "偏多 · MACD空头 · 中低位", "main_flow": "主力净流出·近5日 -139.6亿（派发）",
             "senti": {"score": 54}}
        flags = rv.holding_flags(h)
        self.assertTrue(any(lv == "🔴" and "派发" in msg for lv, msg in flags))

    def test_extreme_greed_yellow(self):
        flags = rv.holding_flags({"tech": "上升趋势", "senti": {"score": 84}})
        self.assertTrue(any(lv == "🟡" for lv, _ in flags))

    def test_extreme_fear_green(self):
        flags = rv.holding_flags({"tech": "偏空 · 深跌", "senti": {"score": 15}})
        levels = [lv for lv, _ in flags]
        self.assertIn("🟢", levels)      # 极度恐惧
        self.assertIn("🔴", levels)      # 同时技术转弱

    def test_revision_cut_red(self):
        flags = rv.holding_flags({"tech": "震荡", "consensus": {"revision": "下修"}, "senti": {"score": 50}})
        self.assertTrue(any("下修" in msg for _, msg in flags))

    def test_normal_no_flags(self):
        self.assertEqual(rv.holding_flags({"tech": "上升趋势 · MACD多头", "senti": {"score": 55}}), [])


class TestReversal(unittest.TestCase):
    def test_reversal_candidate(self):     # 极度恐惧+主力吸筹+趋势未转 → 反转候选
        h = {"tech": "偏空 · 深跌", "main_flow": "主力净流入 +2.16亿", "senti": {"score": 15}}
        self.assertIn("反转候选", rv.reversal_signal(h))

    def test_reversal_confirmed(self):     # +趋势转多 → 反转确认
        h = {"tech": "偏多 · 多头", "main_flow": "主力净流入", "senti": {"score": 20}}
        self.assertIn("反转确认", rv.reversal_signal(h))

    def test_no_reversal(self):
        self.assertIsNone(rv.reversal_signal({"tech": "上升", "main_flow": "净流出", "senti": {"score": 60}}))


class TestMarketVerdict(unittest.TestCase):
    def test_greed_caution(self):
        mkt = {"sentiment": {"US": {"score": 76}, "HK": {"score": 72}}, "macro": {"regime": "复苏"}, "breadth": None}
        v = rv.market_verdict_of(mkt)
        self.assertIn("不追高", v["caution"])
        self.assertIn("复苏", v["summary"])

    def test_weak_breadth(self):
        mkt = {"sentiment": {"A": {"score": 54}}, "macro": {"regime": "复苏"},
               "breadth": {"score": 14, "limit_up": 29, "limit_down": 172}}
        self.assertIn("广度弱", rv.market_verdict_of(mkt)["summary"])


class TestRenderMd(unittest.TestCase):
    R = {
        "cadence": "weekly", "date": "2026-07-14", "source": "账本 x.csv",
        "market": {"verdict": {"summary": "宏观复苏 · 政策要闻1条", "caution": "不追高"},
                   "macro": {"icon": "🟢", "regime": "复苏", "pmi": {"make": 50.3},
                             "cpi": {"yoy": 1}, "m2": {"m2_yoy": 8.6}, "y10y": 4.6},
                   "index_tech": {"US": "上升趋势"}, "breadth": {"limit_up": 29, "limit_down": 172, "label": "偏冷"},
                   "sentiment": {"US": {"score": 73, "label": "贪婪"}},
                   "news": {"policy_count": 1, "cn_tone": 0.2, "cn": []}},
        "port": {"factor": {"n": 8, "n_eff": 4.69, "pc1_pct": 37.4, "verdict": "🟡中度集中",
                            "port_momentum_z": -0.2, "port_vol_z": -0.3}},
        "holdings": [{"symbol": "GOOGL", "name": "谷歌", "weight": 15, "market": "US",
                      "fundamental": "评级乐观·上修·PEG1.44", "tech": "偏多 · MACD多头 · 中位",
                      "rs_pct": 42, "from_high": -12, "rsi14": 44, "vol_ratio": 0.7,
                      "flow": "价量中性", "divergence": "量价基本同步", "cmf": 0.17,
                      "senti": {"score": 60, "label": "贪婪"}}],
        "watch_extras": [], "due": [], "imminent": [], "us_earn": {},
        "radar": {"sectors": {"sectors": [{"sector": "化学制药", "limit_up_count": 4}]},
                  "candidates": {"candidates": [{"code": "688072", "name": "拓荆科技", "signal": "🏛️机构龙虎榜买入",
                                                 "strength": 3, "detail": "4家机构买入", "change": 1.6}]}},
        "actions": ["🌡️ 市场：不追高"], "updates": ["维持"], "thesis": {},
    }

    def test_render_md_structure(self):
        md = rv.render_md(self.R)
        self.assertIn("# 投资组合定期复盘", md)
        self.assertIn("## 一、市场五面摘要", md)
        self.assertIn("### 谷歌 `GOOGL`", md)
        self.assertIn("**技术面**", md)
        self.assertIn("## 六、市场机会雷达", md)
        self.assertIn("拓荆科技", md)
        self.assertIn("## 七、组合 & Watchlist 更新建议", md)


class TestActions(unittest.TestCase):
    def test_build_actions(self):
        holdings = [{"symbol": "603986", "name": "兆易创新",
                     "tech": "偏多", "main_flow": "主力净流出（派发）", "senti": {"score": 54}}]
        due = [{"symbol": "AAPL", "name": "苹果", "review_date": "2026-07-13"}]
        imminent = [{"date": "2026-07-22", "symbol": "GOOGL", "detail": "Q2财报"}]
        acts = rv.build_actions(holdings, [], due, imminent, {"caution": ""})
        self.assertTrue(any("复审到期" in a and "AAPL" in a for a in acts))
        self.assertTrue(any("临近催化剂" in a and "GOOGL" in a for a in acts))
        self.assertTrue(any("红线关注" in a and "603986" in a for a in acts))

    def test_market_caution_in_actions(self):
        acts = rv.build_actions([], [], [], [], {"caution": "情绪偏热→保持现金"})
        self.assertTrue(any("市场" in a for a in acts))

    def test_empty_actions(self):
        holdings = [{"symbol": "VOO", "tech": "上升趋势", "senti": {"score": 55}}]
        self.assertEqual(rv.build_actions(holdings, [], [], [], {"caution": ""}), [])


if __name__ == "__main__":
    unittest.main()
