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
    """**启发式**单边检验:样本均值是否 > null_mean。**圆形**分块重采样(wrap-around)保留自相关。
    → 启发式 p 值(自助均值 <= null_mean 的比例)。纯函数(固定 seed 可复现)。

    ⚠️ 诚实边界(评审纠正):这**不是**严格的"经验零分布 p 值"——它重采样**已观测**的信号收益、
    对比**固定**的基线均值(未同时处理基线估计误差/信号选择/触发间隔不规则)。仅作启发式证据强弱,
    非严格显著性。严格版需时间块置换构造零分布 + scipy/statsmodels oracle 校准 size/power(见路线图)。
    block 应与前瞻窗长挂钩(重叠窗自相关≈horizon);调用方宜传 block≈horizon。"""
    xs = [float(x) for x in sample if x is not None]
    n = len(xs)
    if n == 0:
        return {"p_value": 1.0, "n": 0, "mean": None, "method": "circular-block-bootstrap-heuristic"}
    rnd = random.Random(seed)
    b = max(1, min(int(block), n))
    n_blocks = math.ceil(n / b)
    le = 0
    for _ in range(n_iter):
        vals = []
        for _ in range(n_blocks):
            start = rnd.randint(0, n - 1)                          # 圆形:任意起点
            vals.extend(xs[(start + k) % n] for k in range(b))     # wrap-around 取块
        m = sum(vals[:n]) / n
        if m <= null_mean:
            le += 1
    return {"p_value": le / n_iter, "n": n, "mean": sum(xs) / n, "null_mean": null_mean,
            "block": b, "method": "circular-block-bootstrap-heuristic", "strict": False}


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


def sidak_adjusted_sharpe_pvalue(sharpe_periodic, n_obs, n_trials=1):
    """观测 Sharpe 的**正态近似**单边 p 值,再按试验次数做**Šidák FWER**校正。纯函数。
    n_trials=为找到它试过多少个信号/参数;试得越多,同样的 Sharpe 越不显著(防"试到显著为止")。

    ⚠️ 命名诚实(评审纠正):这**不是**完整 Deflated Sharpe Ratio——DSR 需处理 skew/kurtosis,此处
    只是"正态近似 Sharpe p 值 + Šidák 多重检验校正"。Šidák 控 **FWER(族错误率)**,与 BH 控 **FDR** 不同。"""
    t = sharpe_tstat(sharpe_periodic, n_obs)
    p_single = 1.0 - _norm_cdf(t)
    p_family = 1.0 - (1.0 - p_single) ** max(1, int(n_trials))   # Šidák(FWER)
    return {"t_stat": t, "p_single": p_single, "p_sidak": min(1.0, p_family),
            "p_deflated": min(1.0, p_family), "n_trials": n_trials, "note": "Šidák-adjusted正态近似,非完整DSR"}


# 向后兼容别名(旧名过度承诺,已重命名为 sidak_adjusted_sharpe_pvalue)
deflated_sharpe_pvalue = sidak_adjusted_sharpe_pvalue


# --------------------------------------------------------------------------
# 反转覆盖率门禁(专治"在缺失数据上通过"的空操作剧场)
# --------------------------------------------------------------------------
def coverage_verdict(tested_symbols, delisting_symbols, expected_delisted=None,
                     pit_covered_symbols=None, min_cov=0.8, min_pit_frac=0.8):
    """回测前的诚实门禁。**度量覆盖率(需分母),不是命中**(评审纠正)。纯函数。

    幸存者:分母 = `expected_delisted`（该市场/时期"本应存在的已退市"名单,来自交易所历史证券主表/
    历史指数成分）。覆盖率 = |delisting_symbols ∩ expected_delisted| / |expected_delisted|。
    **无分母 → coverage-unknown(不能通过)**——加一个 LEHMQ 不能证明其余退市数据完整。
    PIT:被测池的点时覆盖率 < 阈值 → 前视修正不可信。"""
    tested = set(tested_symbols)
    flags = []
    # 幸存者覆盖率(需分母)
    if expected_delisted is None:
        cov_frac = None
        flags.append("survivorship: coverage-unknown(无历史证券主表/指数成分分母,无法计算退市覆盖率——不得称'无偏差')")
    else:
        exp = set(expected_delisted)
        cov_frac = (len(set(delisting_symbols) & exp) / len(exp)) if exp else None
        if cov_frac is None:
            flags.append("survivorship: 分母为空,coverage-unknown")
        elif cov_frac < min_cov:
            flags.append(f"survivorship: 退市覆盖率 {cov_frac:.0%}<{min_cov:.0%}(幸存者修正不完整)")
    # PIT 覆盖率
    pit = set(pit_covered_symbols or [])
    pit_frac = (len(tested & pit) / len(tested)) if tested else 0.0
    if pit_covered_symbols is not None and pit_frac < min_pit_frac:
        flags.append(f"lookahead: PIT覆盖仅 {pit_frac:.0%}<{min_pit_frac:.0%}(前视修正不可信)")
    trustworthy = len(flags) == 0
    return {"trustworthy": trustworthy, "survivorship_coverage": cov_frac,
            "pit_frac": round(pit_frac, 3), "flags": flags,
            "verdict": "可信" if trustworthy else ("coverage-unknown/不可信" if cov_frac is None else "coverage-partial/不可信")}


CONSTITUENTS = os.path.join(ROOT, "data", "universe_constituents.jsonl")


def load_expected_delisted(universe, as_of=None, path=CONSTITUENTS):
    """真分母来源:某 universe(指数/市场)在 as_of 前**本应存在的已退市**名单(交易所历史证券主表/指数成分)。
    → set 或 None(无数据源)。纯读取。文件缺失/无匹配 → None → 上游 coverage_verdict 判 coverage-unknown。
    ⚠️ 生产需接交易所历史成分/退市全量;本工具只提供机制,分母数据须另行摄取(免费源受限,诚实待补)。"""
    if not os.path.exists(path):
        return None
    best = None
    for ln in open(path, encoding="utf-8"):
        if not ln.strip():
            continue
        r = json.loads(ln)
        if r.get("universe") != universe:
            continue
        if as_of and r.get("as_of") and r["as_of"] > as_of:
            continue                                   # 只取 as_of 前的成分快照
        if best is None or (r.get("as_of") or "") >= (best.get("as_of") or ""):
            best = r
    return set(best.get("delisted", [])) if best else None


def coverage_from_master(tested_symbols, delisting_symbols, universe, as_of=None,
                         pit_covered_symbols=None, path=CONSTITUENTS, **kw):
    """便捷:从成分主表载真分母 → coverage_verdict。无分母源即 coverage-unknown(诚实,不通过)。"""
    exp = load_expected_delisted(universe, as_of, path)
    return coverage_verdict(tested_symbols, delisting_symbols, expected_delisted=exp,
                            pit_covered_symbols=pit_covered_symbols, **kw)


# --------------------------------------------------------------------------
# 试验台账(append-only,多重比较的分母)
# --------------------------------------------------------------------------
def param_hash(*parts):
    """参数指纹(标识"同一试验")。纯函数。"""
    import hashlib
    s = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(s.encode()).hexdigest()[:12]


def trial_uid(rec):
    """试验唯一 ID = 关键字段内容哈希。纯函数。"""
    import hashlib
    key = "|".join(str(rec.get(k)) for k in ("recorded_at", "signal", "symbol", "horizon", "freq", "cutoff", "split"))
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def _canonical(rec):
    """记录的规范化内容(排除 chain_hash 自身),用于哈希。纯函数。"""
    core = {k: v for k, v in rec.items() if k != "chain_hash"}
    return json.dumps(core, ensure_ascii=False, sort_keys=True)


def _chain_hash(prev_hash, rec):
    """链式哈希 = sha256(前一条 chain_hash | 本条规范化内容)。纯函数。防中间删改(篡改即断链)。"""
    import hashlib
    return hashlib.sha256((str(prev_hash) + "|" + _canonical(rec)).encode()).hexdigest()[:16]


def _append_chained(rec, path):
    """通用哈希链追加(seq+prev_hash+chain_hash)。供试验台账与预注册册共用。IO。"""
    recs = load_trials(path)
    prev = recs[-1].get("chain_hash", "GENESIS") if recs else "GENESIS"
    seq = (recs[-1].get("seq", -1) + 1) if recs else 0
    rec = dict(rec)
    rec["seq"] = seq
    rec["prev_hash"] = prev
    rec["chain_hash"] = _chain_hash(prev, rec)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def record_trial(rec, path=TRIALS):
    """追加一次试验,带哈希链 → 篡改/删除可被 verify 检出。含失败/0触发也记。IO。
    ⚠️ 诚实边界(评审#5):哈希链使删改**可审计(tamper-evident)**,但仍**非防绕过**——
    --no-record 可完全不记,真正不可绕过需强制统一执行入口(外部基础设施)。"""
    return _append_chained(rec, path)


def verify_ledger(path=TRIALS):
    """校验哈希链完整性:重算每条 chain_hash + 检 seq 单调 + prev_hash 衔接。→ 检出篡改/删除。纯计算。"""
    recs = load_trials(path)
    prev, broken = "GENESIS", []
    for i, r in enumerate(recs):
        expect = _chain_hash(prev, {k: v for k, v in r.items() if k != "chain_hash"})
        if r.get("chain_hash") != expect or r.get("seq") != i or r.get("prev_hash") != prev:
            broken.append(i)
        prev = r.get("chain_hash", "")
    return {"ok": len(broken) == 0, "n": len(recs), "broken_at": broken,
            "verdict": "完整(未检出篡改/删除)" if not broken else f"⚠️ 链断裂于第 {broken} 条(疑篡改/删除)"}


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
# 真功效分析(评审#7):MDE / 所需样本 / 达成功效(正态近似,复用 tail_risk.norm_ppf)
# --------------------------------------------------------------------------
def _z(p):
    import tail_risk
    return tail_risk.norm_ppf(p)


def required_n(mde, vol_periodic, alpha=0.05, power=0.8):
    """检出每期均值效应 mde(给定每期波动)所需**期数**(单边)。纯函数。
    N = ((z_alpha + z_power)·vol / mde)²。这才是 power analysis,非"数窗口"。"""
    if mde <= 0 or vol_periodic <= 0:
        return None
    z = _z(1 - alpha) + _z(power)
    return math.ceil((z * vol_periodic / mde) ** 2)


def min_detectable_effect(n, vol_periodic, alpha=0.05, power=0.8):
    """给定 n 期与波动,目标功效下**最小可检测效应(MDE)**(每期均值)。纯函数。"""
    if n <= 0 or vol_periodic <= 0:
        return None
    z = _z(1 - alpha) + _z(power)
    return z * vol_periodic / math.sqrt(n)


def power_at(n, effect, vol_periodic, alpha=0.05):
    """给定 n/效应/波动,单边检验的**达成功效**。纯函数。"""
    if n <= 0 or vol_periodic <= 0:
        return None
    ncp = effect * math.sqrt(n) / vol_periodic          # 非中心参数≈效应的 t
    return 1.0 - _norm_cdf(_z(1 - alpha) - ncp)


# --------------------------------------------------------------------------
# 预注册(评审#7):跑 OOS 前冻结假设/阈值(哈希链),防事后改参再看同段数据
# --------------------------------------------------------------------------
PREREG = os.path.join(ROOT, "data", "preregistrations.jsonl")


def preregister(spec, path=PREREG):
    """在 OOS 跑之前冻结 {因子/参数/horizon/MDE最低值/alpha/目标功效/基准/风险约束} + 参数哈希。
    哈希链存档 → 事后无法伪造"我早就注册过"。返回记录(含 prereg_id)。IO。"""
    spec = dict(spec)
    spec.setdefault("kind", "prereg")
    spec["param_hash"] = spec.get("param_hash") or param_hash(*(str(spec.get(k)) for k in sorted(spec) if k not in ("recorded_at",)))
    rec = _append_chained(spec, path)
    rec_id = rec["chain_hash"]
    return {**rec, "prereg_id": rec_id}


def find_prereg(param_hash_val, path=PREREG):
    """按 param_hash 找预注册(证明"先注册后验证")。→ 记录或 None。纯读取。"""
    for r in load_trials(path):
        if r.get("param_hash") == param_hash_val:
            return r
    return None


def promotion_verdict(oos, prereg):
    """按**预注册**阈值判 OOS 是否达标晋级(评审#7:阈值须预注册,不得事后定)。纯函数。
    prereg 阈值:min_material_edge(每期/年化净超额最低)、max_p(显著性上限)、
    min_net_excess_vs_bench(相对基准净超额,可选)、min_power(可选)。"""
    reasons, ok = [], True
    edge = oos.get("cagr")
    if prereg.get("min_material_edge") is not None:
        if edge is None or edge < prereg["min_material_edge"]:
            ok = False; reasons.append(f"OOS CAGR {edge} < 预注册 material 阈 {prereg['min_material_edge']}")
    if prereg.get("max_p") is not None:
        p = oos.get("bootstrap_p")
        if p is None or p > prereg["max_p"]:
            ok = False; reasons.append(f"OOS p {p} > 预注册上限 {prereg['max_p']}")
    if prereg.get("min_net_excess_vs_bench") is not None:
        ex = oos.get("net_excess_vs_bench")
        if ex is None or ex < prereg["min_net_excess_vs_bench"]:
            ok = False; reasons.append(f"相对基准净超额 {ex} < 预注册 {prereg['min_net_excess_vs_bench']}")
    return {"promote": ok, "reasons": reasons or ["全部预注册阈值达标"],
            "note": "阈值来自预注册(哈希链),非事后所定;holdout 失败不得改参再看同段数据"}


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
    ds = sidak_adjusted_sharpe_pvalue(0.25, 104, n_trials=20)
    print(f"Šidák-adj Sharpe(周SR0.25,104期,试20次): p_single {ds['p_single']:.3f} → p_sidak {ds['p_sidak']:.3f}")
    cv = coverage_verdict(["600519", "000001"], delisting_symbols=["LEHMQ"])   # 无分母
    print(f"覆盖率门禁(无分母): {cv['verdict']} · {cv['flags'][0][:50]}...")
    cv2 = coverage_verdict(["A"], delisting_symbols=["X"], expected_delisted=["X", "Y"])  # 覆盖50%
    print(f"覆盖率门禁(分母2/命中1): {cv2['verdict']} · 覆盖率 {cv2['survivorship_coverage']:.0%}")


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
    sub.add_parser("verify", help="校验试验台账哈希链完整性(检出篡改/删除)")
    args = ap.parse_args()

    def cmd_verify(a):
        v = verify_ledger()
        print(f"试验台账: {trial_count()} 条 · 链完整性: {v['verdict']}")
    {"power": cmd_power, "demo": cmd_demo, "verify": cmd_verify}.get(
        args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
