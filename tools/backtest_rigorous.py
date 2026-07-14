#!/usr/bin/env python3
"""回测严谨化层（T2-3，把 Tier 1 数据地基接入回测，零外部依赖）。

`backtest.py` 做"点时价格 + 含成本"的信号检验，但它自己诚实标注了三个缺口：
幸存者偏差、无点时基本面(估值信号无法检验)、无公司行动复权。本层把 Tier 1 三库
接进来，把这三个缺口补上，并**量化每种偏差的大小**——回测的价值一半在结果、
一半在"知道结果被高估了多少"。

三层严谨性：
  1) 幸存者修正 —— 用 delisting 构造"当时在市"股票池(含后来退市的)，把退市终值
     收益计入；报告 幸存者池 vs 全域 的收益差(偏差量级)。
  2) 点时基本面 —— 用 pit_financials 取"当时已披露"的估值/因子信号(无前视)，让
     估值类信号(如按盈利收益率选股)可被诚实检验。
  3) 公司行动复权 —— 用 corporate_actions 对原始价格收益做拆股/分红调整。

用法：
  # 审计一个回测配置对三种偏差的暴露(查 Tier 1 库,报告需要哪些修正)
  python3 tools/backtest_rigorous.py audit --symbols "AAPL,LEHMQ,GOOGL" --start 2007-01-01 --end 2009-12-31
  # 量化幸存者偏差：给定 全域/幸存者 各自的区间收益
  python3 tools/backtest_rigorous.py survivorship --full "AAPL=0.5,LEHMQ=-1.0,GOOGL=0.8" --survivors "AAPL=0.5,GOOGL=0.8"
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import delisting as dl  # noqa: E402
import corporate_actions as ca  # noqa: E402
import pit_financials as pf  # noqa: E402


# --------------------------------------------------------------------------
# 纯函数（可测）——偏差量化与修正
# --------------------------------------------------------------------------
def survivorship_bias(full_returns, survivor_returns):
    """全域(含退市终值) vs 幸存者池 的等权平均收益差。
    full_returns/survivor_returns: {symbol: 区间收益}。→ (full_avg, surv_avg, bias)。
    bias>0 = 幸存者池高估的幅度(只在活到今天的里选,系统性偏乐观)。纯函数。"""
    fa = (sum(full_returns.values()) / len(full_returns)) if full_returns else 0.0
    sa = (sum(survivor_returns.values()) / len(survivor_returns)) if survivor_returns else 0.0
    return fa, sa, sa - fa


def pit_universe_path(delisting_records, candidates, dates):
    """每个再平衡日的"当时在市"股票池(含后来退市的)。→ {date: [symbols]}。纯函数。"""
    return {d: dl.universe_as_of(delisting_records, candidates, d) for d in dates}


def pit_metric_path(pit_records, symbol, metric, dates):
    """每个日期"当时已披露"的指标值(无前视)。→ {date: value|None}。纯函数。"""
    out = {}
    for d in dates:
        hit = pf.as_of(pit_records, symbol, metric, d)
        out[d] = hit["value"] if hit else None
    return out


def ca_adjusted_return(actions, symbol, p_start, p_end, d_start, d_end, price_ref=None):
    """原始价格收益经公司行动修正。拆股会让 p_end 名义"暴跌"，须还原；分红计入总回报。
    → 修正后区间总回报。纯函数。"""
    sf = ca.share_adjust_factor(actions, symbol, d_start)          # 期间拆股倍数
    adj_end = p_end * sf                                            # 把期末价还原到期初股数口径
    price_ret = (adj_end / p_start - 1) if p_start else 0.0
    div = ca.total_dividends(actions, symbol, d_start, d_end)       # 期间每股分红
    div_yield = (div / p_start) if p_start else 0.0
    return price_ret + div_yield                                    # 总回报 = 价格 + 分红


def rigor_flags(delisting_records, pit_records, actions, symbols, start, end):
    """审计：这个回测配置暴露于哪些偏差、Tier 1 库能否修正。纯函数。"""
    would_drop = [r for r in delisting_records
                  if r["symbol"] in symbols and r.get("delisted")
                  and dl.was_listed(r, start) and not dl.was_listed(r, end)]
    has_pit = {s: any(r["symbol"] == s for r in pit_records) for s in symbols}
    has_ca = {s: any(a["symbol"] == s for a in actions) for s in symbols}
    return {
        "survivorship_dropped": [r["symbol"] for r in would_drop],
        "pit_coverage": [s for s, v in has_pit.items() if v],
        "pit_missing": [s for s, v in has_pit.items() if not v],
        "corporate_actions": [s for s, v in has_ca.items() if v],
    }


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
def _parse_ret(spec):
    out = {}
    for part in (spec or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = float(v)
    return out


def cmd_audit(args):
    syms = [s.strip() for s in args.symbols.split(",") if s.strip()]
    dels = dl.load()
    pits = pf.load()
    acts = ca.load()
    f = rigor_flags(dels, pits, acts, syms, args.start, args.end)
    print("=" * 66)
    print(f"回测严谨性审计 · {len(syms)}只 · {args.start} → {args.end}")
    print("=" * 66)
    print(f"\n① 幸存者偏差:")
    if f["survivorship_dropped"]:
        print(f"   🔴 区间内退市 {len(f['survivorship_dropped'])} 只：{', '.join(f['survivorship_dropped'])}")
        print(f"      → 若只用'活到今天'的池，这些会被漏掉，回测系统性偏乐观。应保留其终值收益。")
    else:
        print(f"   ⚪ 退市库中无该池区间退市样本(库空或确实无) → 无法修正/或无需修正")
    print(f"\n② 点时基本面(估值/因子信号可检验性):")
    if f["pit_coverage"]:
        print(f"   ✅ 有点时财务数据：{', '.join(f['pit_coverage'])}")
    if f["pit_missing"]:
        print(f"   ⬜ 无点时财务：{', '.join(f['pit_missing'])} → 估值/基本面因子信号在这些上无法无前视检验")
    print(f"\n③ 公司行动复权:")
    if f["corporate_actions"]:
        print(f"   ⚠️ 有公司行动需复权：{', '.join(f['corporate_actions'])} → 原始价格收益须经拆股/分红修正")
    else:
        print(f"   ⚪ 无登记的公司行动(或用 datalayer 前复权价即可)")
    print(f"\n⚠️ 严谨性取决于 Tier 1 库的数据完整度——库覆盖不全时，'无偏差'可能只是'没数据'。")


def cmd_survivorship(args):
    full = _parse_ret(args.full)
    surv = _parse_ret(args.survivors)
    fa, sa, bias = survivorship_bias(full, surv)
    print("=" * 60)
    print(f"幸存者偏差量化")
    print("=" * 60)
    print(f"  全域(含退市终值) {len(full)}只 等权平均收益: {fa:+.1%}")
    print(f"  幸存者池        {len(surv)}只 等权平均收益: {sa:+.1%}")
    print(f"  {'─'*40}")
    tag = "🔴 显著高估" if bias > 0.05 else ("🟡 轻微高估" if bias > 0 else "🟢 无高估")
    print(f"  幸存者偏差(高估幅度): {bias:+.1%}  {tag}")
    dropped = set(full) - set(surv)
    if dropped:
        print(f"\n  被幸存者池漏掉的样本: {', '.join(sorted(dropped))}")
        print(f"  这些退市/失败标的的收益({', '.join(f'{s}={full[s]:+.0%}' for s in sorted(dropped))})"
              f"未计入幸存者池 → 回测虚高 {bias:+.1%}。")
    print(f"\n  ⚠️ 这是'只在活到今天的公司里回测'的代价，真实策略当时并不知道谁会活下来。")


def main():
    ap = argparse.ArgumentParser(description="回测严谨化层(T2-3，接入Tier1数据地基，零依赖)")
    sub = ap.add_subparsers(dest="cmd")
    au = sub.add_parser("audit", help="审计回测配置对三种偏差的暴露")
    au.add_argument("--symbols", required=True)
    au.add_argument("--start", required=True)
    au.add_argument("--end", required=True)
    sv = sub.add_parser("survivorship", help="量化幸存者偏差(全域 vs 幸存者)")
    sv.add_argument("--full", required=True, help='"AAPL=0.5,LEHMQ=-1.0,..."全域含退市终值')
    sv.add_argument("--survivors", required=True, help='"AAPL=0.5,..."仅幸存者')
    args = ap.parse_args()
    {"audit": cmd_audit, "survivorship": cmd_survivorship}.get(
        args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
