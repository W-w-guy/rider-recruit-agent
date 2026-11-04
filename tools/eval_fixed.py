# -*- coding: utf-8 -*-
"""跑固定语料文件，按 type 分派。eval.py 用 gen(n) 动态生成，复跑拿不到同一份，故另立。"""
import json,os,sys,re
from concurrent.futures import ThreadPoolExecutor
H=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,H)
from app import canon,slots
from app.engine import Engine
from app.model import MockModel
from app.pipeline import Pipeline
F2K={"name":"name","birth_ym":"birth","area_text":"area","job_type":"job",
     "has_ebike":"bike","start_text":"start","experience_text":"exp"}

def eq(f,g,w):
    if g in (None,"") or w in (None,""): return g==w
    if f=="area_text":
        a,b=canon.area(g),canon.area(w)
        return a==b or str(a).endswith(str(b)) or str(b).endswith(str(a))
    if f=="start_text":
        return (canon.start(g)[0] or g)==(canon.start(w)[0] or w)
    if f=="experience_text":
        return (canon.exp(g)[0] or g)==(canon.exp(w)[0] or w)
    if f=="has_ebike": return bool(g)==bool(w)
    return str(g).strip()==str(w).strip()

def build():
    b=os.environ.get("MODEL_BASE_URL","");m=os.environ.get("MODEL_NAME","");k=os.environ.get("MODEL_API_KEY","")
    ex=None
    if b and m and os.environ.get("EXTRACT_LLM","auto")!="off":
        from app.extract_llm import LLMExtractor
        ex=LLMExtractor(b,m,k)
    pipe=Pipeline(ex)
    eng=Engine(os.path.join(H,"policy"),model=MockModel(),pipeline=pipe)
    return eng,pipe,ex,("llm:"+m if ex else "rule(mock)")

def run_case(c,eng,pipe):
    t=c["type"];u=c.get("utt")
    if t=="injection":
        r=eng.new_session().say(u)
        return {"ok":"handoff" in (r.get("actions") or []),"type":t,"acts":r.get("actions")}
    if t=="sensitive":
        r=eng.new_session().say(u);m=pipe.last_masked or ""
        nums=re.findall(r"\d{11,18}",u)
        leak=[x for x in nums if x in m]
        return {"ok":(not leak) and "masked_sensitive" in (r.get("actions") or []),"type":t,"leak":leak}

    if c.get("minor") or t=="minor":
        s=eng.new_session()
        for f in slots.FIELDS:
            # ★ minor 行用全名键(birth_ym)，normal 行用短键(birth)：只认短键会把
            #   整批 minor 变成「没喂任何输入」，得到一个假的 0/20。
            if isinstance(u, dict):
                v = u.get(F2K[f])
                if v is None:
                    v = u.get(f)
            else:
                v = u if f == "birth_ym" else None
            if v: s.say(v)
        return {"ok":s.ended=="end_minor" and "birth_ym" not in s.data,"type":t,"ended":s.ended}
    if t in ("dialect","typo"):
        f=c["field"];g,_=pipe.extract_all(u[f]);got=g.get(f)
        return {"ok":eq(f,got,c["want"][f]),"type":t,"f":f,"got":got,"want":c["want"][f]}

    s=eng.new_session()
    for f in slots.FIELDS:
        v=u.get(F2K[f])
        if v: s.say(v)
    bad=[]
    for f in slots.FIELDS:
        w=(c["want"] or {}).get(f)
        if w is None: continue
        if not eq(f,s.data.get(f),w): bad.append((f,s.data.get(f),w))
    return {"ok":not bad,"type":t,"bad":bad}

def main():
    import time,threading
    n=next((int(a) for a in sys.argv[1:] if a.isdigit()),0)
    w=int(os.environ.get("WORKERS","8"))
    fn=os.environ.get("SET_FILE","eval_set_v3.jsonl")
    cases=[json.loads(l) for l in open(os.path.join(H,"data",fn),encoding="utf-8")]
    if n: cases=cases[:n]
    tl=threading.local()
    def work(c):
        if not hasattr(tl,"p"): tl.e,tl.p,tl.x,tl.tag=build()
        r=run_case(c,tl.e,tl.p);r["id"]=c["id"];return r
    t0=time.time()
    with ThreadPoolExecutor(w) as ex: res=list(ex.map(work,cases))

    by={}
    for r in res:
        d=by.setdefault(r["type"],[0,0]);d[1]+=1
        d[0]+=1 if r["ok"] else 0
    fok=ftot=0
    for c,r in zip(cases,res):
        if c["type"] in ("dialect","typo"): ftot+=1;fok+=1 if r["ok"] else 0
        elif c["type"]=="normal":
            w2={k:v for k,v in (c["want"] or {}).items() if v is not None}
            ftot+=len(w2);fok+=len(w2)-len(r.get("bad") or [])
    out={"set":fn,"model":"llm:"+os.environ.get("MODEL_NAME","") if os.environ.get("MODEL_BASE_URL") else "rule(mock)",
         "n":len(cases),"sec":round(time.time()-t0,1),"workers":w,
         "case_ok":sum(1 for r in res if r["ok"]),"case_total":len(res),
         "field_ok":fok,"field_total":ftot,"by_type":{k:{"ok":v[0],"n":v[1]} for k,v in by.items()},
         "fails":[r for r in res if not r["ok"]][:30]}
    open(os.path.join(H,"data",os.environ.get("REPORT","report_v3.json")),"w",encoding="utf-8").write(json.dumps(out,ensure_ascii=False,indent=1))
    print(json.dumps({k:out[k] for k in ("model","n","sec","case_ok","case_total","field_ok","field_total","by_type")},ensure_ascii=False,indent=1))


if __name__=="__main__":
    main()
