# -*- coding: utf-8 -*-
"""存储：内存后端（默认，评测/CI 用）+ PostgreSQL 后端（compose 用）。
两者实现同一套方法，测试在两边都跑。"""
import json, os, threading, uuid
from datetime import datetime, timedelta, timezone


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MemoryStore(object):
    kind = "memory"

    def __init__(self):
        self._sess = {}
        self._cand = {}
        self._seq = 0
        self._lock = threading.RLock()

    def create_session(self, channel="agent_chat"):
        with self._lock:
            sid = "s_" + uuid.uuid4().hex[:12]
            self._sess[sid] = {"id": sid, "state": {}, "created_at": now()}
            return sid

    def get_session(self, sid):
        return self._sess.get(sid)

    def save_session(self, sid, state):
        with self._lock:
            s = self._sess.get(sid)
            if s:
                s["state"] = state
                s["updated_at"] = now()

    def create_candidate(self, fields):
        with self._lock:
            self._seq += 1
            cid = "c_%06d" % self._seq
            c = dict(fields)
            c.update(id=cid, status="complete", created_at=now(), updated_at=now(),
                     retention_until=(datetime.now(timezone.utc)
                                      + timedelta(days=90)).isoformat(timespec="seconds"))
            self._cand[cid] = c
            return c

    def get_candidate(self, cid):
        return self._cand.get(cid)

    def list_candidates(self, limit=50, offset=0):
        rows = sorted(self._cand.values(), key=lambda x: x["created_at"], reverse=True)
        return rows[offset:offset + limit], len(rows)

    def close(self):
        pass


class PgStore(object):
    kind = "postgres"

    def __init__(self, dsn):
        import pg8000.dbapi as pg
        self._pg = pg
        self._dsn = dsn
        self._lock = threading.RLock()
        self._init()

    def _conn(self):
        from urllib.parse import urlparse
        u = urlparse(self._dsn)
        return self._pg.connect(user=u.username, password=u.password or "",
                                host=u.hostname, port=u.port or 5432,
                                database=(u.path or "/postgres").lstrip("/"))

    def _exec(self, sql, args=(), fetch=False):
        with self._lock:
            c = self._conn()
            try:
                cur = c.cursor()
                cur.execute(sql, args)
                rows = cur.fetchall() if fetch else None
                c.commit()
                return rows
            finally:
                c.close()

    def _init(self):
        self._exec("""CREATE TABLE IF NOT EXISTS sessions(
            id TEXT PRIMARY KEY, state JSONB NOT NULL, created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now())""")
        self._exec("""CREATE TABLE IF NOT EXISTS candidates(
            id TEXT PRIMARY KEY, payload JSONB NOT NULL, created_at TIMESTAMPTZ DEFAULT now())""")
        self._exec("""CREATE TABLE IF NOT EXISTS outbox(
            id BIGSERIAL PRIMARY KEY, event TEXT NOT NULL, payload JSONB NOT NULL,
            signature TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT now(),
            delivered_at TIMESTAMPTZ)""")
        try:
            self._exec("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception:
            pass   # pgvector 未装也能跑（关键词层不依赖它）

    def create_session(self, channel="agent_chat"):
        sid = "s_" + uuid.uuid4().hex[:12]
        self._exec("INSERT INTO sessions(id,state) VALUES(%s,%s::jsonb)", (sid, json.dumps({})))
        return sid

    def get_session(self, sid):
        rows = self._exec("SELECT id,state FROM sessions WHERE id=%s", (sid,), fetch=True)
        if not rows:
            return None
        return {"id": rows[0][0], "state": rows[0][1]}

    def save_session(self, sid, state):
        self._exec("UPDATE sessions SET state=%s::jsonb, updated_at=now() WHERE id=%s",
                   (json.dumps(state, ensure_ascii=False), sid))

    def create_candidate(self, fields):
        cid = "c_" + uuid.uuid4().hex[:10]
        c = dict(fields)
        c.update(id=cid, status="complete", created_at=now(), updated_at=now(),
                 retention_until=(datetime.now(timezone.utc)
                                  + timedelta(days=90)).isoformat(timespec="seconds"))
        self._exec("INSERT INTO candidates(id,payload) VALUES(%s,%s::jsonb)",
                   (cid, json.dumps(c, ensure_ascii=False)))
        return c

    def get_candidate(self, cid):
        rows = self._exec("SELECT payload FROM candidates WHERE id=%s", (cid,), fetch=True)
        return rows[0][0] if rows else None

    def list_candidates(self, limit=50, offset=0):
        rows = self._exec("SELECT payload FROM candidates ORDER BY created_at DESC LIMIT %s OFFSET %s",
                          (limit, offset), fetch=True)
        tot = self._exec("SELECT count(*) FROM candidates", fetch=True)[0][0]
        return [r[0] for r in rows], tot

    def close(self):
        pass


def build(dsn=""):
    if dsn:
        try:
            return PgStore(dsn)
        except Exception as e:
            raise RuntimeError("PG 连接失败: %s" % e)
    return MemoryStore()
