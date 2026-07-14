"""industry_chain.py 回归测试（T3-3 图算法纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import industry_chain as ic  # noqa: E402


class TestGraph(unittest.TestCase):
    def setUp(self):
        self.edges = [
            ["AI应用", "云算力", "上游"],
            ["云算力", "AI服务器", "上游"],
            ["AI服务器", "GPU", "上游"],
            ["GPU", "HBM", "上游"],
            ["GPU", "晶圆代工", "上游"],
            ["晶圆代工", "光刻机", "上游"],
            ["AI应用", "边缘AI", "替代"],
        ]

    def test_upstream(self):
        self.assertEqual(ic.upstream(self.edges, "GPU"), ["HBM", "晶圆代工"])

    def test_downstream(self):
        self.assertEqual(ic.downstream(self.edges, "GPU"), ["AI服务器"])

    def test_substitutes(self):
        self.assertIn("边缘AI", ic.substitutes(self.edges, "AI应用"))

    def test_all_upstream_depth(self):
        ups = ic.all_upstream(self.edges, "AI应用")
        self.assertEqual(ups["云算力"], 1)
        self.assertEqual(ups["GPU"], 3)
        self.assertEqual(ups["光刻机"], 5)

    def test_shovel_candidates_sorted_by_depth(self):
        cands = ic.shovel_candidates(self.edges, "AI应用", min_depth=3)
        depths = [d for _, d in cands]
        self.assertEqual(depths, sorted(depths))       # 按深度排序
        self.assertTrue(all(d >= 3 for d in depths))   # 均≥min_depth
        names = [n for n, _ in cands]
        self.assertIn("光刻机", names)                  # 深层卖铲人

    def test_transmission_path(self):
        p = ic.transmission_path(self.edges, "AI应用", "光刻机")
        self.assertEqual(p, ["AI应用", "云算力", "AI服务器", "GPU", "晶圆代工", "光刻机"])

    def test_path_none_when_unreachable(self):
        self.assertIsNone(ic.transmission_path(self.edges, "光刻机", "AI应用"))  # 反向无上游边

    def test_path_self(self):
        self.assertEqual(ic.transmission_path(self.edges, "GPU", "GPU"), ["GPU"])

    def test_seed_valid(self):
        seed = ic._seed()
        self.assertGreater(len(seed["edges"]), 10)
        # 播种图上"卖铲子"应能找到晶圆代工/光刻机
        cands = [n for n, _ in ic.shovel_candidates(seed["edges"], "AI应用", 3)]
        self.assertIn("光刻机", cands)


if __name__ == "__main__":
    unittest.main()
