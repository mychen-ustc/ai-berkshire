#!/usr/bin/env python3
"""错误模式库与学习闭环（P4·治理，零外部依赖）。

机构自我进化的最后一环：把"犯过的错"沉淀成可复用的模式库，并在每次新决策前
强制过一遍"事前验尸(premortem)"清单——这些错误你以前犯过，这次别再犯。

三件事：
  1) 错误模式目录(config/error_patterns.json，入库)——价值投资经典陷阱 +
     每种的【事前信号】【规避清单】【哪位大师警告过】。
  2) 事后验尸(postmortem)——给已了结但"未中/亏损"的决策打上错误模式标签，
     存 data/portfolio/postmortems.jsonl(私有)。
  3) 学习报告 learn——统计各错误模式的发生频次，并结合 decision_journal 的
     Brier 校准，指出系统性偏差(如"我在成长股上系统性过度自信")。

用法：
  python3 tools/error_library.py init                 # 播种错误模式目录
  python3 tools/error_library.py catalog              # 看所有模式
  python3 tools/error_library.py checklist            # 事前验尸清单(下单前必过)
  python3 tools/error_library.py tag --decision 3 --pattern growth_trap --note "低估竞争"
  python3 tools/error_library.py learn                # 频次 + 校准偏差学习报告
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERNS = os.path.join(ROOT, "config", "error_patterns.json")
POSTMORTEMS = os.path.join(ROOT, "data", "portfolio", "postmortems.jsonl")
DECISIONS = os.path.join(ROOT, "data", "portfolio", "decisions.jsonl")


# --------------------------------------------------------------------------
# 播种：价值投资经典错误模式（这些是四大师反复警告的坑）
# --------------------------------------------------------------------------
def _seed():
    return [
        {"id": "value_trap", "name": "价值陷阱", "category": "估值",
         "desc": "便宜是因为基本面在恶化——低PE不是安全边际，是市场对衰退的正确定价。",
         "signals": ["低估值但ROIC持续下滑", "护城河在收窄", "行业结构性衰退"],
         "mitigation": "先问「便宜的原因」——是市场错了，还是生意变差了？确认是前者才买。",
         "master": "芒格：以合理价格买好公司，胜过便宜价格买烂公司。"},
        {"id": "growth_trap", "name": "成长陷阱", "category": "竞争格局",
         "desc": "为高增长付过高价，一旦增速回归均值，估值与盈利双杀(戴维斯双杀)。",
         "signals": ["靠高估值支撑股价", "增长依赖持续融资", "竞争格局未固化就重仓"],
         "mitigation": "增长要问「能持续多久、护城河护不护得住」；用远期而非当期估值倒推隐含预期。",
         "master": "段永平：不懂不做——看不清竞争格局稳定性就别下重注。"},
        {"id": "moat_misjudge", "name": "护城河误判", "category": "竞争格局",
         "desc": "把周期性顺风、一次性红利或先发优势，误当成结构性护城河。",
         "signals": ["高利润率但无进入壁垒", "份额靠补贴/低价", "技术迭代快的行业"],
         "mitigation": "列出护城河类型(网络/成本/无形资产/转换成本)，逐一证伪；看10年后还在不在。",
         "master": "巴菲特：护城河是能让对手十年攻不进来的东西。"},
        {"id": "mgmt_trust", "name": "管理层轻信", "category": "管理层",
         "desc": "被管理层叙事/魅力带节奏，忽视资本配置劣迹与利益不一致。",
         "signals": ["高承诺低兑现", "频繁并购摊薄", "关联交易/减持", "薪酬与业绩脱钩"],
         "mitigation": "看历史资本配置(回购时机/并购回报)而非听说辞；管理层利益是否与小股东一致。",
         "master": "李录：管理层的诚信与能力，看做过什么，不看说过什么。"},
        {"id": "macro_timing", "name": "宏观择时", "category": "宏观",
         "desc": "试图预测宏观拐点来择时进出，长期看是负和游戏，摩擦成本吞噬复利。",
         "signals": ["因宏观判断清仓好公司", "频繁调仓", "被单一宏观叙事主导"],
         "mitigation": "宏观是背景不是信号；只在极端估值区间调整总仓位，不预测拐点。",
         "master": "巴菲特：从不因宏观预测买卖，只算生意本身值多少。"},
        {"id": "anchoring", "name": "锚定偏差", "category": "心理偏差",
         "desc": "锚定买入成本或历史高点，导致该卖不卖(等回本)、该买不买(嫌涨多)。",
         "signals": ["以「回本」为卖出条件", "因「比高点跌了X%」判断便宜"],
         "mitigation": "只看「现在的价格 vs 现在的内在价值」，忘掉成本与历史价。",
         "master": "芒格：沉没成本是决策的毒药。"},
        {"id": "confirmation", "name": "确认偏差", "category": "心理偏差",
         "desc": "只找支持自己论点的证据，屏蔽反面信号，越套越深。",
         "signals": ["只读利好", "对空头论点情绪化反驳", "不设证伪条件"],
         "mitigation": "买入前写下「什么证据会证明我错」(卖出触发器)；主动找最强空头论点。",
         "master": "达尔文法则：优先记录与自己观点相悖的证据。"},
        {"id": "recency", "name": "近因偏差", "category": "心理偏差",
         "desc": "把最近的趋势(涨/跌)线性外推，追高杀跌。",
         "signals": ["因近期大涨FOMO", "因近期大跌恐慌", "外推近几个季度增速"],
         "mitigation": "拉长看完整周期与均值回归；问「这个趋势的持续性有基本面支撑吗」。",
         "master": "霍华德·马克斯：钟摆总会摆回，极端不可持续。"},
        {"id": "oversizing", "name": "过度下注", "category": "组合",
         "desc": "对高信心标的下注过重，一旦论点错误造成不可逆的组合级损伤。",
         "signals": ["单一持仓超IPS上限", "凯利满仓不打折", "相关持仓叠加成隐性集中"],
         "mitigation": "用半凯利；单一/单行业设硬上限；查伪分散(factor_model)。",
         "master": "凯利公式：过度下注长期必然破产，即使每次胜率占优。"},
        {"id": "illiquidity", "name": "流动性忽视", "category": "组合",
         "desc": "重仓流动性差的标的，危机时无法按合理价退出，纸面价值≠可变现价值。",
         "signals": ["持仓/ADV 比过高", "小盘/冷门", "退出需多日且冲击大"],
         "mitigation": "买入前算清仓需几天(tail_risk 流动性)；小盘控制仓位。",
         "master": "危机中流动性是唯一重要的东西。"},
    ]


# --------------------------------------------------------------------------
# 纯函数（可测）
# --------------------------------------------------------------------------
def pattern_frequency(postmortems):
    """→ {pattern_id: count}，按发生频次统计错误模式。纯函数。"""
    freq = {}
    for pm in postmortems:
        for pid in pm.get("patterns", []):
            freq[pid] = freq.get(pid, 0) + 1
    return freq


def category_bias(decisions):
    """按（错误模式所属类别的代理=决策的信心档）看系统性高估：resolved 决策中，
    高信心却未命中的比例。→ [(conviction, n, miss_rate)]。纯函数。"""
    out = []
    resolved = [d for d in decisions if d.get("status") == "resolved" and d.get("resolved")]
    for c in sorted({d.get("conviction") for d in resolved if d.get("conviction")}):
        grp = [d for d in resolved if d.get("conviction") == c]
        miss = sum(1 for d in grp if not d["resolved"].get("hit"))
        out.append((c, len(grp), miss / len(grp) if grp else 0.0))
    return out


def overconfidence_gap(decisions):
    """P(论点成立) 均值 − 实际命中率。>0 = 系统性过度自信。纯函数。"""
    resolved = [d for d in decisions
                if d.get("status") == "resolved" and d.get("resolved") and d.get("p_base") is not None]
    if not resolved:
        return None
    pred = sum(d["p_base"] for d in resolved) / len(resolved)
    actual = sum(1 for d in resolved if d["resolved"].get("hit")) / len(resolved)
    return pred - actual


# --------------------------------------------------------------------------
# 存取
# --------------------------------------------------------------------------
def load_patterns(path=PATTERNS):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_patterns(patterns, path=PATTERNS):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(patterns, f, ensure_ascii=False, indent=2)


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def append_jsonl(record, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
def cmd_init(args):
    if os.path.exists(args.patterns) and not args.force:
        print(f"⚠️ 错误模式目录已存在：{args.patterns}（--force 覆盖）")
        return
    save_patterns(_seed(), args.patterns)
    print(f"✅ 已播种错误模式目录 → {args.patterns}（{len(_seed())} 种模式）")


def cmd_catalog(args):
    pats = load_patterns(args.patterns)
    print(f"错误模式目录（{len(pats)} 种）")
    print("=" * 66)
    cats = {}
    for p in pats:
        cats.setdefault(p["category"], []).append(p)
    for cat, items in cats.items():
        print(f"\n【{cat}】")
        for p in items:
            print(f"  · {p['id']:<16} {p['name']}")
            print(f"      {p['desc']}")


def cmd_checklist(args):
    pats = load_patterns(args.patterns)
    print("=" * 66)
    print("事前验尸清单（premortem）——下单前逐条自问：这次会不会又踩这个坑？")
    print("=" * 66)
    for i, p in enumerate(pats, 1):
        print(f"\n  {i:>2}. [{p['name']}] {p['category']}")
        print(f"      事前信号：{'；'.join(p['signals'])}")
        print(f"      ✅ 规避  ：{p['mitigation']}")
        if args.verbose:
            print(f"      💬 {p['master']}")
    print("\n  " + "-" * 62)
    print("  规则：任一「事前信号」命中 → 必须在决策日志 thesis 中回应，否则不下单。")


def cmd_tag(args):
    pats = {p["id"] for p in load_patterns(args.patterns)}
    for pid in args.pattern:
        if pid not in pats:
            raise SystemExit(f"未知错误模式：{pid}（用 catalog 查看，或先 add）")
    rec = {"decision_id": args.decision, "patterns": args.pattern, "note": args.note or "",
           "lesson": args.lesson or ""}
    append_jsonl(rec, args.postmortems)
    print(f"✅ 已给决策 #{args.decision} 打标：{', '.join(args.pattern)}")
    if not args.lesson:
        print("  ⚠️ 未填 --lesson：验尸的价值在于写下「下次怎么做不一样」")


def cmd_learn(args):
    pats = {p["id"]: p for p in load_patterns(args.patterns)}
    postmortems = load_jsonl(args.postmortems)
    decisions = load_jsonl(args.decisions)

    print("=" * 66)
    print(f"学习报告 · 错误模式 {len(postmortems)} 例验尸 · 决策 {len(decisions)} 条")
    print("=" * 66)

    freq = pattern_frequency(postmortems)
    if freq:
        print("\n  📊 错误模式发生频次（你最常踩的坑，排前面的优先建立防线）：")
        for pid, n in sorted(freq.items(), key=lambda x: -x[1]):
            name = pats.get(pid, {}).get("name", pid)
            mit = pats.get(pid, {}).get("mitigation", "")
            print(f"     {n}× {name:<10} → {mit}")
    else:
        print("\n  （暂无验尸记录：用 tag 给已了结的失败决策打标，才能积累模式）")

    gap = overconfidence_gap(decisions)
    if gap is not None:
        tag = "🔴 系统性过度自信" if gap > 0.1 else ("🟡 略过度自信" if gap > 0 else "🟢 校准良好/偏保守")
        print(f"\n  🎯 自信校准：预测概率均值 − 实际命中率 = {gap:+.1%}  {tag}")
        if gap > 0.1:
            print(f"     → 建议：把每次 P(论点成立) 主动下调 {gap:.0%}，直到 Brier 校准回归。")

    cb = category_bias(decisions)
    if cb:
        print("\n  📉 按信心档的落空率（高信心却常落空 = 该档系统性高估）：")
        for c, n, miss in cb:
            flag = "  ⚠️高信心却常落空" if (c >= 4 and miss > 0.4) else ""
            print(f"     信心 {c}/5：落空率 {miss:.0%}（{n} 例）{flag}")

    print("\n  → 详细校准见 decision_journal.py calibrate；本报告聚焦「错误模式」维度。")


def main():
    ap = argparse.ArgumentParser(description="错误模式库与学习闭环（P4·治理，零依赖）")
    ap.add_argument("--patterns", default=PATTERNS)
    ap.add_argument("--postmortems", default=POSTMORTEMS)
    ap.add_argument("--decisions", default=DECISIONS)
    sub = ap.add_subparsers(dest="cmd")

    i = sub.add_parser("init", help="播种错误模式目录")
    i.add_argument("--force", action="store_true")

    sub.add_parser("catalog", help="列出所有错误模式")

    cl = sub.add_parser("checklist", help="事前验尸清单")
    cl.add_argument("--verbose", action="store_true", help="含大师语录")

    tg = sub.add_parser("tag", help="给失败决策打错误模式标签")
    tg.add_argument("--decision", type=int, required=True)
    tg.add_argument("--pattern", nargs="+", required=True)
    tg.add_argument("--note", default="")
    tg.add_argument("--lesson", default="", help="下次怎么做不一样")

    sub.add_parser("learn", help="频次 + 校准偏差 学习报告")

    args = ap.parse_args()
    {"init": cmd_init, "catalog": cmd_catalog, "checklist": cmd_checklist,
     "tag": cmd_tag, "learn": cmd_learn}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
