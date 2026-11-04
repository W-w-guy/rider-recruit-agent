# -*- coding: utf-8 -*-
"""模型适配：主备模型 + 超时降级；记录 tokens 与耗时。

★ 关于「mock」：验收要求「用仓库内写明的模型或 mock 复跑」。
本文件的 MockModel 是确定性规则改写，不含任何随机性 —— 这样评测数字可复现，
换真实模型（OpenAI 兼容）只需设 MODEL_BASE_URL / MODEL_NAME / MODEL_API_KEY。

★ 2026-11-06 更正：本文件早前写过「评测脚本不用改」，那句话是错的，属于文档说谎。
  事实是 tools/eval.py 当时硬编码 MockModel()，配了 key 评测仍走 mock，
  会出现「API 用真模型、评测报 mock 分」两套数字对不上。
  现在 tools/eval_fixed.py 与 tools/diagnose.py 会读环境变量并**在报告里写明用的是哪个模型**。
"""
import json, time, urllib.request


class MockModel(object):
    name = "mock-rule-v1"

    def __init__(self):
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.timeouts = 0

    def chat(self, prompt, chunks, timeout_ms=3000):
        self.calls += 1
        self.tokens_in += len(str(prompt))
        if not chunks:
            return None
        c = chunks[0][1]
        first = c["text"].split("\n")[0].strip()
        reply = "%s（出处：%s v%s / %s）" % (first, c["doc"], c["version"], c["section"])
        self.tokens_out += len(reply)
        return reply


class HttpModel(object):
    """OpenAI 兼容 /chat/completions。timeout 严格按配置，超时抛 TimeoutError。"""
    name = "http"

    def __init__(self, base_url, model, api_key=None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or ""
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.timeouts = 0

    def chat(self, prompt, chunks, timeout_ms=3000):
        self.calls += 1
        if not chunks:
            return None
        c = chunks[0][1]
        sys_p = ("你是骑手招聘助手。只依据给定政策片段回答，必须附出处；"
                 "不得承诺收入、不得歧视、不得索要身份证/银行卡。")
        user_p = "政策片段：%s\n\n问题：%s" % (c["text"], prompt)
        body = json.dumps({"model": self.model, "temperature": 0,
                           "messages": [{"role": "system", "content": sys_p},
                                        {"role": "user", "content": user_p}]}).encode()
        req = urllib.request.Request(self.base_url + "/chat/completions", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", "Bearer " + self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=timeout_ms / 1000.0) as r:
                d = json.load(r)
        except Exception as e:
            if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                self.timeouts += 1
                raise TimeoutError("model timeout after %sms" % timeout_ms)
            raise
        u = d.get("usage") or {}
        self.tokens_in += int(u.get("prompt_tokens", 0))
        self.tokens_out += int(u.get("completion_tokens", 0))
        return d["choices"][0]["message"]["content"]
