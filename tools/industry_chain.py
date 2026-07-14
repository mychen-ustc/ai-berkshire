#!/usr/bin/env python3
"""产业链图谱（T3-3，零外部依赖）。

上下游/供需/替代关系图，支持两类研究：
  1) "卖铲子"发现 —— 一个主题(如 AI)最确定的受益者往往在上游(给淘金者卖铲子的)，
     而非最热的下游应用。图谱帮你从主题顺藤摸到上游卖铲人。
  2) 传导路径 —— 一个环节的景气/冲击如何沿链条传导(AI需求→GPU→HBM→先进封装→…)。

图谱是**参考知识**(公开产业结构)，故存 config/industry_chain.json(入库、可版本化)，
播种一个 AI/半导体链示例；用户可 add-edge 扩充。

诚实边界：这是**结构关系图**，不含实时景气/份额数据；节点是"环节/公司类别"，落到
具体标的仍需自下而上研究。关系是人工整理的定性图，非全产业链数据库。

用法：
  python3 tools/industry_chain.py init                       # 播种 AI 链示例
  python3 tools/industry_chain.py shovels --theme AI应用      # 主题的上游"卖铲人"
  python3 tools/industry_chain.py path --from AI应用 --to 光刻机   # 传导路径
  python3 tools/industry_chain.py neighbors --node GPU
  python3 tools/industry_chain.py add-edge --from HBM --to 先进封装 --type 上游
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "config", "industry_chain.json")


# --------------------------------------------------------------------------
# 播种：AI/半导体产业链(定性结构，环节级)
# 边 (a, b, "上游") 表示 b 是 a 的上游供应(a 依赖 b)。
# --------------------------------------------------------------------------
def _seed():
    return {"edges": [
        ["AI应用", "云算力", "上游"],
        ["云算力", "AI服务器", "上游"],
        ["AI服务器", "GPU", "上游"],
        ["AI服务器", "散热", "上游"],
        ["AI服务器", "电源", "上游"],
        ["GPU", "HBM", "上游"],
        ["GPU", "先进封装", "上游"],
        ["GPU", "晶圆代工", "上游"],
        ["HBM", "存储芯片", "上游"],
        ["晶圆代工", "光刻机", "上游"],
        ["晶圆代工", "刻蚀设备", "上游"],
        ["晶圆代工", "EDA工具", "上游"],
        ["光刻机", "光学镜头", "上游"],
        ["光刻机", "光源", "上游"],
        ["先进封装", "封装设备", "上游"],
        ["电动车", "动力电池", "上游"],
        ["动力电池", "正极材料", "上游"],
        ["动力电池", "锂", "上游"],
        ["AI应用", "边缘AI", "替代"],
    ], "notes": "AI/半导体链示例(定性结构,环节级)。b 是 a 的上游=a 依赖 b。"}


# --------------------------------------------------------------------------
# 纯函数（可测）——图算法
# --------------------------------------------------------------------------
def upstream(edges, node):
    """node 的直接上游(它依赖谁)。纯函数。"""
    return [b for a, b, t in edges if a == node and t == "上游"]


def downstream(edges, node):
    """node 的直接下游(谁依赖它)。纯函数。"""
    return [a for a, b, t in edges if b == node and t == "上游"]


def substitutes(edges, node):
    """node 的替代关系。纯函数。"""
    return [b for a, b, t in edges if a == node and t == "替代"] + \
           [a for a, b, t in edges if b == node and t == "替代"]


def all_upstream(edges, node, max_depth=10):
    """node 的全部(递归)上游及深度。→ {upstream_node: depth}。防环。纯函数。"""
    seen = {}
    frontier = [(node, 0)]
    while frontier:
        cur, d = frontier.pop(0)
        if d >= max_depth:
            continue
        for u in upstream(edges, cur):
            if u not in seen or seen[u] > d + 1:
                seen[u] = d + 1
                frontier.append((u, d + 1))
    return seen


def shovel_candidates(edges, theme, min_depth=2):
    """主题的"卖铲人":深度≥min_depth 的上游(离应用越远、越基础设施、越"卖铲子")。
    按深度排序。纯函数。"""
    ups = all_upstream(edges, theme)
    return sorted([(n, d) for n, d in ups.items() if d >= min_depth], key=lambda x: x[1])


def transmission_path(edges, src, dst, max_depth=12):
    """src → dst 的上游传导路径(BFS 最短)。→ [节点列表] 或 None。纯函数。"""
    if src == dst:
        return [src]
    frontier = [[src]]
    seen = {src}
    while frontier:
        path = frontier.pop(0)
        if len(path) > max_depth:
            continue
        for u in upstream(edges, path[-1]):
            if u == dst:
                return path + [u]
            if u not in seen:
                seen.add(u)
                frontier.append(path + [u])
    return None


# --------------------------------------------------------------------------
# 存取
# --------------------------------------------------------------------------
def load(path=STORE):
    if not os.path.exists(path):
        return {"edges": [], "notes": ""}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(graph, path=STORE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
def cmd_init(args):
    if os.path.exists(args.path) and not args.force:
        print(f"⚠️ 图谱已存在：{args.path}（--force 覆盖）")
        return
    save(_seed(), args.path)
    print(f"✅ 已播种产业链图谱 → {args.path}（{len(_seed()['edges'])} 条边）")


def cmd_shovels(args):
    edges = load(args.path)["edges"]
    cands = shovel_candidates(edges, args.theme, args.min_depth)
    print("=" * 58)
    print(f'"卖铲子"发现 · 主题【{args.theme}】的上游受益者')
    print("=" * 58)
    if not cands:
        print(f"  未找到深度≥{args.min_depth}的上游(主题名不在图中或链太短)。")
        return
    print(f"  离应用越远(深度越大)、越基础设施、越'卖铲人':")
    for n, d in cands:
        print(f"    深度{d}  {'　'*d}└ {n}")
    print(f"\n  → 淘金热里,卖铲子的常最确定。但仍须自下而上落到具体标的+估值,图谱只给方向。")


def cmd_path(args):
    edges = load(args.path)["edges"]
    p = transmission_path(edges, args.frm, args.to)
    print("=" * 58)
    print(f"传导路径 · {args.frm} → {args.to}")
    print("=" * 58)
    if p:
        print("  " + " → ".join(p))
        print(f"\n  → {args.frm} 的景气/冲击沿此链上游传导至 {args.to}(共 {len(p)-1} 跳)。")
    else:
        print(f"  未找到 {args.frm} 到 {args.to} 的上游路径。")


def cmd_neighbors(args):
    edges = load(args.path)["edges"]
    print("=" * 50)
    print(f"环节关系 · {args.node}")
    print("=" * 50)
    print(f"  上游(它依赖): {', '.join(upstream(edges, args.node)) or '—'}")
    print(f"  下游(依赖它): {', '.join(downstream(edges, args.node)) or '—'}")
    subs = substitutes(edges, args.node)
    if subs:
        print(f"  替代关系:     {', '.join(subs)}")


def cmd_add_edge(args):
    graph = load(args.path)
    graph["edges"].append([args.frm, args.to, args.type])
    save(graph, args.path)
    print(f"✅ 已加边：{args.frm} --{args.type}--> {args.to}（共 {len(graph['edges'])} 条）")


def main():
    ap = argparse.ArgumentParser(description="产业链图谱(T3-3，卖铲子/传导路径，零依赖)")
    ap.add_argument("--path", default=STORE)
    sub = ap.add_subparsers(dest="cmd")

    i = sub.add_parser("init", help="播种 AI 链示例")
    i.add_argument("--force", action="store_true")

    sh = sub.add_parser("shovels", help="主题的上游卖铲人")
    sh.add_argument("--theme", required=True)
    sh.add_argument("--min-depth", dest="min_depth", type=int, default=2)

    pa = sub.add_parser("path", help="传导路径")
    pa.add_argument("--from", dest="frm", required=True)
    pa.add_argument("--to", required=True)

    ne = sub.add_parser("neighbors", help="某环节的上下游/替代")
    ne.add_argument("--node", required=True)

    ae = sub.add_parser("add-edge", help="加一条关系边")
    ae.add_argument("--from", dest="frm", required=True)
    ae.add_argument("--to", required=True)
    ae.add_argument("--type", default="上游", choices=["上游", "替代"])

    args = ap.parse_args()
    {"init": cmd_init, "shovels": cmd_shovels, "path": cmd_path,
     "neighbors": cmd_neighbors, "add-edge": cmd_add_edge}.get(
        args.cmd, lambda a: ap.print_help())(args)


if __name__ == "__main__":
    main()
