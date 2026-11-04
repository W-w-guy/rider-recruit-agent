#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 MANIFEST.json（逐文件 sha256）。打包前必跑。"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", "out", ".venv", "node_modules"}
SKIP_FILES = {"MANIFEST.json"}


def main():
    rows = []
    total = 0
    for dp, dns, fns in os.walk(HERE):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for f in sorted(fns):
            if f in SKIP_FILES or f.endswith(".pyc"):
                continue
            fp = os.path.join(dp, f)
            rel = os.path.relpath(fp, HERE).replace(os.sep, "/")
            data = open(fp, "rb").read()
            total += len(data)
            rows.append({"path": rel, "bytes": len(data),
                         "sha256": hashlib.sha256(data).hexdigest()})
    rows.sort(key=lambda x: x["path"])
    out = {"files": rows, "count": len(rows), "total_bytes": total}
    with open(os.path.join(HERE, "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print("MANIFEST.json: %d 文件 / %d 字节" % (len(rows), total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
