#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包前检查：不该带的东西一个都不能带。"""
import json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAD_NAME_EXT = (".pyc", ".pyo", ".db", ".sqlite", ".log")
# .git 不算失败项：在仓库工作目录里跑检查时它本来就在，
# 打包用的是 git archive，天然不含 .git。检查器不该为「工作目录形态」报红。
BAD_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", "out", ".venv"}
INFO_DIRS = {".git"}
FAILS = []


def fail(msg):
    FAILS.append(msg)
    print("[FAIL] " + msg)


def main():
    print("=" * 60)
    n = 0
    for dp, dns, fns in os.walk(HERE):
        rel = os.path.relpath(dp, HERE)
        for d in list(dns):
            if d in INFO_DIRS:
                dns.remove(d)
                continue
            if d in BAD_DIRS:
                fail("不该有的目录: %s" % (os.path.join(rel, d) if rel != "." else d))
        for f in fns:
            n += 1
            if f.endswith(BAD_NAME_EXT):
                fail("不该有的文件: %s" % os.path.join(rel, f))
            if f.startswith(".env"):
                fail("疑似密钥文件: %s" % os.path.join(rel, f))
    for req in ["README.md", "SETUP.md", "VERIFICATION.md", "docker-compose.yml",
                "Dockerfile", "run.py", "MANIFEST.json", "requirements.txt",
                "data/eval_300.jsonl", "data/eval_300_adv.jsonl"]:
        if not os.path.isfile(os.path.join(HERE, req)):
            fail("缺少必需文件: %s" % req)
    adv = 0
    p = os.path.join(HERE, "data", "eval_300_adv.jsonl")
    if os.path.isfile(p):
        adv = sum(1 for _ in open(p, encoding="utf-8"))
    if adv < 30:
        fail("反例不足 30 条（实际 %d）" % adv)
    print("=" * 60)
    print("打包检查：%d 个文件，%d 项失败" % (n, len(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
