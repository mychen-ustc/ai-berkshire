#!/usr/bin/env python3
"""行业专用估值模型（零外部依赖，仅 stdlib）。P4 深度建模。

通用 DCF 套所有行业会失真。本工具给强特征行业的专用锚：
  · 银行 bank：合理 P/B = (ROE − g) / (COE − g)（戈登增长版剩余收益）。
  · 保险 insurance：P/EV 与新业务价值贡献（内含价值法）。
  · 地产 property：NAV/RNAV 折溢价。
  · SaaS：Rule of 40（增速+FCF利润率）+ 由增速反推可承受 EV/S。

用法：
  python3 tools/industry_valuation.py bank --roe 0.15 --coe 0.10 --g 0.03 --bvps 20
  python3 tools/industry_valuation.py saas --growth 0.30 --fcf-margin 0.15 --ev-s 12
  python3 tools/industry_valuation.py property --nav 100 --price 70
  python3 tools/industry_valuation.py insurance --ev 50 --nbv 6 --price 45
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def bank(roe, coe, g, bvps=None):
    """合理 P/B = (ROE-g)/(COE-g)。COE 需 > g。"""
    if coe <= g:
        raise SystemExit("要求 COE > g（否则模型发散）")
    justified_pb = (roe - g) / (coe - g)
    out = {"model": "bank", "justified_pb": justified_pb,
           "note": "ROE>COE 才配 P/B>1；杠杆行业务必看资本充足/拨备/不良"}
    if bvps:
        out["fair_value"] = justified_pb * bvps
    return out


def saas(growth, fcf_margin, ev_s=None):
    """Rule of 40 = 增速 + FCF 利润率(%)；≥40 健康。给定当前 EV/S 评贵贱。"""
    rule40 = (growth + fcf_margin) * 100
    out = {"model": "saas", "rule_of_40": rule40,
           "health": "✅ 达标(≥40)" if rule40 >= 40 else "⚠️ 未达40",
           "note": "Rule of 40 衡量增长-盈利平衡；EV/S 随增速与净留存(NRR)定价"}
    if ev_s is not None:
        # 粗略：可承受 EV/S ≈ rule40/4（经验锚，非精确）
        implied = rule40 / 4
        out["current_ev_s"] = ev_s
        out["heuristic_fair_ev_s"] = implied
        out["verdict"] = "偏贵" if ev_s > implied * 1.2 else ("偏便宜" if ev_s < implied * 0.8 else "大致合理")
    return out


def property_nav(nav, price):
    """地产：现价相对 NAV/RNAV 的折溢价。"""
    disc = (price / nav - 1) if nav else None
    return {"model": "property", "nav": nav, "price": price,
            "premium_discount_pct": round(disc * 100, 1) if disc is not None else None,
            "verdict": ("折价" if disc < -0.1 else ("溢价" if disc > 0.1 else "接近NAV")) if disc is not None else "—",
            "note": "地产看重估净资产 NAV/RNAV；折价未必便宜(需看杠杆/去化/减值)"}


def insurance(ev, nbv, price, nbv_multiple=10):
    """保险内含价值法：评估价值 ≈ EV + NBV×倍数；现价相对其折溢价。"""
    appraisal = ev + nbv * nbv_multiple
    return {"model": "insurance", "ev": ev, "nbv": nbv, "nbv_multiple": nbv_multiple,
            "appraisal_value": appraisal, "price": price,
            "p_ev": round(price / ev, 2) if ev else None,
            "premium_discount_pct": round((price / appraisal - 1) * 100, 1) if appraisal else None,
            "note": "P/EV<1 常见但需看 EV 假设(投资回报/贴现率)与新业务价值增长"}


def main():
    ap = argparse.ArgumentParser(description="行业专用估值（银行/保险/地产/SaaS，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    b = sub.add_parser("bank"); b.add_argument("--roe", type=float, required=True); b.add_argument("--coe", type=float, required=True); b.add_argument("--g", type=float, default=0.03); b.add_argument("--bvps", type=float); b.add_argument("--json", action="store_true")
    s = sub.add_parser("saas"); s.add_argument("--growth", type=float, required=True); s.add_argument("--fcf-margin", type=float, required=True); s.add_argument("--ev-s", type=float); s.add_argument("--json", action="store_true")
    p = sub.add_parser("property"); p.add_argument("--nav", type=float, required=True); p.add_argument("--price", type=float, required=True); p.add_argument("--json", action="store_true")
    i = sub.add_parser("insurance"); i.add_argument("--ev", type=float, required=True); i.add_argument("--nbv", type=float, required=True); i.add_argument("--price", type=float, required=True); i.add_argument("--nbv-multiple", type=float, default=10); i.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.cmd == "bank":
        r = bank(args.roe, args.coe, args.g, args.bvps)
    elif args.cmd == "saas":
        r = saas(args.growth, args.fcf_margin, args.ev_s)
    elif args.cmd == "property":
        r = property_nav(args.nav, args.price)
    elif args.cmd == "insurance":
        r = insurance(args.ev, args.nbv, args.price, args.nbv_multiple)
    else:
        ap.print_help(); return
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print(f"\n  ⚠️ 行业模型是「锚」、非真值；{r['note']}。务必与 DCF/comps 交叉、看行业特有风险。")


if __name__ == "__main__":
    main()
