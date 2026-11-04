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


BIN_EXT = (".png", ".jpg", ".zip", ".pyc", ".gz")


def normalize_eol():
    """把文本文件统一成 LF。

    ★ 为什么会需要它：在 Windows 上用 open(...,"w") 改文件，Python 会把 \n 写成 CRLF。
      之后 make_manifest 哈希的是 CRLF 版本，而 git（.gitattributes eol=lf）存的是 LF 版本 →
      买家 clone 下来哈希对不上，verify 报「哈希不符」，看起来像包被改过。
      实测踩过：Ubuntu 上 verify 报 tests/test_contract.py 哈希不符，Windows 全绿。
    """
    fixed = []
    for dp, dns, fns in os.walk(HERE):
        dns[:] = [d for d in dns if d not in (".git", ".venv", "node_modules")]
        for f in fns:
            if f == "MANIFEST.json" or f.endswith(BIN_EXT):
                continue
            fp = os.path.join(dp, f)
            raw = open(fp, "rb").read()
            if b"\r\n" in raw:
                open(fp, "wb").write(raw.replace(b"\r\n", b"\n"))
                fixed.append(os.path.relpath(fp, HERE))
    return fixed


def main():
    n_eol = normalize_eol()
    if n_eol:
        print("换行归一化 %d 个文件: %s" % (len(n_eol), ", ".join(n_eol[:4])))
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
