# -*- coding: utf-8 -*-
"""RAG / 护栏 / 降级 / 幂等 / outbox 签名。"""
import os, sys, unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from app import guard, kb                        # noqa: E402
from app.engine import Engine                    # noqa: E402
from app.mocks import station, vault             # noqa: E402
from app.model import MockModel                  # noqa: E402
from app.outbox import Outbox, sign, verify      # noqa: E402

POLICY = os.path.join(HERE, "policy")


class Rag(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ch = kb.load(POLICY)

    def test_version_newest_wins(self):
        """到岗时间 v1=3日、v2=5日；必须答 v2。"""
        r = kb.search(self.ch, "多久能到岗面试")
        self.assertEqual(r[0][1]["version"], 2)
        self.assertIn("5", r[0][1]["text"])

    def test_synonym_bridge(self):
        """客户问「工资」政策写「报酬」：不做同义扩展就必然 MISS。"""
        for q in ["工资什么时候发", "钱什么时候到手", "工资多久发一次"]:
            r = kb.search(self.ch, q)
            self.assertTrue(r, q)
            self.assertEqual(r[0][1]["section"], "结算周期", q)

    def test_miss_returns_empty(self):
        self.assertEqual(kb.search(self.ch, "火星上有没有水"), [])

    def test_deposit_maps_to_free_charge(self):
        r = kb.search(self.ch, "会收押金吗")
        self.assertEqual(r[0][1]["section"], "会不会扣钱")


class GuardTest(unittest.TestCase):
    def test_three_banned_classes(self):
        for text, want in [("保证月入8000以上", "income_promise"),
                           ("我们不招女性骑手", "discrimination"),
                           ("请提供身份证号和银行卡", "sensitive_request")]:
            self.assertIn(want, guard.check(text, cited=True), text)

    def test_citation_required(self):
        self.assertIn("no_citation", guard.check("报酬按周结算", cited=False))

    def test_clean_reply_passes(self):
        self.assertEqual(guard.check("报酬按周结算，每周三发放。（出处：x v2 / 结算周期）", cited=True), [])


class Degrade(unittest.TestCase):
    def test_timeout_hands_off_without_breaking(self):
        class Boom(MockModel):
            def chat(self, *a, **kw):
                raise TimeoutError("x")
        eng = Engine(POLICY, model=Boom())
        r = eng.ask_policy("试岗多久")
        self.assertTrue(r["degraded"])
        self.assertIn("handoff", r["actions"])
        self.assertEqual(eng.stats["degraded"], 1)

    def test_primary_ok_second_try(self):
        class Once(MockModel):
            def __init__(self):
                MockModel.__init__(self)
                self.n = 0

            def chat(self, p, c, **kw):
                self.n += 1
                if self.n == 1:
                    raise TimeoutError("first")
                return MockModel.chat(self, p, c)
        eng = Engine(POLICY, model=Once())
        self.assertTrue(eng.ask_policy("试岗多久")["degraded"])
        self.assertFalse(eng.ask_policy("试岗多久")["degraded"])


class MockTask3(unittest.TestCase):
    def setUp(self):
        station.reset()

    def test_quota_zero_excluded(self):
        ids = [s["id"] for s in station.query()]
        self.assertNotIn("st_hz_03", ids)

    def test_sort_by_distance(self):
        rows = station.query()
        self.assertEqual(rows, sorted(rows, key=lambda x: x["distance_km"]))

    def test_booking_idempotent(self):
        a = station.book("c1", "st_hz_01", "2026-11-06T09:00")
        b = station.book("c1", "st_hz_01", "2026-11-06T09:00")
        self.assertEqual(a["id"], b["id"])

    def test_quota_decrements(self):
        before = [s for s in station.STATIONS if s["id"] == "st_hz_02"][0]["open_quota"]
        station.book("c9", "st_hz_02", "2026-11-06T09:00")
        after = [s for s in station.STATIONS if s["id"] == "st_hz_02"][0]["open_quota"]
        self.assertEqual(after, before - 1)


class MockTask5(unittest.TestCase):
    def setUp(self):
        vault.reset()

    def test_token_deterministic(self):
        self.assertEqual(vault.tokenize("phone", "13800138000"),
                         vault.tokenize("phone", "13800138000"))

    def test_roundtrip_and_mask(self):
        t = vault.tokenize("phone", "13800138000")
        self.assertEqual(vault.detokenize(t), "13800138000")
        self.assertEqual(vault.mask("phone", "13800138000"), "138****8000")
        self.assertEqual(vault.mask("name", "王小明"), "王**")

    def test_unknown_token_raises(self):
        with self.assertRaises(KeyError):
            vault.detokenize("〔手机号_999〕")


class OutboxTest(unittest.TestCase):
    def test_hmac_signature_verifies(self):
        ob = Outbox("s3cr3t")
        r = ob.emit("candidate.completed", {"id": "c1"})
        self.assertTrue(verify("s3cr3t", r["body"], r["signature"]))
        self.assertFalse(verify("other", r["body"], r["signature"]))

    def test_unknown_event_rejected(self):
        with self.assertRaises(ValueError):
            Outbox("s").emit("candidate.hacked", {})

    def test_ack_removes_from_pending(self):
        ob = Outbox("s")
        r = ob.emit("handoff.requested", {})
        self.assertEqual(len(ob.pending()), 1)
        ob.ack(r["id"])
        self.assertEqual(ob.pending(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
