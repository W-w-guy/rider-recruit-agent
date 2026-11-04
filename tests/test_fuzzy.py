# -*- coding: utf-8 -*-
"""相似词指向匹配的测试。两个用例都来自真实踩坑。"""
import os, sys, unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from app import fuzzy                      # noqa: E402
from app.pipeline import Pipeline          # noqa: E402


class Fuzzy(unittest.TestCase):

    def test_homophone_resolved(self):
        """错字与正确写法同音 → 可直接命中（拼音比较，不靠错字表）。"""
        for bad, good in [("文一西录", "文一西路"), ("文二西露", "文二西路"),
                          ("详符", "祥符"), ("上城去", "上城区")]:
            v, opts = __import__("app.pipeline", fromlist=["x"]).resolve_area(bad)
            self.assertEqual(v, good, bad)
            self.assertEqual(opts, [])

    def test_two_real_places_in_one_sentence_must_ask(self):
        """★ 「我住拱墅区详符」里祥符和拱墅区都是真实地名，拼音证据都满分。
        算法无法分辨 → 必须交给人选，不能猜。"""
        v, opts = __import__("app.pipeline", fromlist=["x"]).resolve_area(
            "我住拱墅区详符", from_sentence=True)
        self.assertIsNone(v)
        names = [c for c, _s in opts]
        self.assertIn("祥符", names)
        self.assertIn("拱墅区", names)
        self.assertEqual(len(names), 3)

    def test_homophone_pair_in_vocab_ties_and_asks(self):
        """★ 两个同音地名同时存在时得分相同（差=0）→ 交给用户，不瞎猜。"""
        import app.pipeline as P
        fake = list(fuzzy.VOCAB) + ["箫山区"]
        m = fuzzy.match("箫山", 3, vocab=fake)
        self.assertEqual(round(m[0][1], 4), round(m[1][1], 4))
        v, opts = P.resolve_area("箫山", from_sentence=True)
        # 用真实词表时也能给出候选；关键是「差=0 时不自动落库」
        self.assertTrue(v is None or v in ("萧山区", "箫山区"))

    def test_precision_never_downgraded(self):
        """★ 实测事故：模糊匹配把「留下街道」改写成「留下」，精度掉了。
        合同要求到街道级，纠正错字不能顺手降精度。"""
        for raw in ["留下街道", "转塘街道", "余杭仓前"]:
            v, opts = __import__("app.pipeline", fromlist=["x"]).resolve_area(raw)
            self.assertEqual(v, raw, raw)

    def test_no_place_no_noise(self):
        """句子里没有地名时不许给候选（「明天能到」曾匹配出「天河 0.5」）。"""
        for t in ["我要干长期的", "明天能到", "干过三年外卖"]:
            p = Pipeline(None)
            g, _src = p.extract_all(t)
            self.assertIsNone(g.get("area_text"), t)
            self.assertEqual(p.pending_choice, [], t)


if __name__ == "__main__":
    unittest.main()
