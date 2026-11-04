# -*- coding: utf-8 -*-
"""FastAPI 应用：契约 v1 前缀 /api/v1，错误体 {code,message}。

会话接口（任务1 提供）：
  POST /api/v1/agent/sessions
  POST /api/v1/agent/sessions/{id}/messages
配套：政策问答、站点、候选人读回、评测与每日抽检、OpenAPI。
"""
import time
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from . import __version__, contract, errors, slots
from .config import CFG
from .engine import Engine
from .errors import ApiError
from .model import HttpModel, MockModel
from .store import build

app = FastAPI(title="rider-recruit-agent (task 1/5)", version=__version__,
              description="骑手招聘 Agent 化信息收集平台 · 任务1：Agent 对话引擎与政策知识库")

errors.install(app)

_model = (HttpModel(CFG.model_base_url, CFG.model_name) if CFG.model_base_url
          else MockModel())
_engine = Engine(CFG.policy_dir, model=_model, secret=CFG.webhook_secret)
_store = None


def store():
    global _store
    if _store is None:
        _store = build(CFG.database_url)
    return _store


@app.on_event("startup")
def _start():
    store()


@app.get("/health")
def health():
    s = store()
    return {"status": "ok", "version": __version__, "store": s.kind,
            "model": getattr(_model, "name", "?"),
            "policy_chunks": len(_engine.chunks)}


@app.post("/api/v1/agent/sessions", response_model=contract.SessionOut)
def new_session():
    sid = store().create_session()
    return {"session_id": sid}


def _load(sid):
    s = store().get_session(sid)
    if not s:
        raise ApiError("session_not_found", "会话不存在或已过期", 404)
    return s


@app.post("/api/v1/agent/sessions/{sid}/messages", response_model=contract.MessageOut)
def post_message(sid: str, body: contract.MessageIn,
                 x_request_id: Optional[str] = Header(None, alias="X-Request-Id")):
    rec = _load(sid)
    sess = slots.Session.from_state(rec["state"])
    t0 = time.time()
    out = sess.say(body.text)
    store().save_session(sid, sess.to_state())

    # 收齐 → 建候选人并给预约动作。
    # ★ 用 to_state()["created"] 判重，不用 getattr(sess,"_created") ——
    #   后者每次请求都是新对象（from_state 后才设），会导致每次收齐都重复建人。
    already = bool(sess.to_state().get("created"))
    if not sess.missing() and not already:
        cand = _engine.on_complete(sess)
        sess._created = True
        store().save_session(sid, sess.to_state())
        acts = [a for a in (out.get("actions") or []) if a != "show_stations"]
        out["actions"] = acts + ["show_stations"]
        out["stations"] = _engine.stations()
        out["candidate"] = {k: cand.get(k) for k in
                            ("birth_ym", "area_text", "job_type", "has_ebike",
                             "start_text", "experience_text", "status")}
    elif already and not sess.missing():
        # 已建过人：再来消息只回进度，不重复建
        out["actions"] = list(out.get("actions") or [])

    tok = {"in": getattr(_model, "tokens_in", 0), "out": getattr(_model, "tokens_out", 0)}
    out.setdefault("citations", [])
    out["degraded"] = bool(out.get("degraded"))
    out["tokens"] = tok
    out["ms"] = round((time.time() - t0) * 1000, 2)
    return out


@app.post("/api/v1/agent/policy/ask")
def policy_ask(body: dict):
    q = (body or {}).get("question")
    if not q:
        raise ApiError("bad_request", "question 必填", 422)
    return _engine.ask_policy(q)


@app.get("/api/v1/stations")
def stations(lat: float = 30.2870, lng: float = 120.0760, limit: int = 3):
    return {"items": _engine.stations(lat, lng)[:max(1, min(limit, 10))]}


@app.get("/api/v1/candidates")
def list_candidates(limit: int = 50, offset: int = 0):
    rows, total = store().list_candidates(max(1, min(limit, 200)), max(0, offset))
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@app.get("/api/v1/candidates/{cid}")
def get_candidate(cid: str):
    c = store().get_candidate(cid)
    if not c:
        raise ApiError("candidate_not_found", "候选人不存在", 404)
    return c


@app.get("/api/v1/outbox")
def outbox(limit: int = 100):
    return {"items": _engine.outbox.pending(limit)}


@app.post("/api/v1/outbox/{rid}/ack")
def outbox_ack(rid: int):
    return {"ok": _engine.outbox.ack(rid)}


@app.get("/api/v1/quality/daily")
def quality_daily():
    """每日抽检报告接口（契约要求提供）。"""
    return {"date": time.strftime("%Y-%m-%d"), "stats": dict(_engine.stats),
            "policy_chunks": len(_engine.chunks),
            "violations": _engine.stats["violations"]}


@app.get("/api/v1/quality/eval")
def quality_eval():
    """轻量评测摘要（全量评测见 tools/eval.py，一条命令跑 300 条）。"""
    return {"note": "run `python tools/eval.py` for full 300-case benchmark",
            "stats": dict(_engine.stats)}


@app.exception_handler(HTTPException)
async def _http_err(req, exc):
    return JSONResponse({"code": "http_%d" % exc.status_code, "message": str(exc.detail)},
                        status_code=exc.status_code)
