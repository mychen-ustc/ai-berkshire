#!/usr/bin/env python3
"""代码质量硬门禁（零外部依赖，纯 stdlib ast）。

与 report_audit(报告门禁)对称——这是**代码门禁**。专治本项目反复踩的坑：
**循环变量遮蔽外层同名变量**(如 `for horizon in ...` 覆盖了之前的 horizon 字典、
`for market, fn in ...` 覆盖了 market 字典),两次让复盘静默崩溃(TypeError)。
单元测试(测纯函数)测不到这类集成层 bug,故用静态检查在提交前兜底。

检查项：
  1) loop-shadow(error)：for 循环变量遮蔽**同函数内更早的赋值**——最危险,循环后该名
     变成末次循环值,若后续按外层语义用它即 bug。退出码非零。
  2) unused-import(warn)：导入但从未使用(噪声/误导,非致命)。

用法：
  python3 tools/code_gate.py check --path tools/          # 扫目录(退出码 0=无error,1=有)
  python3 tools/code_gate.py check --path tools/review.py # 扫单文件
"""
import argparse
import ast
import os
import sys


# --------------------------------------------------------------------------
# 纯函数（可测）——AST 检查
# --------------------------------------------------------------------------
def _target_names(node):
    """从赋值/循环目标提取**真正绑定的简单名**(Name)——处理 Tuple/List/Starred 解包,
    但跳过 Subscript(prices[s])/Attribute(obj.x):它们是变更容器/属性,不新绑定简单名。"""
    out = []

    def rec(n):
        if isinstance(n, ast.Name):
            out.append(n.id)
        elif isinstance(n, (ast.Tuple, ast.List)):
            for c in n.elts:
                rec(c)
        elif isinstance(n, ast.Starred):
            rec(n.value)
        # Subscript/Attribute → 不绑定简单名,跳过
    rec(node)
    return out


def _own_nodes(fn):
    """yield fn 体内节点，但不下钻进嵌套函数/lambda(它们有独立作用域)。"""
    stack = list(fn.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue                           # 嵌套作用域:不 yield、不下钻其子节点
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _subtree_span(node):
    """节点子树的行号范围 (min, max)。"""
    lines = [n.lineno for n in ast.walk(node) if hasattr(n, "lineno")]
    return (min(lines), max(lines)) if lines else (node.lineno, node.lineno)


def find_shadowing(tree):
    """for 循环变量遮蔽同函数内更早赋值，**且该名在循环后仍被读取** → error。
    精化条件避免误报:临时名跨循环复用(循环后不再用)不算 bug;只有外层有意义绑定被
    循环覆盖、之后又按外层语义读取(如 horizon/market)才是真 bug。纯函数。"""
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        assigned = {}                          # name → 最早(非循环)赋值行
        fors = []
        loads = []                             # (name, line) 读取(Load)
        target_count = {}                      # name → 作循环/推导目标的次数
        for node in _own_nodes(fn):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    for nm in _target_names(t):
                        assigned.setdefault(nm, node.lineno)
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                fors.append(node)
                for nm in _target_names(node.target):
                    target_count[nm] = target_count.get(nm, 0) + 1
            elif isinstance(node, ast.comprehension):
                for nm in _target_names(node.target):
                    target_count[nm] = target_count.get(nm, 0) + 1
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                loads.append((node.id, node.lineno))
        for f in fors:
            _, f_end = _subtree_span(f)
            for nm in _target_names(f.target):
                # 仅当该名"只此一处"作循环/推导目标(非跨循环复用的临时名) + 有更早的意义赋值
                if nm in assigned and assigned[nm] < f.lineno and target_count.get(nm, 0) == 1:
                    # 且该名在**循环体之后**还被读取(外层值已被覆盖) → 真 bug
                    if any(name == nm and ln > f_end for name, ln in loads):
                        out.append({"line": f.lineno, "severity": "error", "code": "loop-shadow",
                                    "msg": f"循环变量 '{nm}' 遮蔽第 {assigned[nm]} 行赋值,且循环后第 "
                                           f"{next(ln for n2, ln in loads if n2 == nm and ln > f_end)} "
                                           f"行仍读取 '{nm}'——已被覆盖为末次值,极可能 bug"})
    return out


def find_unused_imports(tree):
    """导入但从未使用 → warn。纯函数。"""
    imported = {}                              # name → 行
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported[(a.asname or a.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name != "*":
                    imported[a.asname or a.name] = node.lineno
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    return [{"line": ln, "severity": "warn", "code": "unused-import",
             "msg": f"导入 '{nm}' 未使用"}
            for nm, ln in sorted(imported.items(), key=lambda x: x[1]) if nm not in used]


def check_source(source, filename="<src>"):
    """→ findings(按行排序)。语法错误单列。纯函数。"""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        return [{"line": e.lineno or 0, "severity": "error", "code": "syntax",
                 "msg": f"语法错误: {e.msg}"}]
    findings = find_shadowing(tree) + find_unused_imports(tree)
    return sorted(findings, key=lambda x: (x["line"], x["code"]))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _iter_py(path):
    if os.path.isfile(path):
        yield path
        return
    for root, _, files in os.walk(path):
        for f in sorted(files):
            if f.endswith(".py"):
                yield os.path.join(root, f)


def cmd_check(args):
    files = list(_iter_py(args.path))
    total_err = total_warn = 0
    print("=" * 66)
    print(f"代码质量门禁 · {args.path} · {len(files)} 个文件")
    print("=" * 66)
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            findings = check_source(f.read(), fp)
        if args.errors_only:
            findings = [x for x in findings if x["severity"] == "error"]
        if not findings:
            continue
        rel = os.path.relpath(fp)
        for x in findings:
            mark = "🔴" if x["severity"] == "error" else "🟡"
            print(f"  {mark} {rel}:{x['line']} [{x['code']}] {x['msg']}")
            if x["severity"] == "error":
                total_err += 1
            else:
                total_warn += 1
    print("-" * 66)
    print(f"  🔴 error(致命,阻断提交): {total_err}  ·  🟡 warn: {total_warn}")
    if total_err == 0:
        print(f"  ✅ 无致命问题(loop-shadow/syntax),可提交。")
    else:
        print(f"  🔴 有 {total_err} 个致命问题——修复后再提交(这类曾两次让复盘崩溃)。")
    sys.exit(0 if total_err == 0 else 1)


def main():
    ap = argparse.ArgumentParser(description="代码质量硬门禁:循环变量遮蔽/未用导入(零依赖AST)")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check", help="扫描目录/文件")
    c.add_argument("--path", default="tools/")
    c.add_argument("--errors-only", action="store_true", help="只报致命(loop-shadow/syntax)")
    args = ap.parse_args()
    if args.cmd == "check":
        cmd_check(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
