#!/usr/bin/env python3
"""数据血缘与复现日志（T2-4，零外部依赖）。

model_registry 管"模型有哪些、假设与校验状态"；lineage 管**"某个结论/数字到底
由哪版工具、消费了哪批数据算出"**——让任何历史结论可追溯、可重放、可审计。

核心是**可复现签名**：对 (工具版本 + 输入 + 参数) 做确定性哈希。日后重算，签名一致
→ 结果应当复现；若数据被修订(input as_of/fetched_at 变了)、工具升级→签名不同，
明确告诉你"这个历史结论已无法逐位复现，因为 X 变了"。这是机构审计与自省的底线：
不能有"当时算出来是这个数，现在没人知道怎么来的"。

隐私：血缘日志存 data/lineage.jsonl(gitignore，可能含持仓相关输出)。

用法：
  # 记录一次输出的血缘(通常由工具/报告流程调用)
  python3 tools/lineage.py record --output v10-组合优化 --tool portfolio_optimizer --version 0.3 \
      --inputs "VOO@yahoo@2026-07-14,GOOGL@yahoo@2026-07-14" --params "method=risk-parity,period=2y" \
      --result "年化+24.6%/回撤-12.7%"
  # 追溯某结论的来龙去脉
  python3 tools/lineage.py trace --output v10-组合优化
  # 校验是否仍可复现(对比新输入/参数/版本)
  python3 tools/lineage.py verify --output v10-组合优化 \
      --inputs "VOO@yahoo@2026-07-20,GOOGL@yahoo@2026-07-14" --params "method=risk-parity,period=2y" --version 0.3
"""
import argparse
import hashlib
import json
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "data", "lineage.jsonl")


# --------------------------------------------------------------------------
# 纯函数（可测）——可复现签名与血缘
# --------------------------------------------------------------------------
def _canonical(inputs, params, tool_version):
    """规范化 (输入+参数+版本) 为确定性字符串(排序,稳定)。纯函数。"""
    inp = sorted(f"{i.get('source','')}:{i.get('symbol','')}@{i.get('as_of','')}"
                 for i in inputs)
    par = sorted(f"{k}={params[k]}" for k in params)
    return json.dumps({"v": tool_version, "inputs": inp, "params": par},
                      ensure_ascii=False, sort_keys=True)


def signature(inputs, params, tool_version):
    """可复现签名 = SHA256(规范化输入)。同输入同参数同版本 → 同签名。纯函数。"""
    return hashlib.sha256(_canonical(inputs, params, tool_version).encode("utf-8")).hexdigest()[:16]


def build_record(output_id, tool, version, inputs, params, result_summary, computed_at):
    """构造一条血缘记录(含可复现签名)。纯函数。"""
    return {
        "output_id": output_id, "tool": tool, "version": version,
        "inputs": inputs, "params": params, "result_summary": result_summary,
        "computed_at": computed_at, "signature": signature(inputs, params, version),
    }


def find(records, output_id):
    """某 output 的最新血缘记录(按 computed_at)。纯函数。"""
    hits = [r for r in records if r["output_id"] == output_id]
    return sorted(hits, key=lambda r: r.get("computed_at", ""))[-1] if hits else None


def diff_reproducibility(old_record, new_inputs, new_params, new_version):
    """对比旧记录与新(输入/参数/版本)，判断能否逐位复现 + 指出哪部分变了。纯函数。"""
    new_sig = signature(new_inputs, new_params, new_version)
    reproducible = new_sig == old_record["signature"]
    changes = []
    if new_version != old_record["version"]:
        changes.append(f"工具版本 {old_record['version']}→{new_version}")
    old_inp = {f"{i.get('source','')}:{i.get('symbol','')}": i.get("as_of", "") for i in old_record["inputs"]}
    new_inp = {f"{i.get('source','')}:{i.get('symbol','')}": i.get("as_of", "") for i in new_inputs}
    for k in sorted(set(old_inp) | set(new_inp)):
        if old_inp.get(k) != new_inp.get(k):
            changes.append(f"输入 {k}: {old_inp.get(k,'(无)')}→{new_inp.get(k,'(无)')}")
    op, npm = old_record["params"], new_params
    for k in sorted(set(op) | set(npm)):
        if str(op.get(k)) != str(npm.get(k)):
            changes.append(f"参数 {k}: {op.get(k,'(无)')}→{npm.get(k,'(无)')}")
    return {"reproducible": reproducible, "old_signature": old_record["signature"],
            "new_signature": new_sig, "changes": changes}


def _parse_inputs(spec):
    """"VOO@yahoo@2026-07-14,GOOGL@em@2026-07-14" → [{symbol,source,as_of}]。"""
    out = []
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.split("@")
        out.append({"symbol": bits[0],
                    "source": bits[1] if len(bits) > 1 else "",
                    "as_of": bits[2] if len(bits) > 2 else ""})
    return out


def _parse_params(spec):
    out = {}
    for part in (spec or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


# --------------------------------------------------------------------------
# 存取
# --------------------------------------------------------------------------
def load(path=STORE):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def append(rec, path=STORE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
def cmd_record(args):
    inputs = _parse_inputs(args.inputs)
    params = _parse_params(args.params)
    rec = build_record(args.output, args.tool, args.version, inputs, params,
                       args.result or "", args.computed_at or _now())
    append(rec, args.path)
    print(f"✅ 已记录血缘 {args.output}（工具 {args.tool} v{args.version}, "
          f"{len(inputs)} 个输入, 签名 {rec['signature']}）")
    # 交叉核对：工具是否在模型登记册
    try:
        import model_registry as mr
        if not any(e["id"] == args.tool for e in mr.load()):
            print(f"  ⚠️ 工具 {args.tool} 未在模型登记册——建议先 model_registry.py add 登记。")
    except Exception:  # noqa: BLE001
        pass


def cmd_trace(args):
    rec = find(load(args.path), args.output)
    if not rec:
        raise SystemExit(f"未找到血缘：{args.output}")
    print("=" * 64)
    print(f"血缘追溯 · {rec['output_id']}")
    print("=" * 64)
    print(f"  工具    : {rec['tool']} v{rec['version']}")
    print(f"  算出时间: {rec['computed_at']}")
    print(f"  可复现签名: {rec['signature']}")
    print(f"  结果    : {rec['result_summary']}")
    print(f"  参数    : {', '.join(f'{k}={v}' for k, v in rec['params'].items()) or '—'}")
    print(f"  输入 ({len(rec['inputs'])}):")
    for i in rec["inputs"]:
        print(f"     · {i.get('symbol',''):<10} 源 {i.get('source','?'):<10} as_of {i.get('as_of','?')}")
    print(f"\n  → 重算时用 verify 对比签名，即可判断这个结论现在能否逐位复现。")


def cmd_verify(args):
    rec = find(load(args.path), args.output)
    if not rec:
        raise SystemExit(f"未找到血缘：{args.output}")
    d = diff_reproducibility(rec, _parse_inputs(args.inputs), _parse_params(args.params),
                             args.version or rec["version"])
    print("=" * 64)
    print(f"复现校验 · {args.output}")
    print("=" * 64)
    print(f"  原签名: {d['old_signature']}   新签名: {d['new_signature']}")
    if d["reproducible"]:
        print(f"  ✅ 可逐位复现——输入/参数/版本与当初完全一致。")
    else:
        print(f"  🔴 无法逐位复现——以下变化导致结果可能不同：")
        for c in d["changes"]:
            print(f"     · {c}")
        print(f"\n  → 这不是错误，而是审计事实：结论依赖的东西变了，须重新出具而非沿用旧结论。")


def cmd_list(args):
    recs = [r for r in load(args.path) if not args.output or r["output_id"] == args.output]
    print(f"血缘日志（{len(recs)} 条）")
    for r in sorted(recs, key=lambda x: x.get("computed_at", "")):
        print(f"  {r['computed_at']:<20} {r['output_id']:<22} {r['tool']} v{r['version']} "
              f"[{r['signature']}]")


def main():
    ap = argparse.ArgumentParser(description="数据血缘与复现日志(T2-4，可追溯/可重放，零依赖)")
    ap.add_argument("--path", default=STORE)
    sub = ap.add_subparsers(dest="cmd")

    rc = sub.add_parser("record", help="记录一次输出的血缘")
    rc.add_argument("--output", required=True, help="输出标识(如 v10-组合优化)")
    rc.add_argument("--tool", required=True)
    rc.add_argument("--version", required=True)
    rc.add_argument("--inputs", default="", help='"VOO@yahoo@2026-07-14,GOOGL@em@2026-07-14"')
    rc.add_argument("--params", default="", help='"method=risk-parity,period=2y"')
    rc.add_argument("--result", default="", help="结果摘要")
    rc.add_argument("--computed-at", dest="computed_at", help="默认现在")

    tr = sub.add_parser("trace", help="追溯某结论来龙去脉")
    tr.add_argument("--output", required=True)

    ve = sub.add_parser("verify", help="校验是否仍可复现")
    ve.add_argument("--output", required=True)
    ve.add_argument("--inputs", default="")
    ve.add_argument("--params", default="")
    ve.add_argument("--version")

    li = sub.add_parser("list", help="列出血缘日志")
    li.add_argument("--output")

    args = ap.parse_args()
    {"record": cmd_record, "trace": cmd_trace, "verify": cmd_verify,
     "list": cmd_list}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
