# -*- coding: utf-8 -*-
"""一条命令跑出验收第 2 条的三个数（可复现，mock 模型）。

用法: python tools/eval.py [n]        默认 300 条 → data/eval_300.jsonl
输出: extract_acc / policy_acc / violations / minor 四项 + 退出码
"""
import json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from app import guard, slots                       # noqa: E402
from app.engine import Engine                      # noqa: E402
from app.model import MockModel                    # noqa: E402
from tools.gencases import POLICY, gen             # noqa: E402


def run(n=300):
    eng = Engine(os.path.join(HERE, "policy"), model=MockModel())
    cases = gen(n)
    ex_ok = ex_tot = pol_ok = pol_tot = 0
    minor_ok = minor_tot = 0
    viol = 0
    fails = []
    for c in cases:
        s = eng.new_session()
        for f in slots.FIELDS:
            key = {"name": "name", "birth_ym": "birth", "area_text": "area",
                   "job_type": "job", "has_ebike": "bike",
                   "start_text": "start", "experience_text": "exp"}[f]
            r = s.say(c["utt"][key])
            if "end_minor" in (r.get("actions") or []):
                break
        want = c["want"]
        if c["minor"]:
            minor_tot += 1
            # ★ 只判「是否识别并终止」，不判 birth_ym 是否落库 ——
            #   契约要求未成年「终止、不再追问」，引擎的设计是【先判后写】，
            #   即该字段根本不留在会话状态里。原先这里断言 data 里有 birth_ym，
            #   等于用测试逼引擎保存未成年人信息，是测试写错了、不是实现错了。
            if s.ended == "end_minor" and "birth_ym" not in s.data:
                minor_ok += 1
            else:
                fails.append((c["id"], "minor", s.ended, s.data.get("birth_ym")))
            continue
        for f in slots.FIELDS:
            w = want.get(f)
            if w is None:
                continue
            ex_tot += 1
            if s.data.get(f) == w:
                ex_ok += 1
            else:
                fails.append((c["id"], f, s.data.get(f), w))
        q, sec, ver = POLICY[c["id"] % len(POLICY)]
        r = eng.ask_policy(q)
        pol_tot += 1
        cs = r.get("citations") or []
        if cs and cs[0]["section"] == sec and cs[0]["version"] == ver:
            pol_ok += 1
        else:
            fails.append((c["id"], "policy", cs, (sec, ver)))
        if r.get("violations"):
            viol += 1
    return {"n": n,
            "extract_acc": round(ex_ok / max(1, ex_tot), 4), "extract_hit": ex_ok,
            "extract_tot": ex_tot,
            "policy_acc": round(pol_ok / max(1, pol_tot), 4), "policy_hit": pol_ok,
            "policy_tot": pol_tot,
            "violations": viol, "minor": "%d/%d" % (minor_ok, minor_tot),
            "engine": dict(eng.stats), "fail_sample": fails[:10]}


if __name__ == "__main__":
    r = run(int(sys.argv[1]) if len(sys.argv) > 1 else 300)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    ok = (r["extract_acc"] >= 0.95 and r["policy_acc"] >= 0.90 and r["violations"] == 0
          and r["minor"].split("/")[0] == r["minor"].split("/")[1])
    print("\n验收第2条:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
