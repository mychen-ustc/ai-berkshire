#!/usr/bin/env python3
"""API 密钥读取（零依赖）。优先环境变量，其次本地 gitignore 文件 config/secrets.local.json。

密钥永不写入会提交的源码。用法：
  export FINNHUB_API_KEY=xxx          # 方式一：环境变量
  # 或写入 config/secrets.local.json（已 gitignore）：{"FINNHUB_API_KEY": "xxx"}
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SECRETS = os.path.join(ROOT, "config", "secrets.local.json")


def get_key(name, required=False):
    v = os.environ.get(name)
    if not v and os.path.exists(_SECRETS):
        try:
            with open(_SECRETS, encoding="utf-8") as f:
                v = json.load(f).get(name)
        except (ValueError, OSError):
            v = None
    if required and not v:
        raise SystemExit(
            f"缺少密钥 {name}：请 `export {name}=...` 或写入 config/secrets.local.json（已 gitignore）。")
    return v
