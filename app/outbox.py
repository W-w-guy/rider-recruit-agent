# -*- coding: utf-8 -*-
"""outbox + Webhook，HMAC-SHA256 签名（契约要求）。
事件名与 payload 形状固定，测试按契约校验签名，而不是「大概发了个东西」。"""
import hashlib, hmac, json, threading
from datetime import datetime, timezone

EVENTS = ("candidate.created", "candidate.updated", "candidate.completed",
          "booking.created", "booking.cancelled", "handoff.requested")


def sign(secret, body):
    if isinstance(body, str):
        body = body.encode("utf-8")
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify(secret, body, signature):
    return hmac.compare_digest(sign(secret, body), str(signature))


class Outbox(object):
    def __init__(self, secret):
        self.secret = secret
        self._rows = []
        self._lock = threading.Lock()

    def emit(self, event, payload):
        if event not in EVENTS:
            raise ValueError("unknown event: %s" % event)
        body = json.dumps({"event": event, "data": payload,
                           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                          ensure_ascii=False, sort_keys=True)
        row = {"id": len(self._rows) + 1, "event": event, "body": body,
               "signature": sign(self.secret, body)}
        with self._lock:
            self._rows.append(row)
        return row

    def pending(self, limit=100):
        return [r for r in self._rows if not r.get("delivered_at")][:limit]

    def ack(self, rid):
        for r in self._rows:
            if r["id"] == rid:
                r["delivered_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                return True
        return False

    def all(self):
        return list(self._rows)
