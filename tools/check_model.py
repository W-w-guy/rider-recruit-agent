#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3 秒验证模型接入：连通性 + 一次真实抽取往返 + token 消耗。

用法:
  export MODEL_BASE_URL=https://api.deepseek.com/v1
  export MODEL_NAME=deepseek-chat
  export MODEL_API_KEY=sk-xxx
  python tools/check_model.py

不打印、不落盘 key；只显示长度与前 4 位。
退出码 0=可用；1=不可用（会打印原因）。
"""
import os, sys, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from app.extract_llm import LLMExtractor          # noqa: E402
from app.pipeline import validate                  # noqa: E402


def main():
    base = os.environ.get("MODEL_BASE_URL", "")
    model = os.environ.get("MODEL_NAME", "")
    key = os.environ.get("MODEL_API_KEY", "")
    print("MODEL_BASE_URL =", base or "(未设置)")
    print("MODEL_NAME     =", model or "(未设置)")
    print("MODEL_API_KEY  =", (key[:4] + "…" + "(%d 字符)" % len(key)) if key else "(未设置)")
    if not base or not model:
        print("\n[FAIL] 至少需要 MODEL_BASE_URL 与 MODEL_NAME")
        return 1

    ex = LLMExtractor(base, model, key)
    samples = ["免贵姓李", "长期工", "我有美团的车", "我今年25"]
    print()
    t0 = time.time()
    ok = 0
    for s in samples:
        r = ex.extract(s)
        if r is None:
            print("  %-10s -> 抽取失败 (%s)" % (s, ex.last_error))
            continue
        v = validate(r)
        ok += 1
        print("  %-10s -> %s" % (s, {k: v[k] for k in v} or "{} (全部 null)"))
    print("\n耗时 %.1fs，tokens %d，成功 %d/%d" % (time.time() - t0, ex.tokens, ok, len(samples)))
    if ok == 0:
        print("[FAIL] 全部失败：检查 base_url 是否 OpenAI 兼容（/chat/completions）、"
              "model 名是否正确、key 是否有额度")
        return 1
    if ok < len(samples):
        print("[WARN] 部分失败，可能是 max_tokens 太小（推理模型会把额度全用在 reasoning 上）")
    print("[PASS] 模型可用。接着跑：python tools/eval.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
