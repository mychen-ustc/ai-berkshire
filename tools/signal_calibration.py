#!/usr/bin/env python3
"""信号有效性校准（前瞻收益 vs 基线，零外部依赖）——L3 交叉验证支柱(信号侧)。

诊断(全链路能力诊断评级)指出：五面研究的信号**从未被证明有效**——全仓零 forward-return/
backtest 校准。本工具补这根支柱：对一个信号(如 RSI 超卖、金叉)在历史上**每次触发后的
前瞻收益**做统计,与**无条件基线**对比,看信号是否真有"edge"(超额)。

方法：信号触发日 i → 前瞻收益 = P[i+h]/P[i]−1;把所有触发的前瞻收益 与 全样本无条件
前瞻收益对比,看均值/胜率是否更优。**收敛为有效、无 edge 为无效**——把"我觉得这信号有用"
变成"数据是否支持"。

诚实边界：这是**描述性校准非严格显著性检验**(无 t 检验/无多重比较校正);样本少、regime
变化、前瞻窗口重叠都会失真;免费日线前复权;不构成交易建议。仅为"信号有没有被数据支持"提供证据。

用法：
  python3 tools/signal_calibration.py calibrate --symbol AAPL --signal rsi_oversold --horizon 20
  python3 tools/signal_calibration.py calibrate --symbol 600519 --signal golden_cross --horizon 60 --freq daily
"""
import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------
# 纯函数：前瞻收益 + 校准
# --------------------------------------------------------------------------
def forward_return(prices, i, horizon):
    """i 日买入、i+horizon 日的收益。越界返回 None。纯函数。"""
    j = i + horizon
    if i < 0 or j >= len(prices) or prices[i] in (None, 0):
        return None
    if prices[j] is None:
        return None
    return prices[j] / prices[i] - 1.0


def collect_forward(prices, indices, horizon):
    """一组触发日索引 → 各自前瞻收益(去越界)。纯函数。"""
    out = [forward_return(prices, i, horizon) for i in indices]
    return [r for r in out if r is not None]


def baseline_forward(prices, horizon):
    """无条件前瞻收益(每个可算日买入持有 horizon)。纯函数。"""
    return collect_forward(prices, range(len(prices)), horizon)


def _hit_rate(rs):
    return (sum(1 for r in rs if r > 0) / len(rs)) if rs else None


def calibrate(signal_fwd, baseline_fwd):
    """信号前瞻收益 vs 基线 → 均值/中位/胜率/edge。纯函数。
    edge = 信号均值 − 基线均值(>0 表信号后收益优于随机买入)。"""
    n = len(signal_fwd)
    sig_mean = statistics.mean(signal_fwd) if signal_fwd else None
    base_mean = statistics.mean(baseline_fwd) if baseline_fwd else None
    sig_hit = _hit_rate(signal_fwd)
    base_hit = _hit_rate(baseline_fwd)
    return {
        "n_signals": n, "n_baseline": len(baseline_fwd),
        "signal_mean": sig_mean, "signal_median": statistics.median(signal_fwd) if signal_fwd else None,
        "signal_hit": sig_hit, "baseline_mean": base_mean, "baseline_hit": base_hit,
        "edge_mean": (sig_mean - base_mean) if (sig_mean is not None and base_mean is not None) else None,
        "edge_hit": (sig_hit - base_hit) if (sig_hit is not None and base_hit is not None) else None,
        "signal_std": statistics.pstdev(signal_fwd) if len(signal_fwd) > 1 else None,
    }


def verdict(cal, min_n=20):
    """→ 有效/无效/样本不足 + 说明。纯函数。
    有效需:样本≥min_n 且 均值edge>0 且 胜率edge>0(均值与胜率同向占优)。"""
    n = cal["n_signals"]
    if n < min_n:
        return {"status": "样本不足", "note": f"仅 {n} 次触发(<{min_n})，不足以判定有效性"}
    em, eh = cal.get("edge_mean"), cal.get("edge_hit")
    if em is None or eh is None:
        return {"status": "不可判", "note": "缺基线或信号收益"}
    if em > 0 and eh > 0:
        return {"status": "有效", "note": f"信号后均值超额 {em:+.2%}、胜率超额 {eh:+.1%}(均值与胜率同向占优)"}
    if em <= 0 and eh <= 0:
        return {"status": "无效", "note": f"信号后均值超额 {em:+.2%}、胜率超额 {eh:+.1%}——无 edge,不优于随机买入"}
    return {"status": "存疑", "note": f"均值超额 {em:+.2%} 与胜率超额 {eh:+.1%} 方向不一致,证据混杂"}


# --------------------------------------------------------------------------
# 纯函数：信号检测(触发日索引)
# --------------------------------------------------------------------------
def rsi_series(closes, n=14):
    """逐 bar Wilder RSI 序列(前 n 个为 None)。与 technicals.rsi 同法,此处需整条序列。纯函数。"""
    out = [None] * len(closes)
    if len(closes) < n + 1:
        return out
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    avg_g = sum(gains[:n]) / n
    avg_l = sum(losses[:n]) / n
    for i in range(n, len(gains) + 1):
        if i > n:
            avg_g = (avg_g * (n - 1) + gains[i - 1]) / n
            avg_l = (avg_l * (n - 1) + losses[i - 1]) / n
        rs = (avg_g / avg_l) if avg_l != 0 else float("inf")
        out[i] = 100.0 if avg_l == 0 else 100 - 100 / (1 + rs)
    return out


def sma_series(closes, n):
    """逐 bar 简单均线(前 n-1 为 None)。纯函数。"""
    out = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        out[i] = sum(closes[i - n + 1:i + 1]) / n
    return out


def cross_below(series, thresh):
    """series 从 >=thresh 跌破到 <thresh 的索引(信号触发日)。纯函数。"""
    idx = []
    for i in range(1, len(series)):
        a, b = series[i - 1], series[i]
        if a is not None and b is not None and a >= thresh > b:
            idx.append(i)
    return idx


def cross_over(fast, slow):
    """fast 上穿 slow 的索引(金叉)。纯函数。"""
    idx = []
    for i in range(1, len(fast)):
        if None in (fast[i - 1], slow[i - 1], fast[i], slow[i]):
            continue
        if fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]:
            idx.append(i)
    return idx


def fire_indices(closes, signal, rsi_thresh=30):
    """按信号类型返回触发日索引。纯函数。"""
    if signal == "rsi_oversold":
        return cross_below(rsi_series(closes), rsi_thresh)
    if signal == "golden_cross":
        return cross_over(sma_series(closes, 50), sma_series(closes, 200))
    raise ValueError(f"未知信号: {signal}(支持 rsi_oversold / golden_cross)")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def cmd_calibrate(args):
    import datalayer as dl
    env = dl.fetch_history(args.symbol, freq=args.freq, period=args.period)
    pts = env.get("points") or []
    # points 为 (date, close) 元组序列(datalayer 前复权)
    closes = [p[1] for p in pts if len(p) >= 2 and p[1]]
    if len(closes) < 220:
        print(f"⚠️ 历史点仅 {len(closes)},金叉/长周期校准可能不足;继续。")
    idx = fire_indices(closes, args.signal, args.rsi_thresh)
    sig_fwd = collect_forward(closes, idx, args.horizon)
    base_fwd = baseline_forward(closes, args.horizon)
    cal = calibrate(sig_fwd, base_fwd)
    vd = verdict(cal, args.min_n)
    res = {"symbol": args.symbol, "signal": args.signal, "horizon": args.horizon,
           "freq": args.freq, "n_points": len(closes), "calibration": cal, "verdict": vd}
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    print("=" * 64)
    print(f"信号校准 · {args.symbol} · {args.signal} · 前瞻 {args.horizon}{args.freq[:1]} · 【{vd['status']}】")
    print("=" * 64)
    print(f"  触发次数 {cal['n_signals']}  ·  基线样本 {cal['n_baseline']}")
    if cal["signal_mean"] is not None:
        print(f"  信号后前瞻收益: 均值 {cal['signal_mean']:+.2%} · 中位 {cal['signal_median']:+.2%} · 胜率 {cal['signal_hit']:.0%}")
        print(f"  无条件基线:     均值 {cal['baseline_mean']:+.2%} · 胜率 {cal['baseline_hit']:.0%}")
        print(f"  → edge: 均值超额 {cal['edge_mean']:+.2%} · 胜率超额 {cal['edge_hit']:+.1%}")
    print(f"\n  判定: {vd['status']} —— {vd['note']}")
    print("\n  ⚠️ 描述性校准非严格显著性检验;样本少/regime变化/窗口重叠会失真;免费日线前复权;非交易建议。")


def main():
    ap = argparse.ArgumentParser(description="信号有效性校准(前瞻收益vs基线,L3支柱信号侧,零依赖)")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("calibrate", help="校准一个信号的历史前瞻收益 edge")
    c.add_argument("--symbol", required=True)
    c.add_argument("--signal", default="rsi_oversold", choices=["rsi_oversold", "golden_cross"])
    c.add_argument("--horizon", type=int, default=20, help="前瞻持有 bar 数")
    c.add_argument("--freq", default="daily", choices=["daily", "weekly"])
    c.add_argument("--period", default="10y")
    c.add_argument("--rsi-thresh", dest="rsi_thresh", type=float, default=30)
    c.add_argument("--min-n", dest="min_n", type=int, default=20, help="判定有效所需最少触发次数")
    c.add_argument("--json", action="store_true")
    args = ap.parse_args()
    {"calibrate": cmd_calibrate}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
