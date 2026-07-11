#!/usr/bin/env python3
"""仓位管理：凯利公式 / 非对称赔率（P1，零外部依赖，读 IPS 上限）。

把"决策→仓位"这一断点补上（帕伯莱"非对称下注" + 凯利仓位数学）：
  - kelly：给胜率 p 与赔率 b（净赔率=赢额/亏额）→ 凯利最优比例 f* = p − (1−p)/b。
  - asymmetric：给三情景的上行/下行空间 → 赔率 b=上行/下行，再算凯利。
实务用【分数凯利】（默认半凯利），并读 config/investment-policy.json 的单一持仓上限封顶。

统计/比例用 float；与 IPS 风险预算联动，接入 investment-research 第七步半 / investment-checklist。

用法：
  python3 tools/position_sizing.py kelly --p 0.6 --odds 3
  python3 tools/position_sizing.py asymmetric --upside 0.46 --downside 0.045 --p 0.6
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY = os.path.join(ROOT, "config", "investment-policy.json")


def kelly_fraction(p, b):
    """凯利最优下注比例 f* = p − (1−p)/b。b=净赔率(赢额/亏额)。负边际→0(不下注)。"""
    if b <= 0:
        return 0.0
    f = p - (1 - p) / b
    return max(0.0, f)


def ips_cap(policy_path=POLICY):
    """读 IPS 单一持仓上限(%)；缺失返回 None。"""
    if not os.path.exists(policy_path):
        return None, None
    with open(policy_path, encoding="utf-8") as f:
        pol = json.load(f)
    cap = pol.get("position_limits", {}).get("single_name_max_pct")
    return (cap / 100.0 if cap is not None else None), pol.get("status")


def recommend(p, b, fraction=0.5, policy_path=POLICY):
    """返回全/半/四分之一凯利 + IPS 封顶后的建议仓位。"""
    full = kelly_fraction(p, b)
    frac = full * fraction
    cap, status = ips_cap(policy_path)
    capped = min(frac, cap) if cap is not None else frac
    return {"full_kelly": full, "half_kelly": full * 0.5, "quarter_kelly": full * 0.25,
            "fraction": fraction, "fractional": frac, "ips_cap": cap, "ips_status": status,
            "recommended": capped, "capped_by_ips": cap is not None and frac > cap}


def _print(res, p, b, extra=""):
    print("=" * 58)
    print(f"仓位建议 · 胜率 {p:.0%} · 赔率 {b:.2f}:1 {extra}")
    print("=" * 58)
    if res["full_kelly"] <= 0:
        print("  ⚠️ 凯利 ≤ 0：期望边际为负或赔率不足，不建议下注")
        return
    print(f"  全凯利:        {res['full_kelly']:.1%}   (理论最优，实务过激)")
    print(f"  半凯利:        {res['half_kelly']:.1%}   (常用稳健档)")
    print(f"  四分之一凯利:  {res['quarter_kelly']:.1%}")
    print(f"  按 {res['fraction']:.0%} 凯利:  {res['fractional']:.1%}")
    if res["ips_cap"] is not None:
        print(f"  IPS 单一上限:  {res['ips_cap']:.0%}  (policy={res['ips_status']})")
    print(f"  ★ 建议仓位:    {res['recommended']:.1%}"
          + ("   ⚠️ 已被 IPS 封顶" if res["capped_by_ips"] else ""))
    tier = ("确信仓" if res["recommended"] >= 0.06 else
            "标准仓" if res["recommended"] >= 0.03 else "试探仓")
    print(f"  分档:          {tier}")


def main():
    ap = argparse.ArgumentParser(description="仓位管理：凯利/非对称赔率（P1，零依赖，读IPS）")
    ap.add_argument("--fraction", type=float, default=0.5, help="分数凯利(默认0.5半凯利)")
    ap.add_argument("--policy", default=POLICY)
    sub = ap.add_subparsers(dest="cmd")

    k = sub.add_parser("kelly", help="给胜率+净赔率")
    k.add_argument("--p", type=float, required=True, help="胜率 0-1")
    k.add_argument("--odds", type=float, required=True, help="净赔率 b(赢额/亏额)")

    a = sub.add_parser("asymmetric", help="给上行/下行空间(帕伯莱非对称)")
    a.add_argument("--upside", type=float, required=True, help="上行空间(如0.46)")
    a.add_argument("--downside", type=float, required=True, help="下行空间(正数，如0.045)")
    a.add_argument("--p", type=float, required=True, help="上行发生概率 0-1")

    args = ap.parse_args()
    if args.cmd == "kelly":
        res = recommend(args.p, args.odds, args.fraction, args.policy)
        _print(res, args.p, args.odds)
    elif args.cmd == "asymmetric":
        if args.downside <= 0:
            raise SystemExit("--downside 必须为正数(下行空间的绝对值)")
        b = args.upside / args.downside
        res = recommend(args.p, b, args.fraction, args.policy)
        _print(res, args.p, b, extra=f"· 上行{args.upside:.0%}/下行{args.downside:.1%}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
