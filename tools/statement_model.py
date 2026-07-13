#!/usr/bin/env python3
"""三表联动财务预测模型（零外部依赖，仅 stdlib）。P4 深度建模。

driver-based：由收入驱动 → 利润表 → 自由现金流(勾稽营运资本/资本开支/折旧)，
让 DCF 的假设内部自洽(如高增长必然消耗营运资本、需资本开支支撑)，输出 FCF 喂 dcf.py。

驱动假设：营收增速、毛利率、费用率(占营收)、税率、折旧率(占营收)、资本开支率(占营收)、
营运资本变动率(占营收增量)。逐年投影 → EBIT/NOPAT/FCF。

用法：
  python3 tools/statement_model.py project --rev 1000 --years 5 \
    --growth 0.15 --gross 0.60 --opex 0.35 --tax 0.25 --dep 0.04 --capex 0.06 --wc 0.10
  # → 逐年利润表 + FCF；可把末年 FCF/增速接给 tools/dcf.py
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def project(rev0, years, growth, gross, opex, tax, dep, capex, wc):
    """逐年投影三表关键项。返回每年 dict + FCF。growth 可为标量或逐年列表。"""
    rows = []
    prev_rev = rev0
    for y in range(1, years + 1):
        g = growth[y - 1] if isinstance(growth, list) else growth
        rev = prev_rev * (1 + g)
        gp = rev * gross                       # 毛利
        ebit = rev * gross - rev * opex        # = rev*(gross-opex)
        nopat = ebit * (1 - tax)               # 税后经营利润
        d_a = rev * dep                        # 折旧摊销
        capex_v = rev * capex                  # 资本开支
        dwc = (rev - prev_rev) * wc            # 营运资本变动(随营收增量)
        fcf = nopat + d_a - capex_v - dwc      # 自由现金流(FCFF 近似)
        rows.append({"year": y, "revenue": rev, "gross_profit": gp, "ebit": ebit,
                     "ebit_margin": ebit / rev if rev else None, "nopat": nopat,
                     "d_a": d_a, "capex": capex_v, "delta_wc": dwc, "fcf": fcf})
        prev_rev = rev
    return rows


def render(rows, args):
    L = ["=" * 78, f"三表联动预测 · 基期营收 {args.rev} · {args.years} 年 · 增速 {args.growth} · 毛利 {args.gross}", "=" * 78]
    hdr = f"  {'年':<4}{'营收':>10}{'EBIT':>10}{'EBIT率':>8}{'NOPAT':>10}{'折旧':>8}{'资本开支':>9}{'ΔWC':>8}{'FCF':>10}"
    L.append(hdr)
    L.append("  " + "-" * (len(hdr) - 2))
    for r in rows:
        L.append(f"  {r['year']:<4}{r['revenue']:>10.0f}{r['ebit']:>10.0f}{r['ebit_margin'] * 100:>7.1f}%"
                 f"{r['nopat']:>10.0f}{r['d_a']:>8.0f}{r['capex']:>9.0f}{r['delta_wc']:>8.0f}{r['fcf']:>10.0f}")
    fcfs = [r["fcf"] for r in rows]
    L.append("-" * 78)
    L.append(f"  FCF: 首年 {fcfs[0]:.0f} → 末年 {fcfs[-1]:.0f}"
             + (f"（FCF CAGR {((fcfs[-1] / fcfs[0]) ** (1 / (len(fcfs) - 1)) - 1) * 100:+.1f}%）"
                if len(fcfs) > 1 and fcfs[0] > 0 else ""))
    L.append("  → 可把这组 FCF/末年增速接给 tools/dcf.py 做贴现；假设已内部勾稽(增长消耗WC+capex)。")
    L.append("\n  ⚠️ driver 模型放大假设敏感性；毛利/增速/capex 任一偏差都显著改变 FCF。做三情景、勿单点。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="三表联动财务预测（driver-based → FCF，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("project", help="逐年投影利润表 + FCF")
    p.add_argument("--rev", type=float, required=True, help="基期营收")
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--growth", type=float, default=0.10, help="营收增速(标量)")
    p.add_argument("--gross", type=float, default=0.50, help="毛利率")
    p.add_argument("--opex", type=float, default=0.30, help="费用率(占营收)")
    p.add_argument("--tax", type=float, default=0.25)
    p.add_argument("--dep", type=float, default=0.04, help="折旧率(占营收)")
    p.add_argument("--capex", type=float, default=0.05, help="资本开支率(占营收)")
    p.add_argument("--wc", type=float, default=0.10, help="营运资本变动率(占营收增量)")
    p.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd != "project":
        ap.print_help()
        return
    rows = project(args.rev, args.years, args.growth, args.gross, args.opex, args.tax, args.dep, args.capex, args.wc)
    print(json.dumps(rows, ensure_ascii=False, indent=2) if args.json else render(rows, args))


if __name__ == "__main__":
    main()
