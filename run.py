#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""零依赖入口：不装任何第三方包也能跑 demo（出包环境用）。

  python run.py demo      # 跑通一次 7 项完整报名 + 一次政策问答，产物落 out/
  python run.py serve     # 起 FastAPI（需要 requirements.txt 里的依赖）
  python run.py version
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def demo(outdir="out"):
    from app import slots
    from app.engine import Engine
    from app.model import MockModel

    os.makedirs(outdir, exist_ok=True)
    eng = Engine(os.path.join(HERE, "policy"), model=MockModel())
    s = eng.new_session()
    said = ["我叫李强", "1993年4月", "住在文一西路", "全职", "有电动车", "明天", "干过两年外卖"]
    trace = []
    for u in said:
        r = s.say(u)
        trace.append({"in": u, "reply": r["reply"], "progress": r["progress"]})
    cand = eng.on_complete(s) if not s.missing() else {}
    pol = [eng.ask_policy(q) for q in ("工资什么时候发", "试岗多久", "火星上有没有水")]

    rep = {"turns": len(said), "progress": trace[-1]["progress"] if trace else {},
           "candidate": cand,
           "policy": [{"q": q, "cites": p.get("citations"), "handoff": "handoff" in (p.get("actions") or [])}
                      for q, p in zip(("工资什么时候发", "试岗多久", "火星上有没有水"), pol)],
           "stats": eng.stats}
    with open(os.path.join(outdir, "demo_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    ok = (rep["progress"].get("done") == 7 and rep["progress"].get("total") == 7
          and not rep["policy"][2]["cites"])
    print("\ndemo:", "OK" if ok else "FAIL")
    return 0 if ok else 2


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "demo"
    if cmd == "demo":
        return demo(argv[2] if len(argv) > 2 else "out")
    if cmd == "serve":
        import uvicorn
        uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("API_PORT", "8080")))
        return 0
    if cmd == "version":
        from app import __version__
        print(__version__)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
