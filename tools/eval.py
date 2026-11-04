# -*- coding: utf-8 -*-
"""一条命令跑出验收第 2 条的三个数。

★ 自动识别模型：配了 MODEL_BASE_URL+MODEL_NAME 就用真模型，否则用规则(mock)。
★ 报告里必须写明「本次用的是哪个模型」—— 不能让 mock 分和真模型分混为一谈。

用法:
  python tools/eval.py [n]               # 300 条合成集
  python tools/eval.py --wild            # 野外集（刻意避开模板，测泛化）
"""
import json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from app import slots                            # noqa: E402
from app.engine import Engine                    # noqa: E402
from app.model import MockModel                  # noqa: E402
from app.pipeline import Pipeline                # noqa: E402
from tools.gencases import POLICY, gen           # noqa: E402


def build_pipeline():
    """返回 (pipeline, 标签)。标签会打进报告，避免 mock 与真模型混淆。"""
    base = os.environ.get("MODEL_BASE_URL", "")
    model = os.environ.get("MODEL_NAME", "")
    key = os.environ.get("MODEL_API_KEY", "")
    if base and model and os.environ.get("EXTRACT_LLM", "auto") != "off":
        from app.extract_llm import LLMExtractor
        ex = LLMExtractor(base, model, key)
        return Pipeline(ex), "llm:%s" % model, ex
    return Pipeline(None), "rule(mock)", None


def run(n=300, wild=False):
    pipe, tag, ex = build_pipeline()
    eng = Engine(os.path.join(HERE, "policy"), model=MockModel(), pipeline=pipe)
    if wild:
        path = os.path.join(HERE, "data", "wild_set.jsonl")
        cases = [json.loads(l) for l in open(path, encoding="utf-8")]
        cases = [{"id": c["id"], "kind": "wild", "utt": {c["field"]: c["utt"]},
                  "want": {c["field"]: c["want"]}, "minor": False,
                  "field": c["field"]} for c in cases if c.get("want")]
    else:
        cases = gen(n)
    ex_ok = ex_tot = pol_ok = pol_tot = 0
    minor_ok = minor_tot = viol = 0
    fails = []
    for c in cases:
        s = eng.new_session()
        want = c["want"]
        if c["minor"]:
            for f in slots.FIELDS:
                key = {"name": "name", "birth_ym": "birth", "area_text": "area",
                       "job_type": "job", "has_ebike": "bike",
                       "start_text": "start", "experience_text": "exp"}[f]
                r = s.say(c["utt"][key])
                if "end_minor" in (r.get("actions") or []):
                    break
            minor_tot += 1
            if s.ended == "end_minor" and "birth_ym" not in s.data:
                minor_ok += 1
            continue
        if wild:
            f = c["field"]
            got, _src = pipe.extract_one(c["utt"][f], f)
            ex_tot += 1
            if got == want[f]:
                ex_ok += 1
            else:
                fails.append((c["id"], f, got, want[f]))
            continue
        for f in slots.FIELDS:
            key = {"name": "name", "birth_ym": "birth", "area_text": "area",
                   "job_type": "job", "has_ebike": "bike",
                   "start_text": "start", "experience_text": "exp"}[f]
            r = s.say(c["utt"][key])
            if "end_minor" in (r.get("actions") or []):
                break
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
    out = {"model": tag, "n": len(cases),
           "extract_acc": round(ex_ok / max(1, ex_tot), 4), "extract_hit": ex_ok,
           "extract_tot": ex_tot,
           "policy_acc": round(pol_ok / max(1, pol_tot), 4) if pol_tot else None,
           "policy_hit": pol_ok, "policy_tot": pol_tot,
           "violations": viol, "minor": "%d/%d" % (minor_ok, minor_tot),
           "pipeline": dict(pipe.stats),
           "llm": ex.stats() if ex else None,
           "fail_sample": fails[:10]}
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    wild = "--wild" in args
    n = next((int(a) for a in args if a.isdigit()), 300)
    r = run(n, wild)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    thr = 0.95
    ok = r["extract_acc"] >= thr and r["violations"] == 0
    print("\n模型: %s | 抽取 %.1f%% (门槛 %.0f%%) | 违规 %d"
          % (r["model"], r["extract_acc"] * 100, thr * 100, r["violations"]))
    print("验收第2条:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
