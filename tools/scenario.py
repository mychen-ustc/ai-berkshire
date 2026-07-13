#!/usr/bin/env python3
"""情景与概率引擎（零外部依赖，仅 stdlib）。P4 深度建模。

把"牛/基/熊"情景 + 主观概率变成可计算的期望：概率加权价值、期望回报、
非对称赔率(上行/下行)、亏损概率。让 decision_journal 的概率字段可算、可事后校准。

用法：
  python3 tools/scenario.py eval --price 100 --scenarios "bull:0.30:160,base:0.50:110,bear:0.20:60"
  python3 tools/scenario.py eval --price 315 --scenarios "牛:0.25:450,基:0.55:340,熊:0.20:220"
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def analyze(scenarios, price):
    """scenarios: [{name, prob, value}]。返回概率加权与赔率指标。"""
    tp = sum(s["prob"] for s in scenarios)
    if tp <= 0:
        raise SystemExit("概率之和必须 > 0")
    norm = [{**s, "prob": s["prob"] / tp} for s in scenarios]         # 归一化
    ev = sum(s["prob"] * s["value"] for s in norm)
    exp_ret = (ev / price - 1) if price else None
    best = max(norm, key=lambda s: s["value"])
    worst = min(norm, key=lambda s: s["value"])
    up = (best["value"] / price - 1) if price else None               # 最好情景回报
    down = (worst["value"] / price - 1) if price else None            # 最坏情景回报
    p_loss = sum(s["prob"] for s in norm if s["value"] < price)       # 亏损概率
    # 概率加权的上行/下行（相对现价）
    up_cap = sum(s["prob"] * max(0.0, s["value"] / price - 1) for s in norm) if price else None
    down_cap = sum(s["prob"] * max(0.0, 1 - s["value"] / price) for s in norm) if price else None
    asym = (up_cap / down_cap) if (up_cap is not None and down_cap) else None
    return {"price": price, "scenarios": norm, "ev": ev, "expected_return": exp_ret,
            "best_return": up, "worst_return": down, "p_loss": p_loss,
            "up_capture": up_cap, "down_capture": down_cap, "asymmetry": asym}


def render(r):
    L = ["=" * 58, f"情景与概率 · 现价 {r['price']}", "=" * 58]
    for s in sorted(r["scenarios"], key=lambda x: -x["value"]):
        ret = (s["value"] / r["price"] - 1) * 100 if r["price"] else 0
        L.append(f"  {s['name']:<8} P={s['prob'] * 100:>4.0f}%  目标 {s['value']:>8.2f}  ({ret:+.1f}%)")
    L.append("-" * 58)
    L.append(f"  概率加权价值(EV):   {r['ev']:.2f}")
    L.append(f"  期望回报:           {r['expected_return'] * 100:+.1f}%")
    L.append(f"  最好/最坏情景:      {r['best_return'] * 100:+.1f}% / {r['worst_return'] * 100:+.1f}%")
    L.append(f"  亏损概率:           {r['p_loss'] * 100:.0f}%")
    if r["asymmetry"] is not None:
        L.append(f"  非对称赔率(上/下):  {r['asymmetry']:.2f}  "
                 f"({'✅ 上行占优' if r['asymmetry'] >= 1.5 else ('⚠️ 下行占优' if r['asymmetry'] < 1 else '中性')})")
    L.append("\n  ⚠️ 概率是主观判断、非事实；EV 对概率与目标价高度敏感。用来结构化思考+事后校准(Brier)，非精确预测。")
    return "\n".join(L)


def parse_scenarios(spec):
    out = []
    for part in spec.split(","):
        f = part.split(":")
        if len(f) != 3:
            raise SystemExit(f"情景格式应为 名称:概率:目标价，如 bull:0.3:160；收到 {part}")
        out.append({"name": f[0].strip(), "prob": float(f[1]), "value": float(f[2])})
    return out


def main():
    ap = argparse.ArgumentParser(description="情景与概率引擎（概率加权EV + 非对称赔率，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    e = sub.add_parser("eval", help="评估牛/基/熊情景")
    e.add_argument("--price", type=float, required=True)
    e.add_argument("--scenarios", required=True, help='名称:概率:目标价,... 如 "bull:0.3:160,base:0.5:110,bear:0.2:60"')
    e.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd != "eval":
        ap.print_help()
        return
    r = analyze(parse_scenarios(args.scenarios), args.price)
    print(json.dumps(r, ensure_ascii=False, indent=2) if args.json else render(r))


if __name__ == "__main__":
    main()
