#!/usr/bin/env python3
"""Report Audit Tool for AI Berkshire.

数据抽检工具：从研究报告中抽取15%的财务数据点，与可靠信源比对，
通过则准出，不通过则打回并说明原因。

Zero external dependencies — uses only Python stdlib.
Requires Python >= 3.7.

工作流程（三步）：
  Step 1 — 提取数据点，随机抽样15%：
    python3 tools/report_audit.py extract --report reports/xxx.md

  Step 2 — Claude 对抽检清单中的每个数据点，从可靠信源（macrotrends/
            stockanalysis/aastocks/eastmoney）取数，填入 fetched_value

  Step 3 — 输入核验结果，输出准出/打回判决：
    python3 tools/report_audit.py verdict --results '[...]'

  一步完成（仅提取+打印抽检清单，不做网络验证）：
    python3 tools/report_audit.py extract --report reports/xxx.md --dry-run
"""

import argparse
import json
import math
import os
import re
import sys
from decimal import Decimal, Context, ROUND_HALF_EVEN
from random import Random

_CTX = Context(prec=28, rounding=ROUND_HALF_EVEN)

# ---------------------------------------------------------------------------
# 数据点提取：从 Markdown 报告中识别财务数字
# ---------------------------------------------------------------------------

# 匹配模式：数字 + 单位，前面有上下文标签
# 例：收入：1,239亿元、PE 18.8x、毛利率 56%、市值 ~$5,670亿
_PATTERNS = [
    # 百分比
    (r'([\d,，\.]+)\s*%',                        '%',    'percent'),
    # 亿元/亿美元/亿港元
    (r'([\d,，\.]+)\s*亿(元|美元|港元|RMB|USD|HKD)?', '亿',    'hundred_million'),
    # 倍数 PE/PB/PS
    (r'([\d,，\.]+)\s*[xX倍]',                   'x',    'multiple'),
    # 万亿
    (r'([\d,，\.]+)\s*万亿',                      '万亿', 'trillion'),
    # 美元绝对值（B/T）
    (r'\$\s*([\d,，\.]+)\s*([BMT亿])',             '$',    'usd_abs'),
    # 纯整数（如市值、收入、用户数等，出现在表格 | 里）
    (r'\|\s*[~约]?\$?([\d,，\.]+)\s*\|',          '',     'table_num'),
]

_LABEL_RE = re.compile(
    r'(?P<label>[^\|\n：:]{2,25})[：:\s]+[~约]?\$?(?P<num>[\d,，\.]+)\s*(?P<unit>亿[元美港]?元?|万亿|[xX倍]|%|[BMT])?'
)

_TABLE_ROW_RE = re.compile(
    r'\|\s*(?P<label>[^|]{1,40})\s*\|\s*[~约]?\$?(?P<num>[\d,，\.]+)\s*(?P<unit>亿[元美港]?元?|万亿|[xX倍]|%|[BMT])?\s*\|'
)


def _clean_num(s: str) -> float:
    """把带逗号、中文逗号的数字字符串转为 float。"""
    s = s.replace(',', '').replace('，', '').strip()
    try:
        return float(s)
    except ValueError:
        return None


def _is_valid_label(label: str) -> bool:
    """判断标签是否是有意义的财务字段名，过滤噪声。"""
    label = label.strip()
    # 太短
    if len(label) < 2:
        return False
    # 纯数字或纯年份
    if re.fullmatch(r'[\d\s年季度Q]+', label):
        return False
    # 以符号/markdown标记开头
    if re.match(r'^[+\-\*#\|~\$>_`]', label):
        return False
    # 含有 markdown 粗体/代码标记
    if '**' in label or '`' in label or '__' in label:
        return False
    # 标签含有纯增速符号（如 +56%、-13% 单独作标签）
    if re.fullmatch(r'[+\-]?\d+(\.\d+)?%', label):
        return False
    # 常见无意义标签
    _SKIP = {'来源', 'sources', 'source', '说明', '注意', '备注', '数据来源',
             'n/a', '—', '-', '/', '合计', 'total', '单位', '趋势'}
    if label.lower() in _SKIP:
        return False
    return True


# 两列表格行：| 标签 | 数值 unit |（专为财务报告的 KV 表设计）
_KV_TABLE_RE = re.compile(
    r'^\|\s*(?P<label>[^|*\n]{2,40}?)\s*\|\s*[~约]?\$?(?P<num>[\d,，\.]+)\s*'
    r'(?P<unit>亿[元美港]?元?|万亿|[xX倍]|%|[BMT亿])?\s*[\|（\(]'
)

# 带标签的 KV 行：标签：数值 单位
_KV_LABEL_RE = re.compile(
    r'(?P<label>[\u4e00-\u9fa5A-Za-z][^\|\n：:*]{1,30})[：:]\s*[~约]?\$?'
    r'(?P<num>[\d,，\.]+)\s*(?P<unit>亿[元美港]?元?|万亿|[xX倍]|%|[BMT])?'
)


def _parse_md_tables(lines: list) -> list:
    """解析 Markdown 中所有表格，返回 (row_label, col_header, value, unit, lineno, raw) 列表。"""
    results = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 检测表头行（含 | 且不是分隔行）
        if '|' in line and not re.match(r'^\|[\-\s\|:]+\|$', line):
            headers_raw = [h.strip().strip('*_').strip() for h in line.split('|')]
            headers_raw = [h for h in headers_raw if h]
            # 下一行应是分隔行
            if i + 1 < len(lines) and re.match(r'^\|[\-\s\|:]+\|$', lines[i+1].strip()):
                i += 2  # 跳过分隔行
                # 读数据行
                while i < len(lines):
                    dline = lines[i].strip()
                    if not dline or not dline.startswith('|'):
                        break
                    cells = [c.strip().strip('*_~').strip() for c in dline.split('|')]
                    cells = [c for c in cells if c != '']
                    if len(cells) < 2:
                        i += 1
                        continue
                    row_label = cells[0]
                    for col_idx, cell in enumerate(cells[1:], start=1):
                        col_header = headers_raw[col_idx] if col_idx < len(headers_raw) else f'列{col_idx}'
                        # 提取 cell 中的数字+单位
                        m = re.search(
                            r'[~约]?\$?([\d,，\.]+)\s*(亿[元美港]?元?|万亿|[xX倍]|%|[BMT])?',
                            cell
                        )
                        if m:
                            val = _clean_num(m.group(1))
                            unit = (m.group(2) or '').strip()
                            if val and val != 0 and val < 1e15:
                                results.append((row_label, col_header, val, unit, i + 1, dline))
                    i += 1
                continue
        i += 1
    return results


def extract_data_points(md_text: str) -> list:
    """从 Markdown 报告中提取所有可识别的财务数据点。

    覆盖三类结构：
      1. 多列 Markdown 表格（最主要的来源）：(行标签 + 列标题) → 数值
      2. 带冒号的 KV 行：标签：数值 单位
      3. 加粗数字行：**数值** 单位

    返回 list of dict：
      {id, label, reported_value, unit, raw_text, line_number}
    """
    points = []
    seen = set()

    def _add(label, val, unit, lineno, raw):
        label = re.sub(r'[\*_`]+', '', label).strip()
        if not _is_valid_label(label):
            return
        if val is None or val == 0 or val > 1e15:
            return
        # 过滤纯年份/季度
        if re.fullmatch(r'(20\d{2}|Q[1-4]|\d{4}\s*Q[1-4])', label.strip()):
            return
        key = f"{label}|{round(val,4)}|{unit}"
        if key in seen:
            return
        seen.add(key)
        points.append({
            'id': len(points) + 1,
            'label': label,
            'reported_value': val,
            'unit': unit,
            'raw_text': raw[:120],
            'line_number': lineno,
        })

    lines = md_text.split('\n')
    in_code = False

    # --- 1. 多列表格 ---
    for row_label, col_header, val, unit, lineno, raw in _parse_md_tables(lines):
        # 跳过无意义行标签
        if not _is_valid_label(row_label):
            continue
        # 跳过无意义列标题（YoY增速列单独标注，不作为待核验数据）
        if col_header.upper() in ('YOY', 'YOY增速', '增速', '同比', '变化', '趋势', '说明', '备注'):
            continue
        # label = "行标签 · 列标题"（若列标题是行标签的补充）
        if col_header and col_header != row_label:
            label = f"{row_label} · {col_header}"
        else:
            label = row_label
        _add(label, val, unit, lineno, raw)

    # --- 2. KV 冒号行 ---
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code = not in_code
            continue
        if in_code or stripped.startswith('> ') or re.match(r'^#{1,6}\s', stripped):
            continue
        if '|' in stripped:
            continue  # 表格已在上面处理

        for m in _KV_LABEL_RE.finditer(stripped):
            label = m.group('label')
            val = _clean_num(m.group('num'))
            unit = (m.group('unit') or '').strip()
            _add(label, val, unit, lineno, stripped)

    return points


def sample_points(points: list, ratio: float = 0.15, seed: int = None) -> list:
    """随机抽取 ratio 比例的数据点，最少 3 个，最多 30 个。"""
    n = max(3, min(30, math.ceil(len(points) * ratio)))
    n = min(n, len(points))
    rng = Random(seed)
    sampled = rng.sample(points, n)
    # 按行号排序，方便人工比对
    return sorted(sampled, key=lambda p: p['line_number'])


# ---------------------------------------------------------------------------
# 准出/打回判决
# ---------------------------------------------------------------------------

_TOLERANCE = 0.01   # 1% 容差


def _pct_diff(reported: float, fetched: float) -> float:
    """相对偏差 (absolute)。"""
    if reported == 0:
        return 0.0 if fetched == 0 else float('inf')
    return abs(reported - fetched) / abs(reported)


def render_verdict(results: list, report_name: str = "") -> dict:
    """
    根据核验结果输出准出/打回判决。

    results: list of dict，每项包含：
      - id, label, reported_value, unit, fetched_value, fetched_source
      - (可选) fetched_value2, fetched_source2   ← 第二来源

    返回：
      {
        'verdict': 'PASS' | 'FAIL',
        'pass_count': int,
        'fail_count': int,
        'total': int,
        'fail_items': [...],
        'summary': str,
      }
    """
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'

    print('=' * 70)
    print(f'{BOLD}报告数据抽检 — 准出/打回判决{RESET}')
    if report_name:
        print(f'报告：{report_name}')
    print('=' * 70)
    print()

    fail_items = []
    warn_items = []

    for item in results:
        label = item.get('label', '?')
        reported = float(item.get('reported_value', 0))
        unit = item.get('unit', '')
        fetched = item.get('fetched_value')
        source = item.get('fetched_source', '?')
        fetched2 = item.get('fetched_value2')
        source2 = item.get('fetched_source2', '')

        # --- 主来源比对 ---
        if fetched is None:
            # 没有提供核验值 → 跳过（不计入通过/失败）
            print(f'  ⬜ [{item["id"]:>2}] {label[:35]:35s} {reported:>12.2f} {unit}  →  [未提供核验值，跳过]')
            continue

        fetched = float(fetched)
        diff1 = _pct_diff(reported, fetched)

        # --- 第二来源比对（如有）---
        diff2 = None
        if fetched2 is not None:
            fetched2 = float(fetched2)
            diff2 = _pct_diff(reported, fetched2)

        # 判断
        pass1 = diff1 <= _TOLERANCE
        pass2 = (diff2 is None) or (diff2 <= _TOLERANCE)

        if pass1 and pass2:
            status = f'{GREEN}✅ 通过{RESET}'
            detail = f'{source}: {fetched:.2f} (偏差 {diff1*100:.2f}%)'
            if diff2 is not None:
                detail += f'  |  {source2}: {fetched2:.2f} (偏差 {diff2*100:.2f}%)'
        elif not pass1 and not pass2:
            status = f'{RED}❌ 不通过{RESET}'
            detail = f'{source}: {fetched:.2f} (偏差 {diff1*100:.2f}%)'
            if diff2 is not None:
                detail += f'  |  {source2}: {fetched2:.2f} (偏差 {diff2*100:.2f}%)'
            fail_items.append({
                'id': item['id'],
                'label': label,
                'reported': reported,
                'unit': unit,
                'fetched': fetched,
                'source': source,
                'fetched2': fetched2,
                'source2': source2,
                'diff1_pct': round(diff1 * 100, 2),
                'diff2_pct': round(diff2 * 100, 2) if diff2 is not None else None,
                'raw_text': item.get('raw_text', ''),
                'line_number': item.get('line_number', 0),
            })
        else:
            # 一个来源通过，一个不通过 → 警告，不计入失败
            status = f'{YELLOW}⚠️  警告{RESET}'
            detail = f'{source}: {fetched:.2f} (偏差 {diff1*100:.2f}%)'
            if diff2 is not None:
                detail += f'  |  {source2}: {fetched2:.2f} (偏差 {diff2*100:.2f}%)'
            warn_items.append({
                'id': item['id'], 'label': label,
                'reported': reported, 'unit': unit,
                'diff1_pct': round(diff1 * 100, 2),
                'diff2_pct': round(diff2 * 100, 2) if diff2 is not None else None,
            })

        print(f'  {status} [{item["id"]:>2}] {label[:35]:35s}  报告: {reported:>12.2f} {unit}')
        print(f'              {" " * 38}{detail}')

    print()
    print('-' * 70)

    total = len([r for r in results if r.get('fetched_value') is not None])
    fail_count = len(fail_items)
    warn_count = len(warn_items)
    pass_count = total - fail_count - warn_count

    print(f'  抽检总数: {total}  |  通过: {GREEN}{pass_count}{RESET}  |  警告: {YELLOW}{warn_count}{RESET}  |  不通过: {RED}{fail_count}{RESET}')
    print()

    if fail_count == 0:
        print(f'{BOLD}{GREEN}【准出】所有抽检数据通过，报告可发布。{RESET}')
        verdict = 'PASS'
    else:
        print(f'{BOLD}{RED}【打回】{fail_count} 个数据点核验不通过，报告需修正后重审。{RESET}')
        print()
        print(f'{BOLD}打回原因：{RESET}')
        for fi in fail_items:
            print(f'  ❌ 第 {fi["line_number"]} 行 | {fi["label"]}')
            print(f'     报告值：{fi["reported"]} {fi["unit"]}')
            print(f'     {fi["source"]}：{fi["fetched"]}  （偏差 {fi["diff1_pct"]}%）')
            if fi.get('fetched2') is not None:
                print(f'     {fi["source2"]}：{fi["fetched2"]}  （偏差 {fi["diff2_pct"]}%）')
            print(f'     原文：{fi["raw_text"][:80]}')
            print()
        verdict = 'FAIL'

    if warn_count > 0:
        print(f'{YELLOW}注意：{warn_count} 个数据点两来源结果不一致（超过1%），可能是口径差异（GAAP/Non-GAAP或汇率），请人工复核。{RESET}')
        for wi in warn_items:
            print(f'  ⚠️  {wi["label"]}  报告:{wi["reported"]} {wi["unit"]}  偏差: {wi["diff1_pct"]}% / {wi["diff2_pct"]}%')

    print('=' * 70)

    return {
        'verdict': verdict,
        'pass_count': pass_count,
        'warn_count': warn_count,
        'fail_count': fail_count,
        'total': total,
        'fail_items': fail_items,
        'warn_items': warn_items,
    }


# ---------------------------------------------------------------------------
# AI 硬门禁：发布前的结构性防线（在"数据抽检"之前先过这一关）
#   1) 来源可核    — 量化断言附近须有来源标注；无源的具体数字=幻觉风险
#   2) 主观词拒答  — CLAUDE.md 禁用"我认为/显然/毫无疑问"等主观表述
#   3) 估计须标注  — 预测/估算值须标"估计"，不得冒充事实
#   4) 交叉验证    — 关键数据应有 ≥2 来源
# 门禁是启发式(正则)非语义理解——它降低幻觉与无据断言的概率，不替代人工与数据抽检。
# ---------------------------------------------------------------------------

# 主观表述黑名单（CLAUDE.md 明令禁止）。"绝对"用具体搭配以避开"绝对值/绝对规模"等技术词。
_SUBJECTIVE = ["我认为", "我觉得", "我相信", "显然", "毫无疑问", "众所周知",
               "肯定会", "一定会", "必然会", "绝对会", "绝对能", "绝对不", "绝对是", "绝对安全"]

# 来源标记：出现这些词/结构，视为该行/邻近有来源支撑
_SOURCE_MARKERS = [
    "来源", "数据来源", "source", "根据", "据", "引自", "出自", "披露", "财报", "年报", "季报",
    "招股书", "公告", "macrotrends", "stockanalysis", "aastocks", "eastmoney", "东财", "东方财富",
    "腾讯", "yahoo", "finnhub", "edgar", "wind", "彭博", "bloomberg", "reuters", "路透",
    "cninfo", "巨潮", "sec", "10-k", "10-q", "20-f", "http",
]

# 前瞻/估算语境词：出现则该数字应被视为"估计"，须有估计标注。
# 只保留"真前瞻"词——历史年份(FY2025/2026Q1)是已发生事实不算前瞻，故不含裸年份。
_FORWARD_CTX = ["预计", "预测", "假设", "目标价", "展望", "guidance",
                "指引", "有望", "或将", "预期", "远期", "隐含", "测算"]
# 显式远期估计年记法：2027E / 2026e（带 E 后缀才是估计年）
_FORWARD_YEAR_RE = re.compile(r'20\d{2}\s*[eE]\b')
_ESTIMATE_TAGS = ["估计", "估算", "预计", "预测", "假设", "约", "~", "e)", "（e", "(e", "est"]


def _has_marker(text, markers):
    low = text.lower()
    return any(m.lower() in low for m in markers)


def gate_report(md_text: str) -> dict:
    """报告发布前硬门禁。返回结构化判决：来源覆盖率、主观词、未标注估计、交叉验证。纯函数。"""
    lines = md_text.split("\n")
    in_code = False

    subjective_hits = []           # (lineno, word, text)
    unsourced_claims = []          # 有量化数字但邻近无来源
    unlabeled_estimates = []       # 前瞻语境的数字但未标"估计"
    quant_lines = 0
    sourced_lines = 0

    # 数字模式：具体的量化断言（百分比/亿/倍/美元额），排除纯列表序号/年份
    num_re = re.compile(r'([\d,，\.]+)\s*(%|亿|万亿|[xX倍]|[BMT])|[$¥￥]\s*[\d,，\.]+')

    for lineno, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not stripped or re.match(r'^#{1,6}\s', stripped):
            continue
        # 表格分隔行跳过
        if re.match(r'^\|[\-\s\|:]+\|$', stripped):
            continue

        # 1) 主观词（跳过引用块——大师语录里的"我觉得"是被引用的，非分析者本人口吻）
        if not stripped.startswith(">"):
            for w in _SUBJECTIVE:
                if w in stripped:
                    subjective_hits.append((lineno, w, stripped[:80]))

        # 2/4) 量化断言 → 来源覆盖
        has_num = bool(num_re.search(stripped))
        # 过滤纯年份行（如 "2026Q1"）——不是量化断言
        only_year = re.fullmatch(r'[\s\|\-]*20\d{2}\s*(Q[1-4])?[\s\|\-]*', stripped)
        if has_num and not only_year:
            quant_lines += 1
            # 来源可以在本行、上一行、下一行（表格常把"来源"放脚注）
            window = stripped
            if lineno - 2 >= 0:
                window += " " + lines[lineno - 2]
            if lineno < len(lines):
                window += " " + lines[lineno]
            if _has_marker(window, _SOURCE_MARKERS):
                sourced_lines += 1
            else:
                unsourced_claims.append((lineno, stripped[:80]))

            # 3) 前瞻语境但未标注估计（真前瞻词 或 显式 YYYYE 记法）
            is_forward = _has_marker(stripped, _FORWARD_CTX) or bool(_FORWARD_YEAR_RE.search(stripped))
            if is_forward and not _has_marker(stripped, _ESTIMATE_TAGS):
                # 排除历史年份陈述（含"实现/录得/去年"等已发生词）
                if not _has_marker(stripped, ["实现", "录得", "去年", "上季", "同比", "环比", "已"]):
                    unlabeled_estimates.append((lineno, stripped[:80]))

    coverage = (sourced_lines / quant_lines) if quant_lines else 1.0

    # 交叉验证信号：全文出现"两来源/交叉验证/复核"或多个不同来源名
    distinct_sources = set()
    low = md_text.lower()
    for m in _SOURCE_MARKERS:
        if m.lower() in low and m not in ("来源", "数据来源", "source", "根据", "据"):
            distinct_sources.add(m)
    cross_verified = len(distinct_sources) >= 2 or _has_marker(md_text, ["交叉验证", "两个来源", "双源", "两来源", "互相印证"])

    # 判决规则
    reasons = []
    if subjective_hits:
        reasons.append(f"含 {len(subjective_hits)} 处主观表述（CLAUDE.md 禁用）")
    if coverage < 0.6 and quant_lines >= 5:
        reasons.append(f"量化断言来源覆盖率仅 {coverage:.0%}（<60%），存在无据数字")
    if len(unlabeled_estimates) > 3:
        reasons.append(f"{len(unlabeled_estimates)} 处前瞻数字未标注「估计」")
    if not cross_verified and quant_lines >= 10:
        reasons.append("未见交叉验证/多来源（关键数据应 ≥2 来源）")

    verdict = "PASS" if not reasons else "FAIL"
    return {
        "verdict": verdict, "reasons": reasons,
        "quant_lines": quant_lines, "sourced_lines": sourced_lines, "coverage": round(coverage, 3),
        "subjective_hits": subjective_hits, "unsourced_claims": unsourced_claims,
        "unlabeled_estimates": unlabeled_estimates,
        "distinct_sources": sorted(distinct_sources), "cross_verified": cross_verified,
    }


def render_gate(res: dict, report_name: str = "") -> None:
    BOLD, RED, GREEN, YELLOW, RESET = '\033[1m', '\033[91m', '\033[92m', '\033[93m', '\033[0m'
    print("=" * 70)
    print(f"{BOLD}AI 硬门禁 — 报告发布前结构性防线{RESET}")
    if report_name:
        print(f"报告：{report_name}")
    print("=" * 70)
    cov = res["coverage"]
    cov_c = GREEN if cov >= 0.6 else RED
    print(f"  量化断言 {res['quant_lines']} 行  ·  有来源 {res['sourced_lines']} 行  ·  "
          f"来源覆盖率 {cov_c}{cov:.0%}{RESET}")
    print(f"  交叉验证：{(GREEN+'✓ 多来源') if res['cross_verified'] else (YELLOW+'⚠ 未见多来源')}{RESET}"
          + (f"（{', '.join(res['distinct_sources'])}）" if res['distinct_sources'] else ""))
    if res["subjective_hits"]:
        print(f"\n  {RED}❌ 主观表述（{len(res['subjective_hits'])}）：{RESET}")
        for ln, w, t in res["subjective_hits"][:10]:
            print(f"     第{ln}行「{w}」: {t}")
    if res["unsourced_claims"]:
        print(f"\n  {YELLOW}⚠️  无来源标注的量化断言（{len(res['unsourced_claims'])}，抽样）：{RESET}")
        for ln, t in res["unsourced_claims"][:8]:
            print(f"     第{ln}行: {t}")
    if res["unlabeled_estimates"]:
        print(f"\n  {YELLOW}⚠️  前瞻数字未标「估计」（{len(res['unlabeled_estimates'])}，抽样）：{RESET}")
        for ln, t in res["unlabeled_estimates"][:8]:
            print(f"     第{ln}行: {t}")
    print()
    if res["verdict"] == "PASS":
        print(f"{BOLD}{GREEN}【门禁通过】结构性检查通过，可进入数据抽检(extract/verdict)。{RESET}")
    else:
        print(f"{BOLD}{RED}【门禁打回】需修正后重审：{RESET}")
        for r in res["reasons"]:
            print(f"  ❌ {r}")
    print("=" * 70)
    print(f"  {YELLOW}注：门禁是启发式而非语义理解，通过不代表内容正确——仍须数据抽检 + 人工复核。{RESET}")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Report Audit Tool — 研究报告数据抽检工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
工作流程：

  Step 1 — 提取数据点并随机抽样 15%，输出抽检清单：
    python3 tools/report_audit.py extract --report reports/腾讯/腾讯-research-20260408.md

  Step 2 — Claude 对清单中每个数据点，从可靠信源取数，
            填入 fetched_value / fetched_source / fetched_value2 / fetched_source2

  Step 3 — 输入核验结果，输出准出/打回判决：
    python3 tools/report_audit.py verdict --results '[
      {"id":1,"label":"营业收入","reported_value":7518,"unit":"亿","fetched_value":7518,"fetched_source":"macrotrends","fetched_value2":7500,"fetched_source2":"stockanalysis"},
      ...
    ]'

  一步预览（只打印抽检清单，不核验）：
    python3 tools/report_audit.py extract --report reports/xxx.md --dry-run

  指定抽样比例（默认0.15）：
    python3 tools/report_audit.py extract --report reports/xxx.md --ratio 0.20

  固定随机种子（复现同一批样本）：
    python3 tools/report_audit.py extract --report reports/xxx.md --seed 42
        """)

    sub = parser.add_subparsers(dest='command')

    # extract
    ext = sub.add_parser('extract', help='从报告提取数据点并随机抽样')
    ext.add_argument('--report', required=True, help='报告文件路径（Markdown）')
    ext.add_argument('--ratio', type=float, default=0.15, help='抽样比例，默认 0.15')
    ext.add_argument('--seed', type=int, default=None, help='随机种子（可选，用于复现）')
    ext.add_argument('--dry-run', action='store_true', help='只打印，不输出 JSON')

    # verdict
    vrd = sub.add_parser('verdict', help='根据核验结果输出准出/打回判决')
    vrd.add_argument('--results', required=True, help='JSON 数组，含 fetched_value 等字段')
    vrd.add_argument('--report', default='', help='报告名称（可选，用于显示）')
    vrd.add_argument('--output-json', action='store_true', help='将判决结果以 JSON 输出到 stdout')

    # gate — 发布前硬门禁（来源覆盖/主观词/估计标注/交叉验证）
    gt = sub.add_parser('gate', help='AI 硬门禁：发布前结构性防线（先于数据抽检）')
    gt.add_argument('--report', required=True, help='报告文件路径（Markdown）')
    gt.add_argument('--output-json', action='store_true')

    args = parser.parse_args()

    if args.command == 'extract':
        if not os.path.exists(args.report):
            print(f'❌ 文件不存在: {args.report}', file=sys.stderr)
            sys.exit(1)

        with open(args.report, 'r', encoding='utf-8') as f:
            text = f.read()

        all_points = extract_data_points(text)
        sampled = sample_points(all_points, ratio=args.ratio, seed=args.seed)

        print('=' * 70)
        print(f'报告数据抽检清单')
        print(f'文件：{args.report}')
        print(f'总提取数据点：{len(all_points)}  |  抽样比例：{args.ratio:.0%}  |  抽检数量：{len(sampled)}')
        if args.seed is not None:
            print(f'随机种子：{args.seed}（可用于复现同一批样本）')
        print('=' * 70)
        print()
        print(f'{"ID":>3}  {"行号":>5}  {"数据标签":<35}  {"报告值":>12}  {"单位"}')
        print(f'{"─"*3}  {"─"*5}  {"─"*35}  {"─"*12}  {"─"*6}')
        for p in sampled:
            print(f'{p["id"]:>3}  {p["line_number"]:>5}  {p["label"][:35]:<35}  {p["reported_value"]:>12.2f}  {p["unit"]}')
        print()
        print('↑ 请对上述每个数据点，从以下信源取数，填入 fetched_value：')
        print('  美股：macrotrends.net（主）+ stockanalysis.com（副）')
        print('  港股：aastocks.com（主）+ macrotrends ADR（副）')
        print('  A股： eastmoney.com（主）+ cninfo.com.cn（副）')
        print()

        if not args.dry_run:
            # 输出可填写的 JSON 模板
            template = []
            for p in sampled:
                template.append({
                    'id': p['id'],
                    'label': p['label'],
                    'reported_value': p['reported_value'],
                    'unit': p['unit'],
                    'line_number': p['line_number'],
                    'raw_text': p['raw_text'],
                    'fetched_value': None,       # ← 填入主来源核验值
                    'fetched_source': '',        # ← 填入主来源名称
                    'fetched_value2': None,      # ← 填入副来源核验值（可选）
                    'fetched_source2': '',       # ← 填入副来源名称（可选）
                })
            print('抽检清单 JSON（填入 fetched_value 后，传给 verdict 命令）：')
            print()
            print(json.dumps(template, ensure_ascii=False, indent=2))

    elif args.command == 'verdict':
        try:
            results = json.loads(args.results)
        except json.JSONDecodeError as e:
            print(f'❌ JSON 解析失败: {e}', file=sys.stderr)
            sys.exit(1)

        report_name = args.report or ''
        outcome = render_verdict(results, report_name=report_name)

        if args.output_json:
            print(json.dumps(outcome, ensure_ascii=False, indent=2))

        # 非零退出码表示打回，方便 CI/脚本判断
        sys.exit(0 if outcome['verdict'] == 'PASS' else 1)

    elif args.command == 'gate':
        if not os.path.exists(args.report):
            print(f'❌ 文件不存在: {args.report}', file=sys.stderr)
            sys.exit(1)
        with open(args.report, 'r', encoding='utf-8') as f:
            text = f.read()
        res = gate_report(text)
        if args.output_json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            render_gate(res, report_name=args.report)
        sys.exit(0 if res['verdict'] == 'PASS' else 1)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
