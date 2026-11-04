#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清理打包残留：__pycache__ / *.pyc / .pytest_cache / .mypy_cache / out。

★ 清完必须自检，有残留就返回 1 —— 清理工具不能给自己发合格证。
（上个项目踩过：clean 报「清理 20 项」，紧接着 check_package 仍报 .pytest_cache 残留，
  根因是只删了目录下的文件、没删子目录，且三处 except: pass 全在吞错误。）"""
import os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAD_DIRS = ("__pycache__", ".pytest_cache", ".mypy_cache")
removed, fail = [], []


def _rm_file(p):
    try:
        os.remove(p); removed.append(p)
    except OSError as e:
        fail.append("%s (%s)" % (p, e))


def _rm_tree(top):
    for dp, dns, fns in os.walk(top, topdown=False):
        for f in fns:
            _rm_file(os.path.join(dp, f))
        for d in dns:
            full = os.path.join(dp, d)
            try:
                os.rmdir(full); removed.append(full)
            except OSError as e:
                fail.append("%s (%s)" % (full, e))
    try:
        os.rmdir(top); removed.append(top)
    except OSError as e:
        fail.append("%s (%s)" % (top, e))


def scan():
    hits = []
    for dp, dns, fns in os.walk(HERE):
        for d in dns:
            if d in BAD_DIRS:
                hits.append(os.path.relpath(os.path.join(dp, d), HERE))
        for f in fns:
            if f.endswith(".pyc"):
                hits.append(os.path.relpath(os.path.join(dp, f), HERE))
    return hits


def main():
    for dp, dns, fns in os.walk(HERE, topdown=False):
        for d in list(dns):
            if d in BAD_DIRS:
                _rm_tree(os.path.join(dp, d))
    for dp, dns, fns in os.walk(HERE, topdown=False):
        for f in fns:
            if f.endswith(".pyc"):
                _rm_file(os.path.join(dp, f))
    left = scan()
    print("清理 %d 项；残留 %d 项" % (len(removed), len(left)))
    for h in left[:10]:
        print("  残留: %s" % h)
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main())
