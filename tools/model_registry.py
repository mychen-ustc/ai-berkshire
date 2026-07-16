#!/usr/bin/env python3
"""模型登记册（P4·治理，零外部依赖）。

机构模型风险治理(对标 SR 11-7)：任何"产出会进入投资决策的数字"的模型，都必须
登记——用途、核心假设、已知局限、数据源、校验状态、上次校验日、复校周期、负责人。
这样才能回答监管与自省都会问的三个问题：
  1) 这个数字是哪个模型算的？它的假设是什么、什么时候会失效？
  2) 这个模型上次校验是什么时候？现在还在有效期内吗？
  3) 报告里用到的模型，是不是都还在"已校验"状态，没有过期或已弃用？

登记册本身入库(config/model_registry.json)作为审计轨迹——与私有持仓不同，模型
清单应当版本可追溯。

用法：
  python3 tools/model_registry.py init                 # 用当前工具链播种登记册
  python3 tools/model_registry.py list [--status validated|experimental|deprecated]
  python3 tools/model_registry.py show --id portfolio_risk
  python3 tools/model_registry.py validate --id tail_risk --date 2026-07-14 --by MartinChen
  python3 tools/model_registry.py audit [--today 2026-07-14]   # 过期 / 实验中 / 无测试
  python3 tools/model_registry.py add --id x --name .. --tool tools/x.py --category 风险 ...
"""
import argparse
import json
import os
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "config", "model_registry.json")

STATUSES = ("validated", "experimental", "deprecated")


# --------------------------------------------------------------------------
# 播种数据：把当前"产出决策数字"的核心模型登记在册
# 每条记录都是对该模型假设/局限的诚实声明——局限不是缺陷，是使用边界。
# --------------------------------------------------------------------------
def _seed():
    return [
        {"id": "financial_rigor", "name": "财务精确计算", "tool": "tools/financial_rigor.py",
         "category": "计算基座", "method": "Decimal 全程精确求值(PE/ROE/增速/复合)",
         "assumptions": ["输入财务数据准确", "口径一致(GAAP/非GAAP不混用)"],
         "limitations": ["不判断数据真伪，只保证不引入浮点误差", "不做勾稽校验"],
         "data_sources": ["调用方提供"], "tests": ["tests/test_financial_rigor.py"],
         "status": "validated", "validated_on": "2026-06-01", "revalidate_every_days": 365,
         "owner": "MartinChen"},
        {"id": "portfolio_risk", "name": "组合风险诊断", "tool": "tools/portfolio_risk.py",
         "category": "风险", "method": "年化波动/相关矩阵/最大回撤/集中度(HHI)，周频对数收益",
         "assumptions": ["历史波动近似未来", "收益近似平稳", "汇率折算到 base 币种"],
         "limitations": ["回撤依赖样本窗口长度(短窗低估)", "相关性在危机中会跳升", "不含尾部"],
         "data_sources": ["东财/腾讯/Yahoo 前复权 kline"], "tests": ["tests/test_portfolio_risk.py"],
         "status": "validated", "validated_on": "2026-07-01", "revalidate_every_days": 180,
         "owner": "MartinChen"},
        {"id": "tail_risk", "name": "尾部与压力测试", "tool": "tools/tail_risk.py",
         "category": "风险", "method": "VaR/CVaR(历史+参数法, Acklam 逆正态)/beta 映射压力/流动性天数",
         "assumptions": ["历史分布或正态近似", "beta 稳定", "参与率(ADV) 20%"],
         "limitations": ["VaR 不含未见过的黑天鹅", "参数法假设正态低估厚尾", "压力情景为假设非预测"],
         "data_sources": ["portfolio_risk 收益矩阵"], "tests": ["tests/test_tail_risk.py"],
         "status": "validated", "validated_on": "2026-07-13", "revalidate_every_days": 180,
         "owner": "MartinChen"},
        {"id": "portfolio_optimizer", "name": "组合优化器", "tool": "tools/portfolio_optimizer.py",
         "category": "组合构建", "method": "逆波动/风险平价(ERC平方根阻尼)/最小方差(Σ⁻¹1)/等权 + IPS上限",
         "assumptions": ["协方差可估且稳定", "无收益预测(只管风险)", "长仓(min-var 负权截零)"],
         "limitations": ["不预测收益", "min-var 对协方差估计误差敏感", "样本外协方差会漂移"],
         "data_sources": ["datalayer 历史收益"], "tests": ["tests/test_optimizer_math.py"],
         "status": "validated", "validated_on": "2026-07-14", "revalidate_every_days": 180,
         "owner": "MartinChen"},
        {"id": "rebalance", "name": "再平衡引擎", "tool": "tools/rebalance.py",
         "category": "组合构建", "method": "现状账本+目标权重→买卖股数/换汇缺口/成本估计/CSV",
         "assumptions": ["实时报价可得", "线性成本(bps)", "缺席目标=清仓"],
         "limitations": ["报价折算股数会滑动", "未含冲击成本", "跨币种需人工补FX行"],
         "data_sources": ["ledger 账本 + datalayer 报价"], "tests": ["tests/test_rebalance.py"],
         "status": "validated", "validated_on": "2026-07-14", "revalidate_every_days": 180,
         "owner": "MartinChen"},
        {"id": "position_sizing", "name": "仓位定量", "tool": "tools/position_sizing.py",
         "category": "组合构建", "method": "凯利/赔率赔率比 + 上限约束",
         "assumptions": ["赔率与胜率估计可靠", "用分数凯利(半凯利)防高估"],
         "limitations": ["凯利对胜率估计极敏感(高估→过度下注)", "单期模型不含路径风险"],
         "data_sources": ["调用方赔率假设"], "tests": ["tests/test_position_sizing.py"],
         "status": "validated", "validated_on": "2026-07-01", "revalidate_every_days": 180,
         "owner": "MartinChen"},
        {"id": "factor_model", "name": "因子/伪分散检测", "tool": "tools/factor_model.py",
         "category": "风险", "method": "收益相关矩阵 PCA(Jacobi 特征分解)，主成分暴露识别伪分散",
         "assumptions": ["线性相关捕捉共同驱动", "样本足够估计协方差"],
         "limitations": ["PCA 成分无经济含义标签(需人工解读)", "非线性依赖捕捉不到"],
         "data_sources": ["datalayer 历史收益"], "tests": ["tests/test_factor_model.py"],
         "status": "validated", "validated_on": "2026-07-05", "revalidate_every_days": 180,
         "owner": "MartinChen"},
        {"id": "decision_journal", "name": "决策校准(Brier)", "tool": "tools/decision_journal.py",
         "category": "治理", "method": "记录 P(论点成立)，resolve 后 Brier 分数 + 分桶校准 + 按信心分层",
         "assumptions": ["命中定义=达到基准目标价", "样本独立"],
         "limitations": ["小样本 Brier 噪声大(需≥20)", "命中/未中二值化损失信息"],
         "data_sources": ["data/portfolio/decisions.jsonl"], "tests": ["tests/test_decision_journal.py"],
         "status": "validated", "validated_on": "2026-07-01", "revalidate_every_days": 365,
         "owner": "MartinChen"},
        {"id": "attribution", "name": "业绩归因", "tool": "tools/attribution.py",
         "category": "治理", "method": "贡献分解(w×r) + Brinson(配置/选股/交互效应)",
         "assumptions": ["基准与分组口径一致", "区间收益可得"],
         "limitations": ["Brinson 单期，多期需几何链接(未实现)", "分组主观影响归因"],
         "data_sources": ["datalayer 区间收益 + 分组CSV"], "tests": ["tests/test_attribution.py"],
         "status": "validated", "validated_on": "2026-07-01", "revalidate_every_days": 365,
         "owner": "MartinChen"},
        {"id": "comps", "name": "可比公司估值", "tool": "tools/comps.py",
         "category": "估值", "method": "横截面 PE/PB/PS/EV倍数中位数 + 分位数",
         "assumptions": ["可比集可比(同业务/阶段/资本结构)", "会计口径可比"],
         "limitations": ["负PE需剔除或标注", "相对估值传染泡沫(全行业高估时误判便宜)"],
         "data_sources": ["腾讯/东财 倍数"], "tests": ["tests/test_comps.py"],
         "status": "validated", "validated_on": "2026-07-08", "revalidate_every_days": 180,
         "owner": "MartinChen"},
        {"id": "statement_model", "name": "三表建模", "tool": "tools/statement_model.py",
         "category": "估值", "method": "利润表/资产负债表/现金流预测 + DCF",
         "assumptions": ["增长/利润率/资本开支假设", "永续增长<折现率"],
         "limitations": ["DCF 对终值与折现率极敏感", "假设即结论(需情景分析佐证)"],
         "data_sources": ["调用方假设 + 历史财报"], "tests": ["tests/test_statement_model.py"],
         "status": "validated", "validated_on": "2026-07-08", "revalidate_every_days": 180,
         "owner": "MartinChen"},
        {"id": "scenario", "name": "情景/敏感性分析", "tool": "tools/scenario.py",
         "category": "估值", "method": "多情景加权 + 单变量敏感性",
         "assumptions": ["情景概率主观赋值", "变量间独立(单变量扫描)"],
         "limitations": ["概率主观", "忽略变量联动"], "data_sources": ["调用方假设"],
         "tests": ["tests/test_scenario.py"], "status": "validated",
         "validated_on": "2026-07-08", "revalidate_every_days": 365, "owner": "MartinChen"},
        {"id": "macro_regime", "name": "宏观 Regime", "tool": "tools/macro_regime.py",
         "category": "宏观", "method": "PMI/CPI/M2/利率 判别宏观状态(扩张/滞胀/衰退/复苏)",
         "assumptions": ["指标领先/同步关系稳定", "阈值划分合理"],
         "limitations": ["Regime 转折点事后才清晰", "阈值划分主观", "不预测拐点"],
         "data_sources": ["东财宏观 + Yahoo ^TNX/VIX"], "tests": ["tests/test_macro_regime.py"],
         "status": "validated", "validated_on": "2026-07-09", "revalidate_every_days": 180,
         "owner": "MartinChen"},
        {"id": "security_master", "name": "证券主数据 + PIT", "tool": "tools/security_master.py",
         "category": "事实源", "method": "内部ID + 时点(PIT)快照，pit_latest 剔除 as_of>日期防前视",
         "assumptions": ["快照 as_of 日期准确", "同一标的 market+symbol 唯一"],
         "limitations": ["退市/更名需手工维护快照", "不自动纠错源数据"],
         "data_sources": ["datalayer detect/quote"], "tests": ["tests/test_security_master.py"],
         "status": "validated", "validated_on": "2026-07-13", "revalidate_every_days": 365,
         "owner": "MartinChen"},
        {"id": "report_audit", "name": "报告数据抽检 + 硬门禁", "tool": "tools/report_audit.py",
         "category": "治理", "method": "抽15%数据点双源核验 + 门禁(来源覆盖/主观词/估计标注/幻觉抽检)",
         "assumptions": ["报告为 Markdown", "数字附近有来源标注"],
         "limitations": ["正则提取覆盖不全(复杂表格漏检)", "门禁是启发式非语义理解"],
         "data_sources": ["报告文本 + 人工/网络核验值"], "tests": ["tests/test_report_gate.py"],
         "status": "validated", "validated_on": "2026-07-14", "revalidate_every_days": 180,
         "owner": "MartinChen"},
    ]


# --------------------------------------------------------------------------
# 纯函数（可测）
# --------------------------------------------------------------------------
def _parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def days_since_validation(entry, today):
    """距上次校验的天数；today/validated_on 为 date。未校验返回 None。"""
    if not entry.get("validated_on"):
        return None
    return (today - _parse_date(entry["validated_on"])).days


def needs_revalidation(entry, today):
    """是否已过复校周期。deprecated 不再要求复校。"""
    if entry.get("status") == "deprecated":
        return False
    d = days_since_validation(entry, today)
    if d is None:
        return True
    return d > int(entry.get("revalidate_every_days", 365))


def missing_test_files(entry, root):
    """登记项声明的 test 文件里，磁盘上实际不存在的那些。root=仓库根。纯函数(仅 stat)。"""
    return [t for t in (entry.get("tests") or [])
            if not os.path.exists(t if os.path.isabs(t) else os.path.join(root, t))]


def audit_findings(entries, today, root=None):
    """→ {overdue, experimental, untested, tests_missing}。治理体检的问题模型分类。

    tests_missing：status 标 validated 却引用了磁盘上不存在的测试文件——
    此前 audit 只判 tests 字段非空、从不 stat 文件，对"已验证但测试文件不存在"结构性失明
    (诊断审计发现的治理盲区)。传 root 才启用该检查。"""
    overdue, experimental, untested, tests_missing = [], [], [], []
    for e in entries:
        if needs_revalidation(e, today):
            overdue.append(e)
        if e.get("status") == "experimental":
            experimental.append(e)
        if not e.get("tests"):
            untested.append(e)
        if root is not None and e.get("tests"):
            miss = missing_test_files(e, root)
            if miss:
                tests_missing.append({"entry": e, "missing": miss})
    return {"overdue": overdue, "experimental": experimental,
            "untested": untested, "tests_missing": tests_missing}


# --------------------------------------------------------------------------
# 存取
# --------------------------------------------------------------------------
def load(path=REGISTRY):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(entries, path=REGISTRY):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def _today(args):
    return _parse_date(args.today) if getattr(args, "today", None) else date.today()


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
def cmd_init(args):
    if os.path.exists(args.path) and not args.force:
        print(f"⚠️ 登记册已存在：{args.path}（--force 覆盖重播种）")
        return
    save(_seed(), args.path)
    print(f"✅ 已播种模型登记册 → {args.path}（{len(_seed())} 个模型）")


def cmd_list(args):
    entries = load(args.path)
    if args.status:
        entries = [e for e in entries if e.get("status") == args.status]
    print(f"模型登记册（{len(entries)} 个）")
    ic = {"validated": "✅", "experimental": "🧪", "deprecated": "⚰️"}
    for e in sorted(entries, key=lambda x: (x.get("category", ""), x["id"])):
        print(f"  {ic.get(e.get('status'), '?')} {e['id']:<20} [{e.get('category','?'):<6}] "
              f"{e['name']:<16} 上次校验 {e.get('validated_on','—')}")


def cmd_show(args):
    entries = {e["id"]: e for e in load(args.path)}
    e = entries.get(args.id)
    if not e:
        raise SystemExit(f"未找到模型 #{args.id}")
    print("=" * 66)
    print(f"模型：{e['name']}  [{e['id']}]   状态：{e.get('status')}")
    print("=" * 66)
    print(f"  文件      : {e.get('tool')}")
    print(f"  分类      : {e.get('category')}")
    print(f"  方法      : {e.get('method')}")
    print(f"  核心假设  :")
    for a in e.get("assumptions", []):
        print(f"    · {a}")
    print(f"  已知局限  :")
    for l in e.get("limitations", []):
        print(f"    ⚠ {l}")
    print(f"  数据源    : {', '.join(e.get('data_sources', []))}")
    print(f"  测试      : {', '.join(e.get('tests', [])) or '（无！）'}")
    print(f"  负责人    : {e.get('owner','—')}")
    print(f"  上次校验  : {e.get('validated_on','—')}  ·  复校周期 {e.get('revalidate_every_days')}天")


def cmd_validate(args):
    entries = load(args.path)
    for e in entries:
        if e["id"] == args.id:
            e["validated_on"] = args.date
            if args.status:
                e["status"] = args.status
            if args.by:
                e["owner"] = args.by
            save(entries, args.path)
            print(f"✅ 模型 {args.id} 已记录校验：{args.date}"
                  + (f"（状态→{args.status}）" if args.status else ""))
            return
    raise SystemExit(f"未找到模型 #{args.id}")


def cmd_add(args):
    entries = load(args.path)
    if any(e["id"] == args.id for e in entries):
        raise SystemExit(f"模型 {args.id} 已存在，请用 validate 更新")
    entries.append({
        "id": args.id, "name": args.name, "tool": args.tool, "category": args.category,
        "method": args.method or "", "assumptions": args.assumptions or [],
        "limitations": args.limitations or [], "data_sources": args.data_sources or [],
        "tests": args.tests or [], "status": args.status or "experimental",
        "validated_on": args.date, "revalidate_every_days": args.revalidate_every_days,
        "owner": args.by or "",
    })
    save(entries, args.path)
    print(f"✅ 已登记模型 {args.id}（状态 {args.status or 'experimental'}）")


def cmd_audit(args):
    entries = load(args.path)
    today = _today(args)
    f = audit_findings(entries, today, root=ROOT)
    print("=" * 66)
    print(f"模型治理体检 · {today} · 在册 {len(entries)} 个")
    print("=" * 66)
    if f["overdue"]:
        print(f"\n  🔴 已过复校期（{len(f['overdue'])}）——数字仍在用但模型未按期复核：")
        for e in f["overdue"]:
            d = days_since_validation(e, today)
            age = f"{d}天前" if d is not None else "从未校验"
            print(f"     · {e['id']:<20} 上次 {e.get('validated_on','—')}（{age}，周期{e.get('revalidate_every_days')}天）")
    if f["experimental"]:
        print(f"\n  🧪 实验中（{len(f['experimental'])}）——产出未定稿，报告引用需显式标注：")
        for e in f["experimental"]:
            print(f"     · {e['id']:<20} {e['name']}")
    if f["untested"]:
        print(f"\n  ⚠️  无回归测试（{len(f['untested'])}）：")
        for e in f["untested"]:
            print(f"     · {e['id']:<20} {e['name']}")
    if f["tests_missing"]:
        print(f"\n  🔴 测试文件缺失（{len(f['tests_missing'])}）——标 validated 却引用不存在的测试(治理剧场)：")
        for m in f["tests_missing"]:
            e = m["entry"]
            print(f"     · {e['id']:<20} 缺 {', '.join(m['missing'])}")
    if not any(f.values()):
        print("\n  ✅ 全部模型在有效期内、均已校验、均有测试——治理健康。")
    print()


def main():
    ap = argparse.ArgumentParser(description="模型登记册：治理量化模型的假设/局限/校验（零依赖）")
    ap.add_argument("--path", default=REGISTRY)
    sub = ap.add_subparsers(dest="cmd")

    i = sub.add_parser("init", help="用当前工具链播种登记册")
    i.add_argument("--force", action="store_true")

    li = sub.add_parser("list", help="列出在册模型")
    li.add_argument("--status", choices=STATUSES)

    sh = sub.add_parser("show", help="查看单个模型详情")
    sh.add_argument("--id", required=True)

    v = sub.add_parser("validate", help="记录一次校验")
    v.add_argument("--id", required=True)
    v.add_argument("--date", required=True)
    v.add_argument("--status", choices=STATUSES)
    v.add_argument("--by", default="")

    ad = sub.add_parser("add", help="登记新模型")
    ad.add_argument("--id", required=True)
    ad.add_argument("--name", required=True)
    ad.add_argument("--tool", required=True)
    ad.add_argument("--category", required=True)
    ad.add_argument("--method")
    ad.add_argument("--assumptions", nargs="*")
    ad.add_argument("--limitations", nargs="*")
    ad.add_argument("--data-sources", dest="data_sources", nargs="*")
    ad.add_argument("--tests", nargs="*")
    ad.add_argument("--status", choices=STATUSES)
    ad.add_argument("--date", required=True)
    ad.add_argument("--revalidate-every-days", dest="revalidate_every_days", type=int, default=180)
    ad.add_argument("--by", default="")

    au = sub.add_parser("audit", help="过期/实验中/无测试 体检")
    au.add_argument("--today", help="YYYY-MM-DD（默认今天）")

    args = ap.parse_args()
    {"init": cmd_init, "list": cmd_list, "show": cmd_show, "validate": cmd_validate,
     "add": cmd_add, "audit": cmd_audit}.get(args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
