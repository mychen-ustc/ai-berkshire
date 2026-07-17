#!/usr/bin/env python3
"""信号研究防过拟合工具箱（零外部依赖，纯 stdlib）——信号与策略路线图 P0/P1 一等公民。

诊断实证:全库 walk-forward/OOS/holdout/bootstrap/deflated-Sharpe/FDR 命中=0——过拟合"完全无防守"。
本工具把"防过拟合"从事后诚实声明升级为**可复用、可测的原语**,必须先于任何信号规模化测试落地:

  · 功效体检     effective_independent_obs —— 重叠前瞻窗把 N 次触发压成几个独立观测(诚实预期锚)
  · 密封 holdout  holdout_split / in_holdout —— 唯二无法回填之一:发现阶段永不触碰的样本外
  · 试验台账     record_trial / trial_count —— 唯二无法回填之二:多重比较的分母(不能把 N 次失败藏在 1 个幸存者后)
  · 样本外切分   walk_forward_splits —— 滚动训练/测试 + purge(防重叠标签泄漏)+ embargo
  · 显著性       block_bootstrap_pvalue —— 分块自助尊重重叠窗自相关(替换 signal_calibration 朴素 edge>0)
  · 多重检验     benjamini_hochberg —— FDR 校正(测 N 个信号必有假阳性)
  · 去膨胀       deflated_sharpe_pvalue —— 按试验次数惩罚 Sharpe(防"试到显著为止")
  · 反转门禁     coverage_verdict —— 修正数据缺失时拒绝声称"无偏差",强制标 coverage-absent(专治空操作剧场)

诚实边界:zero-dep 下显著性数学手写(block-bootstrap/erf 正态);样本薄时结论多为 null——这是特性不是bug。

用法(库为主,供 signal_calibration/strategy 回测调用):
  python3 tools/signal_lab.py power --triggers 21 --horizon 20        # 功效体检:有效独立观测
  python3 tools/signal_lab.py demo                                    # 各原语自检
"""
import argparse
import json
import math
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRIALS = os.path.join(ROOT, "data", "signal_trials.jsonl")


# --------------------------------------------------------------------------
# 功效体检:重叠前瞻窗 → 有效独立观测
# --------------------------------------------------------------------------
def effective_independent_obs(trigger_indices, horizon):
    """一组触发日索引 + 前瞻窗长 → 贪心取**不重叠**前瞻窗的数量(有效独立观测)。纯函数。
    两次触发若相距 < horizon,其前瞻收益高度重叠、非独立。这是诚实的样本量下界。"""
    if horizon <= 0:
        raise ValueError("horizon 必须 > 0")
    idx = sorted(set(int(i) for i in trigger_indices))
    count, last_claim_end = 0, -1
    for i in idx:
        if i >= last_claim_end:          # 落在上一个前瞻窗之外 → 独立
            count += 1
            last_claim_end = i + horizon
    return count


def power_verdict(n_triggers, horizon, eff_obs, min_obs=20):
    """→ 样本是否够判定有效性。纯函数。诚实预期:薄样本大概率支持不了任何 OOS 结论。"""
    if eff_obs < 5:
        level = "极薄(≈无法验证任何 edge)"
    elif eff_obs < min_obs:
        level = "偏薄(仅够探索,不足以确认)"
    else:
        level = "尚可"
    return {"n_triggers": n_triggers, "horizon": horizon, "effective_obs": eff_obs,
            "min_obs": min_obs, "adequate": eff_obs >= min_obs, "level": level}


# --------------------------------------------------------------------------
# 密封 holdout(时间轴样本外,发现阶段永不触碰)
# --------------------------------------------------------------------------
def holdout_split(sorted_dates, holdout_frac=None, holdout_from=None):
    """按时间轴切 (discovery, holdout)。holdout_from='YYYY-MM-DD' 或 holdout_frac(末尾比例)。纯函数。"""
    ds = list(sorted_dates)
    if holdout_from is not None:
        disc = [d for d in ds if d < holdout_from]
        hold = [d for d in ds if d >= holdout_from]
    else:
        frac = holdout_frac if holdout_frac is not None else 0.25
        k = int(round(len(ds) * (1 - frac)))
        disc, hold = ds[:k], ds[k:]
    return disc, hold


def in_holdout(date, holdout_dates):
    """某日期是否落在密封 holdout(供发现代码断言不触碰)。纯函数。"""
    return date in set(holdout_dates)


def assert_no_holdout_leak(used_dates, holdout_dates):
    """发现阶段用到的日期若与 holdout 相交即抛错(结构性防泄漏)。纯函数。"""
    leak = set(used_dates) & set(holdout_dates)
    if leak:
        raise AssertionError(f"holdout 泄漏:发现阶段触碰了 {len(leak)} 个密封样本(如 {sorted(leak)[:3]})")
    return True


# --------------------------------------------------------------------------
# walk-forward 滚动样本外 + purge/embargo(防重叠标签泄漏)
# --------------------------------------------------------------------------
def walk_forward_splits(n, train, test, step=None, purge=0, embargo=0):
    """滚动前进切分。每个 fold: train=[s,e) → purge 间隔 → test=[s,e);embargo 附加于 test 后。
    step 默认=test(测试窗不重叠)。purge 丢弃 train 末与 test 始之间的 bar,防重叠前瞻标签泄漏。纯函数。"""
    if train <= 0 or test <= 0:
        raise ValueError("train/test 必须 > 0")
    step = step or test
    folds = []
    tr = 0
    while True:
        tr_end = tr + train
        te_start = tr_end + purge
        te_end = te_start + test
        if te_end > n:
            break
        folds.append({"train": (tr, tr_end), "test": (te_start, te_end)})
        tr += step + embargo
    return folds


# --------------------------------------------------------------------------
# 分块自助显著性(尊重重叠前瞻窗的自相关)
# --------------------------------------------------------------------------
def block_bootstrap_pvalue(sample, null_mean=0.0, block=5, n_iter=2000, seed=0):
    """单边检验:样本均值是否显著 > null_mean。分块重采样保留自相关(重叠前瞻窗必须)。
    → 经验 p 值(自助均值 <= null_mean 的比例)。纯函数(固定 seed 可复现)。"""
    xs = [float(x) for x in sample if x is not None]
    n = len(xs)
    if n == 0:
        return {"p_value": 1.0, "n": 0, "mean": None}
    rnd = random.Random(seed)
    b = max(1, min(int(block), n))
    n_blocks = math.ceil(n / b)
    le = 0
    for _ in range(n_iter):
        vals = []
        for _ in range(n_blocks):
            start = rnd.randint(0, n - b) if n > b else 0
            vals.extend(xs[start:start + b])
        m = sum(vals[:n]) / n
        if m <= null_mean:
            le += 1
    return {"p_value": le / n_iter, "n": n, "mean": sum(xs) / n, "null_mean": null_mean, "block": b}


# --------------------------------------------------------------------------
# 多重检验:Benjamini-Hochberg FDR
# --------------------------------------------------------------------------
def benjamini_hochberg(pvalues, alpha=0.05):
    """BH-FDR:控制假发现率。→ {rejected:[bool...原序], threshold, n_reject}。纯函数。
    测 N 个信号必有假阳性;BH 比 Bonferroni 更不保守但控 FDR。"""
    m = len(pvalues)
    if m == 0:
        return {"rejected": [], "threshold": None, "n_reject": 0}
    order = sorted(range(m), key=lambda i: pvalues[i])
    thresh = 0.0
    kmax = -1
    for rank, i in enumerate(order, start=1):
        if pvalues[i] <= (rank / m) * alpha:
            kmax = rank
            thresh = (rank / m) * alpha
    rejected = [False] * m
    if kmax > 0:
        for rank, i in enumerate(order, start=1):
            if rank <= kmax:
                rejected[i] = True
    return {"rejected": rejected, "threshold": thresh, "n_reject": sum(rejected)}


# --------------------------------------------------------------------------
# 去膨胀 Sharpe:按试验次数惩罚(防"试到显著为止")
# --------------------------------------------------------------------------
def _norm_cdf(z):
    """标准正态 CDF,用 math.erf(stdlib,无需 scipy)。纯函数。"""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def sharpe_tstat(sharpe_periodic, n_obs):
    """周期 Sharpe 的 t 统计量(Lo 2002 近似,含 SR 自身方差修正)。纯函数。"""
    if n_obs <= 1:
        return 0.0
    se = math.sqrt((1.0 + 0.5 * sharpe_periodic ** 2) / n_obs)
    return sharpe_periodic / se if se > 0 else 0.0


def deflated_sharpe_pvalue(sharpe_periodic, n_obs, n_trials=1):
    """观测 Sharpe 的单边 p 值,再按试验次数做族内校正(Šidák)。→ 去膨胀后 p。纯函数。
    n_trials=你为找到它试过多少个信号/参数;试得越多,同样的 Sharpe 越不显著。"""
    t = sharpe_tstat(sharpe_periodic, n_obs)
    p_single = 1.0 - _norm_cdf(t)
    p_family = 1.0 - (1.0 - p_single) ** max(1, int(n_trials))   # Šidák
    return {"t_stat": t, "p_single": p_single, "p_deflated": min(1.0, p_family), "n_trials": n_trials}


# --------------------------------------------------------------------------
# 反转覆盖率门禁(专治"在缺失数据上通过"的空操作剧场)
# --------------------------------------------------------------------------
def coverage_verdict(tested_symbols, delisting_symbols, pit_covered_symbols=None, min_pit_frac=0.8):
    """回测前的诚实门禁。修正数据对被测池覆盖不足时,拒绝声称"无偏差",强制标 coverage-absent。纯函数。
    - 退市库对被测池若 0 命中 → 幸存者修正是空操作,不能称"无幸存者偏差"
    - PIT 覆盖 < 阈值 → 前视修正不可信"""
    tested = set(tested_symbols)
    delist_hits = len(tested & set(delisting_symbols))
    pit = set(pit_covered_symbols or [])
    pit_frac = (len(tested & pit) / len(tested)) if tested else 0.0
    flags = []
    if delist_hits == 0:
        flags.append("survivorship: coverage-absent(退市库对被测池0命中,幸存者修正为空操作,不得称'无偏差')")
    if pit_covered_symbols is not None and pit_frac < min_pit_frac:
        flags.append(f"lookahead: PIT覆盖仅 {pit_frac:.0%}<{min_pit_frac:.0%}(前视修正不可信)")
    trustworthy = len(flags) == 0
    return {"trustworthy": trustworthy, "delist_hits": delist_hits, "pit_frac": round(pit_frac, 3),
            "flags": flags, "verdict": "可信" if trustworthy else "coverage-absent/不可信"}


# --------------------------------------------------------------------------
# 试验台账(append-only,多重比较的分母)
# --------------------------------------------------------------------------
def record_trial(rec, path=TRIALS):
    """追加一次信号校准试验(从第 1 次起记,不能把 N 次失败藏在 1 个幸存者后)。IO。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_trials(path=TRIALS):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def trial_count(path=TRIALS, split=None):
    """试验总数(多重检验的 n_trials)。split 可筛 'train'/'holdout'。纯计数。"""
    recs = load_trials(path)
    if split:
        recs = [r for r in recs if r.get("split") == split]
    return len(recs)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def cmd_power(args):
    # 无触发索引时,用均匀近似:span=triggers*horizon 假设最坏聚集
    idx = list(range(0, args.triggers * max(1, args.spacing), max(1, args.spacing)))
    eff = effective_independent_obs(idx, args.horizon)
    v = power_verdict(args.triggers, args.horizon, eff, args.min_obs)
    print(json.dumps(v, ensure_ascii=False, indent=2) if args.json else
          f"功效体检: {args.triggers} 次触发 · 前瞻 {args.horizon} · 间距 {args.spacing}\n"
          f"  → 有效独立观测 {eff}（{v['level']}）· 达标({args.min_obs})? {'是' if v['adequate'] else '否'}")


def cmd_demo(args):
    print("=" * 60); print("signal_lab 原语自检"); print("=" * 60)
    print("功效: 21触发/间距8/前瞻20 →", effective_independent_obs(range(0, 21*8, 8), 20), "独立观测")
    print("walk-forward(n100,train40,test20,purge5):", len(walk_forward_splits(100, 40, 20, purge=5)), "折")
    d = [f"2024-{m:02d}-01" for m in range(1, 13)]
    disc, hold = holdout_split(d, holdout_frac=0.25)
    print(f"holdout(12期,25%): discovery {len(disc)} / sealed {len(hold)}")
    bp = block_bootstrap_pvalue([0.02]*30 + [0.05]*30, null_mean=0.01, seed=1)
    print(f"block-bootstrap p(均值0.035 vs null0.01): {bp['p_value']:.3f}")
    bh = benjamini_hochberg([0.001, 0.01, 0.04, 0.2, 0.5])
    print(f"BH-FDR([.001,.01,.04,.2,.5],a=.05): 拒绝 {bh['n_reject']} 个,阈值 {bh['threshold']:.4f}")
    ds = deflated_sharpe_pvalue(0.25, 104, n_trials=20)
    print(f"deflated Sharpe(周SR0.25,104期,试20次): p_single {ds['p_single']:.3f} → p_deflated {ds['p_deflated']:.3f}")
    cv = coverage_verdict(["600519", "000001"], delisting_symbols=["LEHMQ"], pit_covered_symbols=["600519"])
    print(f"覆盖率门禁: {cv['verdict']} · {cv['flags']}")


def main():
    ap = argparse.ArgumentParser(description="信号研究防过拟合工具箱(零依赖,纯函数原语)")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("power", help="功效体检:有效独立观测")
    p.add_argument("--triggers", type=int, required=True)
    p.add_argument("--horizon", type=int, required=True)
    p.add_argument("--spacing", type=int, default=8, help="触发平均间距(bar)")
    p.add_argument("--min-obs", dest="min_obs", type=int, default=20)
    p.add_argument("--json", action="store_true")
    sub.add_parser("demo", help="各原语自检")
    args = ap.parse_args()
    {"power": cmd_power, "demo": cmd_demo}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
