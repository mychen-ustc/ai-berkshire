#!/usr/bin/env python3
"""统一取数韧性层（零外部依赖，仅 stdlib）。

在 datalayer._curl（已含重试+退避）之上，再提供：
  · retry_call：对任意可调用做重试+指数退避（不限于 HTTP）。
  · fallback：多源降级——按序尝试 (名称, 取数函数)，返回首个成功源，全失败才报错。
  · get：带 TTL 磁盘缓存的 HTTP 取数（缓存目录 data/cache/http/ 已 gitignore）。
    ⚠️ 缓存默认关闭(ttl=0)：行情/资金流等时效数据不宜缓存；仅对稳定数据(如公司主数据、宏观历史)显式开 TTL。

设计原则：韧性≠掩盖失败。多源降级会记录每个源的失败原因；缓存有 TTL 且默认关闭，
不静默返回陈旧数据（呼应"缺失/过期/冲突不得被静默使用"）。

用法（库）：
  from fetcher import retry_call, fallback, get
  env = fallback([("yahoo", lambda: parse_yahoo(...)), ("stooq", lambda: parse_stooq(...))])
  txt = get(url, ttl=86400)     # 稳定数据缓存 1 天
"""
import hashlib
import os
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, _HERE)
import datalayer as dl  # noqa: E402

CACHE_DIR = os.path.join(os.path.dirname(_HERE), "data", "cache", "http")


def retry_call(fn, retries=2, backoff=0.4, exc=(Exception,)):
    """对 fn 做 retries+1 次尝试，指数退避。全败抛最后一次异常。backoff=0 便于测试。"""
    last = None
    for i in range(retries + 1):
        try:
            return fn()
        except exc as e:  # noqa: BLE001
            last = e
            if i < retries and backoff:
                time.sleep(backoff * (i + 1))
    raise last if last else RuntimeError("retry_call: 无结果")


def fallback(sources):
    """sources: [(name, callable)]。返回 {"source", "value"} 首个成功(非 None)源；全失败抛错并附各源原因。"""
    errs = []
    for name, fn in sources:
        try:
            v = fn()
            if v is not None:
                return {"source": name, "value": v}
            errs.append(f"{name}: 返回空")
        except Exception as e:  # noqa: BLE001
            errs.append(f"{name}: {e}")
    raise RuntimeError("所有源失败降级：" + " | ".join(errs))


def _cache_path(url):
    return os.path.join(CACHE_DIR, hashlib.sha1(url.encode("utf-8")).hexdigest() + ".txt")


def cache_age(url):
    """缓存年龄(秒)，无缓存返回 None。"""
    p = _cache_path(url)
    return (time.time() - os.path.getmtime(p)) if os.path.exists(p) else None


def get(url, ttl=0, headers=None, ua=None, retries=2):
    """HTTP 取数：ttl>0 且缓存未过期则读缓存，否则联网(含重试)并按 ttl 写缓存。"""
    if ttl > 0:
        age = cache_age(url)
        if age is not None and age < ttl:
            with open(_cache_path(url), encoding="utf-8") as f:
                return f.read()
    data = dl._curl(url, headers=headers, ua=ua, retries=retries)
    if ttl > 0:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_cache_path(url), "w", encoding="utf-8") as f:
            f.write(data)
    return data
