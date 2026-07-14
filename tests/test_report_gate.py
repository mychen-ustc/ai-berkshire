"""report_audit.py AI 硬门禁回归测试（gate_report 纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import report_audit as ra  # noqa: E402


class TestGate(unittest.TestCase):
    def test_subjective_word_fails(self):
        md = "分析显示营收 100亿元（来源：财报）。\n我认为这家公司毫无疑问会涨。"
        res = ra.gate_report(md)
        self.assertEqual(res["verdict"], "FAIL")
        self.assertTrue(any("主观" in r for r in res["reasons"]))
        words = {w for _, w, _ in res["subjective_hits"]}
        self.assertIn("我认为", words)
        self.assertIn("毫无疑问", words)

    def test_blockquote_subjective_allowed(self):
        # 引用块中的"我觉得"是被引用的大师语录，不算分析者主观口吻
        md = "> 段永平：我觉得10年后腾讯会更值钱。"
        res = ra.gate_report(md)
        self.assertEqual(res["subjective_hits"], [])

    def test_absolute_scale_not_flagged(self):
        # "绝对规模"是技术词，不应命中主观词"绝对会/绝对是"
        md = "字节广告绝对规模约为腾讯 3倍（来源：财报）。"
        res = ra.gate_report(md)
        self.assertEqual(res["subjective_hits"], [])

    def test_historical_year_not_estimate(self):
        # FY2025 已实现营收带来源，不是前瞻估计
        md = "FY2025 总收入 7,518亿元（+14%）（来源：腾讯官方公告）。"
        res = ra.gate_report(md)
        self.assertEqual(res["unlabeled_estimates"], [])

    def test_forward_year_needs_estimate_label(self):
        # "远期"是前瞻词但非自标注(不同于"预测/预计")；2027E 记法也应触发
        many = "\n".join(
            f"远期 2027E 营收 {100+i}亿元（来源：财报）。" for i in range(5))  # 5 处前瞻无"估计"标注
        res = ra.gate_report(many)
        self.assertGreater(len(res["unlabeled_estimates"]), 3)
        self.assertEqual(res["verdict"], "FAIL")

    def test_source_coverage(self):
        # 10 行量化断言，全部有来源 → 覆盖率高、通过
        md = "\n".join(f"指标{i} {i*10}亿元（来源：财报）。" for i in range(10))
        res = ra.gate_report(md)
        self.assertGreaterEqual(res["coverage"], 0.9)

    def test_unsourced_low_coverage_fails(self):
        md = "\n".join(f"指标{i} {i*10}亿元。" for i in range(10))  # 无任何来源
        res = ra.gate_report(md)
        self.assertLess(res["coverage"], 0.6)
        self.assertEqual(res["verdict"], "FAIL")

    def test_clean_report_passes(self):
        md = ("# 报告\n"
              "营收 100亿元（来源：腾讯财报）。\n"
              "净利润 20亿元（数据来源：macrotrends）。\n"
              "毛利率 50%（来源：stockanalysis）。")
        res = ra.gate_report(md)
        self.assertEqual(res["verdict"], "PASS")
        self.assertTrue(res["cross_verified"])


if __name__ == "__main__":
    unittest.main()
