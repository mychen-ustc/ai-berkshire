"""financial_rigor.py 回归测试（stdlib unittest，零依赖）。

重点覆盖 calc 浮点污染修复（commit c05cc0e）的 golden case，
以及 AST 白名单的注入防护。运行：
    python3 -m unittest discover -s tests
"""
import ast
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import financial_rigor as fr  # noqa: E402


def ev(expr):
    return fr._eval_decimal(ast.parse(expr, mode="eval"))


class TestExactCalc(unittest.TestCase):
    def test_no_float_drift(self):
        # 修复前会得到 0.30000000000000004
        self.assertEqual(ev("0.1 + 0.2"), Decimal("0.3"))

    def test_classic_traps(self):
        self.assertEqual(ev("0.3 - 0.2"), Decimal("0.1"))
        self.assertEqual(ev("1.1 * 3"), Decimal("3.3"))

    def test_scientific_notation(self):
        self.assertEqual(ev("510 * 9.11e9"), Decimal("4646100000000.0"))

    def test_power_compounding(self):
        self.assertEqual(ev("1.05 ** 3"), Decimal("1.157625"))

    def test_parens_and_unary(self):
        self.assertEqual(ev("-(3 - 5) * 2.5"), Decimal("5.0"))

    def test_division(self):
        self.assertEqual(ev("3 / 4"), Decimal("0.75"))

    def test_reject_name(self):
        with self.assertRaises(ValueError):
            ev("os")

    def test_reject_call_injection(self):
        with self.assertRaises(ValueError):
            ev("__import__('os')")

    def test_division_by_zero_raises(self):
        with self.assertRaises(ZeroDivisionError):
            ev("1 / 0")

    def test_exact_calc_returns_none_on_injection(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = fr.exact_calc("__import__('os').system('echo pwned')")
        self.assertIsNone(result)
        self.assertNotIn("pwned", buf.getvalue())

    def test_exact_calc_happy_path(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = fr.exact_calc("0.1 + 0.2")
        self.assertEqual(result, 0.3)
        self.assertIn("0.3", buf.getvalue())


class TestExactHelper(unittest.TestCase):
    def test_float_to_decimal(self):
        self.assertEqual(fr.exact(0.1), Decimal("0.1"))

    def test_str_to_decimal(self):
        self.assertEqual(fr.exact("510"), Decimal("510"))

    def test_decimal_passthrough(self):
        self.assertEqual(fr.exact(Decimal("1.5")), Decimal("1.5"))


if __name__ == "__main__":
    unittest.main()
