# -*- coding: utf-8 -*-
"""会话引擎：状态机 + 政策 RAG + 护栏 + 降级 + 工具调用（mock 任务3/任务5）。"""
import time

from . import guard, kb, slots
from .mocks import station, vault
from .outbox import Outbox


class Engine(object):
    def __init__(self, policy_dir, model=None, secret="dev-secret"):
        self.chunks = kb.load(policy_dir)
        self.model = model
        self.outbox = Outbox(secret)
        self.stats = {"policy_q": 0, "policy_ok": 0, "handoff": 0,
                      "violations": 0, "degraded": 0, "sessions": 0,
                      "candidate_created": 0}

    # ---------- 会话 ----------
    def new_session(self, today=None):
        self.stats["sessions"] += 1
        s = slots.Session(today)
        s.consent = {"consent_version": "v1", "consent_at": slots_now()}
        return s

    def on_complete(self, sess):
        """7 项收齐 → 建 candidate（脱敏后入 token，明文只进保险箱）。"""
        data = dict(sess.data)
        raw_name, raw_area = data.get("name"), data.get("area_text")
        out = {k: v for k, v in data.items() if k not in ("name", "phone")}
        if raw_name:
            out["name_token"] = vault.tokenize("name", raw_name)
        if raw_area:
            out["area_text"] = raw_area
        out["status"] = "complete"
        self.stats["candidate_created"] += 1
        self.outbox.emit("candidate.completed",
                         {"candidate": {k: out[k] for k in ("birth_ym", "area_text",
                                                            "job_type", "status") if k in out}})
        return out

    # ---------- 政策问答 ----------
    def ask_policy(self, question):
        self.stats["policy_q"] += 1
        t0 = time.time()
        masked, kinds = slots.mask(question)
        try:
            hits = kb.search(self.chunks, masked)
        except Exception:
            hits = []
        degraded = False
        reply = None
        try:
            if self.model is not None:
                reply = self.model.chat(masked, hits)
        except TimeoutError:
            degraded = True
            self.stats["degraded"] += 1
            reply = None
        if not reply:
            # 检索不到 / 模型超时 → 转人工，绝不编造；报名链路不中断
            self.stats["handoff"] += 1
            self.outbox.emit("handoff.requested", {"reason": "policy_miss" if not hits else "model_timeout"})
            return {"reply": "这个问题我不确定，已转人工同事回复您，报名不受影响。",
                    "actions": ["handoff"], "citations": [], "degraded": degraded,
                    "ms": round((time.time() - t0) * 1000, 2), "masked": kinds}
        v = guard.check(reply, cited=True)
        if v:
            self.stats["violations"] += 1
            self.stats["handoff"] += 1
            return {"reply": "已转人工。", "actions": ["handoff"], "citations": [],
                    "degraded": degraded, "violations": v,
                    "ms": round((time.time() - t0) * 1000, 2), "masked": kinds}
        self.stats["policy_ok"] += 1
        return {"reply": reply, "actions": [],
                "citations": [{"doc": hits[0][1]["doc"], "version": hits[0][1]["version"],
                               "section": hits[0][1]["section"]}],
                "degraded": degraded, "ms": round((time.time() - t0) * 1000, 2),
                "masked": kinds}

    # ---------- 工具 ----------
    def stations(self, lat=30.2870, lng=120.0760):
        return station.query(lat, lng)


def slots_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
