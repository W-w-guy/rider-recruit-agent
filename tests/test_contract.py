# -*- coding: utf-8 -*-
"""契约 v1 一致性：接口形状、错误体、动作取值。"""
import os, sys, unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

try:
    from fastapi.testclient import TestClient
    HAVE = True
except Exception:
    HAVE = False

try:
    import pydantic  # noqa: F401
    HAVE_PYD = True
except Exception:
    HAVE_PYD = False


@unittest.skipUnless(HAVE_PYD, "pydantic 未安装（先 pip install -r requirements.txt）")
class ContractShape(unittest.TestCase):
    """不依赖 FastAPI 也能验的部分：模型字段与动作枚举。"""

    def test_actions_enum(self):
        from app import contract
        want = {"show_stations", "booking_confirmed", "handoff", "end_minor"}
        got = set(contract.ACTION.__args__)
        self.assertEqual(got, want)

    def test_status_enum(self):
        from app import contract
        self.assertEqual(set(contract.STATUS.__args__),
                         {"new", "collecting", "complete", "booked", "interviewed",
                          "hired", "rejected", "handoff"})

    def test_candidate_required(self):
        from app import contract
        c = contract.Candidate(id="c1", created_at="t", updated_at="t")
        self.assertEqual(c.status, "collecting")
        self.assertEqual(c.health_cert, "unknown")
        self.assertEqual(c.source_channel, "agent_chat")

    def test_birth_ym_pattern(self):
        from app import contract
        with self.assertRaises(Exception):
            contract.Candidate(id="c1", created_at="t", updated_at="t", birth_ym="1993/04")

    def test_message_max_len(self):
        from app import contract
        with self.assertRaises(Exception):
            contract.MessageIn(text="x" * 2001)


@unittest.skipUnless(HAVE, "fastapi 未安装（run.py demo 不需要它）")
class ApiEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("DATABASE_URL", None)
        from app.main import app
        cls.c = TestClient(app)

    def test_health(self):
        r = self.c.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_full_enroll_7_of_7(self):
        sid = self.c.post("/api/v1/agent/sessions").json()["session_id"]
        said = ["我叫李强", "1993年4月", "住在文一西路", "全职", "有电动车", "明天", "干过两年外卖"]
        last = None
        for u in said:
            r = self.c.post("/api/v1/agent/sessions/%s/messages" % sid, json={"text": u})
            self.assertEqual(r.status_code, 200, r.text)
            last = r.json()
        self.assertEqual(last["progress"]["done"], 7)
        self.assertEqual(last["progress"]["total"], 7)
        self.assertIn("show_stations", last["actions"])
        self.assertEqual(last["candidate"]["job_type"], "fulltime")

    def test_session_not_found(self):
        r = self.c.post("/api/v1/agent/sessions/nope/messages", json={"text": "hi"})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["code"], "session_not_found")

    def test_empty_text_422(self):
        sid = self.c.post("/api/v1/agent/sessions").json()["session_id"]
        r = self.c.post("/api/v1/agent/sessions/%s/messages" % sid, json={"text": ""})
        self.assertEqual(r.status_code, 422)

    def test_openapi_paths(self):
        d = self.c.get("/openapi.json").json()
        for p in ["/api/v1/agent/sessions", "/api/v1/agent/sessions/{sid}/messages",
                  "/api/v1/stations", "/api/v1/candidates", "/health"]:
            self.assertIn(p, d["paths"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
