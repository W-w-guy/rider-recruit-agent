#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交付自检：客户拿到包后一条命令核对。只说可判定的事实。

  1) 单元测试全过（且「声明用例数 == 实际运行数」，防 pytest 风格用例被静默跳过）
  2) demo 跑两遍，产物逐字节相同
  3) 验收第 2 条：300 条评测 accuracy / violations
  4) 留出集命中率（泛化，不当成 100%）
  5) MANIFEST 逐个 sha256 核对
  6) 产物里没有本机绝对路径
退出码：0 全过；1 有失败。
"""
import hashlib, json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def chk(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, "%s: %s" % (type(e).__name__, e)
    print("[%s] %-32s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILS.append(name)


def run(cmd, cwd=HERE):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def _declared_tests():
    n = 0
    d = os.path.join(HERE, "tests")
    for f in os.listdir(d):
        if f.endswith(".py"):
            with open(os.path.join(d, f), encoding="utf-8", errors="replace") as fh:
                n += len(re.findall(r"^\s*def (test_\w+)", fh.read(), re.M))
    return n


def t_tests():
    r = run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"])
    out = (r.stderr or "") + (r.stdout or "")
    m = re.search(r"Ran (\d+) tests", out)
    ran = int(m.group(1)) if m else -1
    dec = _declared_tests()
    if ran != dec:
        return False, "收集不完整: 声明 %d 条, 实际运行 %d 条" % (dec, ran)
    return r.returncode == 0, "Ran %d tests" % ran


def t_demo():
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        for out in (a, b):
            r = run([sys.executable, "-B", "run.py", "demo", out])
            if r.returncode != 0:
                return False, "demo rc=%d %s" % (r.returncode, (r.stderr or "")[-120:])
        fa = os.path.join(a, "demo_report.json")
        fb = os.path.join(b, "demo_report.json")
        ha = hashlib.sha256(open(fa, "rb").read()).hexdigest()
        hb = hashlib.sha256(open(fb, "rb").read()).hexdigest()
        return ha == hb, "两遍 sha256 %s" % ("一致" if ha == hb else "不同")


def t_eval():
    r = run([sys.executable, "-B", "tools/eval.py", "300"])
    m = re.search(r"\{.*\}", r.stdout or "", re.S)
    if not m:
        return False, "eval 无输出"
    d = json.loads(m.group(0))
    ok = (d["extract_acc"] >= 0.95 and d["policy_acc"] >= 0.90
          and d["violations"] == 0)
    return ok, "抽取 %.1f%% 政策 %.1f%% 违规 %d 未成年 %s" % (
        d["extract_acc"] * 100, d["policy_acc"] * 100, d["violations"], d["minor"])


def t_holdout():
    r = run([sys.executable, "-B", "tools/holdout.py"])
    m = re.search(r"留出集命中率: (\d+)/(\d+) = ([\d.]+)%", r.stdout or "")
    if not m:
        return False, "holdout 无输出"
    acc = float(m.group(3))
    return acc >= 85, "%s%%（%s/%s，仅作泛化参考）" % (m.group(3), m.group(1), m.group(2))


def t_manifest():
    p = os.path.join(HERE, "MANIFEST.json")
    if not os.path.isfile(p):
        return False, "MANIFEST.json 缺失"
    man = json.load(open(p, encoding="utf-8"))
    bad = []
    for item in man["files"]:
        fp = os.path.join(HERE, item["path"])
        if not os.path.isfile(fp):
            bad.append("缺失:" + item["path"]); continue
        h = hashlib.sha256(open(fp, "rb").read()).hexdigest()
        if h != item["sha256"]:
            bad.append("哈希不符:" + item["path"])
    return not bad, ("%d 文件逐个核对通过" % len(man["files"])) if not bad else "; ".join(bad[:4])


def t_no_abs_path():
    hits = []
    with tempfile.TemporaryDirectory() as out:
        run([sys.executable, "-B", "run.py", "demo", out])
        for dp, _dn, fns in os.walk(out):
            for f in fns:
                fp = os.path.join(dp, f)
                with open(fp, encoding="utf-8", errors="replace") as fh:
                    if HERE.replace(os.sep, "/") in fh.read() or HERE in fh.read():
                        hits.append(f)
    return not hits, "无本机绝对路径" if not hits else "泄漏: " + ",".join(hits)


def t_no_crlf():
    """文本文件不得含 CRLF：否则 git 归一化后 MANIFEST 哈希必然不符。"""
    hits = []
    for dp, dns, fns in os.walk(HERE):
        # ★ 必须剪掉 .git/.venv/node_modules：vendor 目录里的第三方文件换行不归我们管，
        #   不剪会把「第三方包有 CRLF」报成我们的交付缺陷（实测在 .venv 里误报 3 条）。
        dns[:] = [d for d in dns if d not in (".git", ".venv", "node_modules", "__pycache__")]
        if ".git" in dp:
            continue
        for f in fns:
            if f == "MANIFEST.json" or f.endswith((".png", ".jpg", ".zip", ".pyc", ".gz")):
                continue
            fp = os.path.join(dp, f)
            if b"\r\n" in open(fp, "rb").read():
                hits.append(os.path.relpath(fp, HERE))
    return not hits, "全为 LF" if not hits else "含 CRLF: " + ",".join(hits[:3])


def main():
    print("=" * 70)
    chk("单元测试全过", t_tests)
    chk("demo 两遍字节一致", t_demo)
    chk("评测 300 条达标", t_eval)
    chk("留出集泛化", t_holdout)
    chk("换行统一为 LF", t_no_crlf)
    chk("MANIFEST 哈希核对", t_manifest)
    chk("产物无本机绝对路径", t_no_abs_path)
    print("=" * 70)
    print("%d passed / %d failed" % (7 - len(FAILS), len(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
