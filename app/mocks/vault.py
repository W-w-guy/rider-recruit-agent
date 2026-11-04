# -*- coding: utf-8 -*-
"""任务 5（保险箱）的 mock：与契约一致的 tokenize / detokenize。
真实实现不在本任务范围；这里保证「模型只看到占位符，回填只在服务端」可跑通。"""
import hashlib, threading

_LOCK = threading.Lock()
_STORE = {}
_SEQ = {}


def _next(kind):
    with _LOCK:
        _SEQ[kind] = _SEQ.get(kind, 0) + 1
        return _SEQ[kind]


def tokenize(kind, value):
    """确定性令牌：同一 (kind,value) 永远同一 token，等价于 HMAC(tenant, 规范化值)。"""
    key = (kind, str(value))
    with _LOCK:
        if key in _STORE:
            return _STORE[key]
    tok = "〔%s_%d〕" % ({"phone": "手机号", "idcard": "身份证号", "name": "姓名"}.get(kind, kind),
                        _next(kind))
    with _LOCK:
        _STORE[key] = tok
        _STORE[tok] = str(value)
    return tok


def detokenize(token, reason=""):
    with _LOCK:
        v = _STORE.get(token)
    if v is None:
        raise KeyError(token)
    return v


def mask(kind, value):
    v = str(value)
    if kind == "phone" and len(v) == 11:
        return v[:3] + "****" + v[-4:]
    if kind == "name":
        return v[0] + "**"
    return v[:2] + "***"


def reset():
    with _LOCK:
        _STORE.clear()
        _SEQ.clear()
