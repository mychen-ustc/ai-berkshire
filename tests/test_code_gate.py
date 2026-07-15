"""code_gate.py 回归测试（AST 静态检查纯函数，零依赖）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import code_gate as g  # noqa: E402


class TestShadowing(unittest.TestCase):
    def _codes(self, src):
        return [f["code"] for f in g.check_source(src)]

    def test_true_bug_flagged(self):
        # 外层意义赋值 + 循环覆盖 + 循环后读取 = 真 bug(horizon/market 模式)
        src = ("def run(c):\n"
               "    horizon = pick(c)\n"
               "    for horizon in [1, 2, 3]:\n"
               "        pass\n"
               "    return build(horizon)\n")
        self.assertIn("loop-shadow", self._codes(src))

    def test_throwaway_reuse_not_flagged(self):
        # 同名在多个循环当临时变量 → 非 bug(target_count>1)
        src = ("def run(xs, ys):\n"
               "    k = init()\n"
               "    for k in xs:\n"
               "        use(k)\n"
               "    for k in ys:\n"
               "        use(k)\n"
               "    return k\n")
        self.assertNotIn("loop-shadow", self._codes(src))

    def test_subscript_index_not_binding(self):
        # prices[s]= 中 s 是下标非绑定;s 仅循环变量 → 不报
        src = ("def run(alloc):\n"
               "    for s in alloc:\n"
               "        prices[s] = 1\n"
               "    for s, a in alloc.items():\n"
               "        out(s, a)\n")
        self.assertNotIn("loop-shadow", self._codes(src))

    def test_no_use_after_not_flagged(self):
        # 循环后不再读取该名 → 非 bug
        src = ("def run(c):\n"
               "    horizon = pick(c)\n"
               "    use(horizon)\n"
               "    for horizon in [1, 2]:\n"
               "        pass\n")
        self.assertNotIn("loop-shadow", self._codes(src))

    def test_nested_function_own_scope(self):
        # 嵌套函数独立作用域,不与外层混算
        src = ("def outer():\n"
               "    x = 1\n"
               "    def inner():\n"
               "        for x in [1, 2]:\n"
               "            pass\n"
               "        return x\n"
               "    return x\n")
        self.assertNotIn("loop-shadow", self._codes(src))


class TestUnusedImport(unittest.TestCase):
    def test_unused_flagged(self):
        codes = [f["code"] for f in g.check_source("import os\nimport sys\nprint(sys.argv)\n")]
        self.assertIn("unused-import", codes)

    def test_used_not_flagged(self):
        codes = [f["code"] for f in g.check_source("import sys\nprint(sys.argv)\n")]
        self.assertNotIn("unused-import", codes)


class TestSyntax(unittest.TestCase):
    def test_syntax_error(self):
        self.assertEqual(g.check_source("def f(:\n pass")[0]["code"], "syntax")


if __name__ == "__main__":
    unittest.main()
