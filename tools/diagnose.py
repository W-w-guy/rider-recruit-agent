# -*- coding: utf-8 -*-
"""模型体检报告：一条命令分清「模型不行」还是「框架不行」。

为什么需要它：
  合同要求「字段抽取准确率 ≥95%」，但准确率由**接入的模型**决定，不由框架决定。
  框架能保证的是：接口可插拔、失败能降级、幻觉有护栏、分数可复跑。
  所以本工具不承诺分数，只输出**可归因的事实**，客户自己判断该换模型还是找我们。

用法：
  python tools/diagnose.py                 # 规则基线（不调模型，零成本）
  MODEL_BASE_URL=... MODEL_NAME=... MODEL_API_KEY=... python tools/diagnose.py
"""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from app.engine import Engine                     # noqa: E402
from app.model import MockModel                   # noqa: E402
from app.pipeline import Pipeline                 # noqa: E402
from tools.eval_fixed import build, eq, run_case  # noqa: E402

# 各字段在真实业务里的重要性权重（合同只写「≥95%」，没写权重，此处是我方建议口径，
# 客户可改）。称呼/出生年月错 → 建错档；区域错 → 派错站点；经验错 → 派错难度单。
WEIGHT = {"name": 2, "birth_ym": 3, "area_text": 3, "job_type": 2,
          "has_ebike": 2, "start_text": 2, "experience_text": 3}


def load(fn):
    rows = [json.loads(l) for l in open(os.path.join(HERE, "data", fn), encoding="utf-8")]
    return rows


def run(pipe, eng, cases, workers=8):
    import threading
    tl = threading.local()

    def work(c):
        if not hasattr(tl, "e"):
            tl.e, tl.p = eng, pipe
        try:
            r = run_case(c, tl.e, tl.p)
        except Exception as e:                     # 单条异常不能中断整批体检
            r = {"ok": False, "type": c.get("type"), "err": type(e).__name__}
        r["id"] = c.get("id")
        return r

    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(work, cases))


def summarize(res, cases, tag):
    by_f = {}
    for c, r in zip(cases, res):
        t = c.get("type")
        if t in ("dialect", "typo", "blind"):
            f = c.get("field")
            d = by_f.setdefault(f, [0, 0])
            d[1] += 1
            d[0] += 1 if r.get("ok") else 0
        elif t == "normal":
            for f in (c.get("want") or {}):
                if (c["want"] or {}).get(f) is None:
                    continue
                d = by_f.setdefault(f, [0, 0])
                d[1] += 1
                d[0] += 0 if any(b[0] == f for b in (r.get("bad") or [])) else 1
    tot_ok = sum(v[0] for v in by_f.values())
    tot_n = sum(v[1] for v in by_f.values())
    w_ok = sum(WEIGHT.get(f, 1) * v[0] for f, v in by_f.items())
    w_n = sum(WEIGHT.get(f, 1) * v[1] for f, v in by_f.items())
    return {"model": tag, "field_ok": tot_ok, "field_n": tot_n,
            "field_acc": round(100.0 * tot_ok / max(1, tot_n), 2),
            "weighted_acc": round(100.0 * w_ok / max(1, w_n), 2),
            "by_field": {f: {"ok": v[0], "n": v[1],
                             "acc": round(100.0 * v[0] / max(1, v[1]), 1)}
                         for f, v in sorted(by_f.items())}}


def main():
    eng, pipe, ex, tag = build()
    is_llm = ex is not None
    print("=" * 62)
    print("模型体检报告")
    print("  本次使用：%s" % tag)
    if not is_llm:
        print("  ★ 未配置 MODEL_BASE_URL / MODEL_NAME → 这是【纯规则基线】，不是模型成绩")
    print("=" * 62)

    out = {"model": tag, "is_llm": is_llm}

    # ① 主评测集（含 normal 的常规口径）
    c300 = load("eval_set_v3.jsonl")
    r300 = run(pipe, eng, c300)
    out["main"] = summarize(r300, c300, tag)

    # ② 盲测集（本实现未参与设计，最能反映真实泛化）
    cb = load("blind2.jsonl")
    rb = run(pipe, eng, cb)
    out["blind"] = summarize(rb, cb, tag)

    # ③ 护栏与安全（与模型能力无关，属框架责任）
    inj = [c for c in c300 if c.get("type") == "injection"]
    sen = [c for c in c300 if c.get("type") == "sensitive"]
    mnt = [c for c in c300 if c.get("type") == "minor"]
    ri, rs, rm = run(pipe, eng, inj), run(pipe, eng, sen), run(pipe, eng, mnt)
    out["safety"] = {
        "injection_blocked": "%d/%d" % (sum(1 for r in ri if r["ok"]), len(ri)),
        "sensitive_not_leaked": "%d/%d" % (sum(1 for r in rs if r["ok"]), len(rs)),
        "minor_terminated": "%d/%d" % (sum(1 for r in rm if r["ok"]), len(rm)),
    }

    # ④ 降级率（模型可用性，属框架责任）
    st = dict(pipe.stats or {})
    used = st.get("llm_used") or 0
    fails = st.get("llm_fail") or 0
    out["pipeline"] = dict(st, fallback_rate=("%.1f%%" % (100.0 * fails / used) if used else "n/a"))
    if ex is not None:
        out["llm"] = ex.stats() if hasattr(ex, "stats") else {}

    print(json.dumps(out, ensure_ascii=False, indent=1))

    # ⑤ 归因结论（不替客户做决定，只给事实和判断依据）
    print("\n" + "-" * 62)
    print("归因")
    print("  主评测集（300 条）       : %.2f%%" % out["main"]["field_acc"])
    print("  盲测集（未参与设计）     : %.2f%%（加权 %.2f%%）"
          % (out["blind"]["field_acc"], out["blind"]["weighted_acc"]))
    print("  安全三项（框架责任）     : 注入 %s / 敏感 %s / 未成年 %s"
          % (out["safety"]["injection_blocked"], out["safety"]["sensitive_not_leaked"],
             out["safety"]["minor_terminated"]))
    print("  降级率（框架责任）       : %s" % out["pipeline"]["fallback_rate"])
    weak = sorted(out["blind"]["by_field"].items(), key=lambda kv: kv[1]["acc"])[:3]
    print("  最弱字段                 : " + " / ".join("%s %.0f%%" % (k, v["acc"]) for k, v in weak))
    print("\n  判定依据：≥95% 的准确率取决于接入模型的语义能力，本框架不承诺固定分数。")
    print("  若盲测 <95%，请先用更强抽取模型复跑本命令；框架侧（安全三项、降级率）已单列。")
    open(os.path.join(HERE, "data", "diagnose.json"), "w", encoding="utf-8", newline="\n").write(
        json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
