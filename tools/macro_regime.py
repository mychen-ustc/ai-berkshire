#!/usr/bin/env python3
"""宏观 regime 引擎（零外部依赖，仅 stdlib）。

给一个**描述性**的宏观状态盘：增长(PMI) × 通胀(CPI) 定位美林投资时钟象限，
加流动性(M2/M1 剪刀差)与利率(10Y)读数。用途是**明确宏观只影响哪些决策**
（如现金区间、行业暴露、久期），**绝不用来在自下而上研究里随意改个股估值假设**。

数据（免费源）：
  · 中国 PMI / CPI / M2：东财宏观（datacenter）。
  · 10Y 利率：Yahoo ^TNX（美债 10Y，全球无风险利率锚）。

美林投资时钟（增长×通胀四象限，仅历史经验倾向、非预测）：
  复苏(增长↑通胀↓)→股票 ｜ 过热(增长↑通胀↑)→商品/周期 ｜ 滞胀(增长↓通胀↑)→现金 ｜ 衰退(增长↓通胀↓)→债券

诚实边界：
  · regime 是**事后描述、非预测**；单月 PMI/CPI 有噪声，方向可能反复。
  · 时钟象限的"利好资产"是历史统计倾向、**不构成择时信号**。
  · 中国 10Y 未直接接入（用美债 10Y 作全球利率锚）；宏观判断只调整组合层旋钮，不改个股基本面结论。

用法：
  python3 tools/macro_regime.py now
  python3 tools/macro_regime.py now --json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalayer as dl  # noqa: E402

DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def _dc(report, size=2):
    url = f"{DC}?reportName={report}&columns=ALL&pageSize={size}&sortColumns=REPORT_DATE&sortTypes=-1"
    d = json.loads(dl._curl(url, headers=["Referer: https://data.eastmoney.com/"]))
    return ((d.get("result") or {}).get("data")) or []


def fetch_pmi():
    rows = _dc("RPT_ECONOMY_PMI", 2)
    if not rows:
        return None
    cur, prev = rows[0], (rows[1] if len(rows) > 1 else rows[0])
    return {"time": cur.get("TIME"), "make": cur.get("MAKE_INDEX"), "make_prev": prev.get("MAKE_INDEX"),
            "nmake": cur.get("NMAKE_INDEX")}


def fetch_cpi():
    rows = _dc("RPT_ECONOMY_CPI", 2)
    if not rows:
        return None
    cur, prev = rows[0], (rows[1] if len(rows) > 1 else rows[0])
    return {"time": cur.get("TIME"), "yoy": cur.get("NATIONAL_SAME"), "yoy_prev": prev.get("NATIONAL_SAME"),
            "mom": cur.get("NATIONAL_SEQUENTIAL")}


def fetch_m2():
    rows = _dc("RPT_ECONOMY_CURRENCY_SUPPLY", 1)
    if not rows:
        return None
    r = rows[0]
    m2, m1 = r.get("BASIC_CURRENCY_SAME"), r.get("CURRENCY_SAME")
    scissors = (m1 - m2) if (isinstance(m1, (int, float)) and isinstance(m2, (int, float))) else None
    return {"time": r.get("TIME"), "m2_yoy": m2, "m1_yoy": m1, "scissors": scissors}


def fetch_10y():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX?interval=1d&range=5d"
        return dl.parse_yahoo(dl._curl(url)).get("price")
    except Exception:  # noqa: BLE001
        return None


def classify(pmi, cpi):
    """增长(PMI 扩张/收缩) × 通胀(CPI 升温/回落) → 美林时钟象限。"""
    growth_up = pmi and pmi["make"] is not None and pmi["make"] >= 50
    # 通胀方向：CPI 同比环比上升=升温
    infl_up = cpi and cpi["yoy"] is not None and cpi["yoy_prev"] is not None and cpi["yoy"] > cpi["yoy_prev"]
    if growth_up and not infl_up:
        return "复苏", "增长↑ 通胀↓", "历史倾向超配【股票】；顺周期成长占优", "🟢"
    if growth_up and infl_up:
        return "过热", "增长↑ 通胀↑", "历史倾向超配【商品/周期】；股票中性偏谨慎、久期收短", "🟠"
    if (not growth_up) and infl_up:
        return "滞胀", "增长↓ 通胀↑", "历史倾向超配【现金】；防御、控久期、避高估值", "🔴"
    return "衰退", "增长↓ 通胀↓", "历史倾向超配【债券】；股票防御为主、等政策转向", "🔵"


def now():
    pmi, cpi, m2, y10 = fetch_pmi(), fetch_cpi(), fetch_m2(), fetch_10y()
    regime, quad, favored, icon = classify(pmi, cpi)
    return {"pmi": pmi, "cpi": cpi, "m2": m2, "y10y": y10,
            "regime": regime, "quadrant": quad, "favored": favored, "icon": icon}


def render(d):
    p, c, m = d["pmi"], d["cpi"], d["m2"]
    L = ["=" * 62, "宏观 regime · 美林投资时钟", "=" * 62]
    L.append(f"  ▶ 当前象限: {d['icon']} 【{d['regime']}】 {d['quadrant']}")
    L.append(f"    {d['favored']}")
    L.append("\n  读数:")
    if p:
        arrow = "↑" if (p["make"] and p["make_prev"] and p["make"] > p["make_prev"]) else "↓"
        state = "扩张" if (p["make"] and p["make"] >= 50) else "收缩"
        L.append(f"    增长 PMI({p['time']}): 制造业 {p['make']} {arrow}（{state}, 荣枯线50） · 非制造业 {p['nmake']}")
    if c:
        arrow = "↑升温" if (c["yoy"] and c["yoy_prev"] and c["yoy"] > c["yoy_prev"]) else "↓回落"
        L.append(f"    通胀 CPI({c['time']}): 同比 {c['yoy']}% {arrow}（上期 {c['yoy_prev']}%） · 环比 {c['mom']}%")
    if m:
        sc = f"{m['scissors']:+.1f}pp" if m["scissors"] is not None else "—"
        L.append(f"    流动性 M2({m['time']}): M2 同比 {m['m2_yoy']}% · M1 同比 {m['m1_yoy']}% · M1-M2 剪刀差 {sc}"
                 + ("（<0 资金活化不足）" if (m["scissors"] is not None and m["scissors"] < 0) else ""))
    if d["y10y"] is not None:
        L.append(f"    利率 美债10Y: {d['y10y']}%（全球无风险利率锚）")
    L.append("\n  ⚠️ regime 是事后描述、非预测；单月数据有噪声；时钟「利好资产」是历史倾向、非择时信号。")
    L.append("     宏观只调组合层旋钮（现金/行业/久期），绝不用来改个股自下而上估值假设。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="宏观 regime 引擎（美林时钟 + 流动性 + 利率，零依赖）")
    sub = ap.add_subparsers(dest="cmd")
    n = sub.add_parser("now", help="当前宏观 regime 盘")
    n.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd != "now":
        ap.print_help()
        return
    d = now()
    print(json.dumps(d, ensure_ascii=False, indent=2) if args.json else render(d))


if __name__ == "__main__":
    main()
