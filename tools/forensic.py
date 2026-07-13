#!/usr/bin/env python3
"""会计取证 / 造假与暴雷预警（P2，零外部依赖）。

用成体系的量化指标给财报"验伤"，避免踩雷（防守价值极高）：
  - Beneish M-Score：8 变量盈余操纵概率模型（> -1.78 提示可能操纵）。
  - Altman Z-Score：破产风险（<1.81 危险区 / >2.99 安全区）。
  - 应计比率：(净利润 - 经营现金流)/总资产，高正值=盈利不由现金支撑(低质量)。
  - 现金转化：经营现金流/净利润，持续 <1 是"纸面利润"警号。

统计/比率用 float（会计指标是估计与判别，非货币精算）。与 investment-research
第四步(芒格逆向)、financial-data(交叉验证) 联动。

用法：
  python3 tools/forensic.py mscore --dsri 1.0 --gmi 1.0 --aqi 1.0 --sgi 1.0 \
      --depi 1.0 --sgai 1.0 --tata 0 --lvgi 1.0
  python3 tools/forensic.py altman --wc-ta 0.2 --re-ta 0.3 --ebit-ta 0.15 --mve-tl 2.0 --sales-ta 1.1
  python3 tools/forensic.py quality --ni 142 --cfo -30 --ta 400   # 应计比率 + 现金转化
"""
import argparse


# --------------------------------------------------------------------------
# Beneish M-Score（8 变量，纯函数）
# --------------------------------------------------------------------------
def beneish_mscore(dsri, gmi, aqi, sgi, depi, sgai, tata, lvgi):
    """8 变量 M-Score。各 *I 为当年/上年比值指数；tata=总应计/总资产。
    阈值：M > -1.78 → 可能盈余操纵；越高越可疑。"""
    return (-4.84 + 0.92 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi
            + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)


def mscore_flag(m):
    return "⚠️ 可能操纵盈余" if m > -1.78 else "✅ 未触发操纵阈值"


# --------------------------------------------------------------------------
# Altman Z-Score（制造业原版，纯函数）
# --------------------------------------------------------------------------
def altman_z(wc_ta, re_ta, ebit_ta, mve_tl, sales_ta):
    """Z = 1.2·营运资本/资产 + 1.4·留存收益/资产 + 3.3·EBIT/资产
    + 0.6·市值/总负债 + 1.0·营收/资产。"""
    return 1.2 * wc_ta + 1.4 * re_ta + 3.3 * ebit_ta + 0.6 * mve_tl + 1.0 * sales_ta


def altman_zone(z):
    if z > 2.99:
        return "✅ 安全区"
    if z >= 1.81:
        return "⚠️ 灰色区"
    return "🔴 财务困境区"


# --------------------------------------------------------------------------
# 盈利质量（纯函数）
# --------------------------------------------------------------------------
def accrual_ratio(ni, cfo, ta):
    """(净利润 - 经营现金流)/总资产。高正值=应计高、盈利质量低。"""
    return (ni - cfo) / ta if ta else float("nan")


def cash_conversion(ni, cfo):
    """经营现金流/净利润。<1 说明利润未充分转化为现金。"""
    return cfo / ni if ni else float("nan")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def cmd_mscore(a):
    m = beneish_mscore(a.dsri, a.gmi, a.aqi, a.sgi, a.depi, a.sgai, a.tata, a.lvgi)
    print("=" * 56)
    print(f"Beneish M-Score = {m:.3f}   {mscore_flag(m)}")
    print("=" * 56)
    print(f"  阈值 -1.78：> 阈值提示可能操纵盈余（越高越可疑）")
    print(f"  输入：DSRI={a.dsri} GMI={a.gmi} AQI={a.aqi} SGI={a.sgi} "
          f"DEPI={a.depi} SGAI={a.sgai} TATA={a.tata} LVGI={a.lvgi}")
    print("  提示：应收/收入、毛利、应计(TATA)是最常见的操纵信号来源")


def cmd_altman(a):
    z = altman_z(a.wc_ta, a.re_ta, a.ebit_ta, a.mve_tl, a.sales_ta)
    print("=" * 56)
    print(f"Altman Z-Score = {z:.3f}   {altman_zone(z)}")
    print("=" * 56)
    print("  >2.99 安全 · 1.81–2.99 灰色 · <1.81 困境")


def cmd_quality(a):
    ar = accrual_ratio(a.ni, a.cfo, a.ta)
    cc = cash_conversion(a.ni, a.cfo)
    print("=" * 56)
    print("盈利质量检验")
    print("=" * 56)
    print(f"  应计比率 (NI-CFO)/TA:  {ar:+.2%}   "
          + ("🔴 高应计，盈利质量低（利润未由现金支撑）" if ar > 0.10 else
             "⚠️ 偏高" if ar > 0.05 else "✅ 健康"))
    print(f"  现金转化 CFO/NI:       {cc:.2f}   "
          + ("🔴 利润未转化为现金" if cc < 0.5 else "⚠️ 偏弱" if cc < 1 else "✅ 良好"))
    if a.cfo < 0 < a.ni:
        print("  🔴 净利润为正但经营现金流为负——典型'纸面利润'暴雷前兆，务必深查")


def main():
    ap = argparse.ArgumentParser(description="会计取证：M-Score/Altman-Z/盈利质量（P2，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    m = sub.add_parser("mscore", help="Beneish 盈余操纵 M-Score")
    for k in ["dsri", "gmi", "aqi", "sgi", "depi", "sgai", "lvgi"]:
        m.add_argument(f"--{k}", type=float, default=1.0)
    m.add_argument("--tata", type=float, default=0.0)
    z = sub.add_parser("altman", help="Altman 破产风险 Z-Score")
    for k in ["wc-ta", "re-ta", "ebit-ta", "mve-tl", "sales-ta"]:
        z.add_argument(f"--{k}", type=float, required=True, dest=k.replace("-", "_"))
    q = sub.add_parser("quality", help="盈利质量(应计比率+现金转化)")
    q.add_argument("--ni", type=float, required=True, help="净利润")
    q.add_argument("--cfo", type=float, required=True, help="经营活动现金流")
    q.add_argument("--ta", type=float, required=True, help="总资产")
    args = ap.parse_args()
    {"mscore": cmd_mscore, "altman": cmd_altman, "quality": cmd_quality}.get(
        args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
