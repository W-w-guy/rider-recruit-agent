# -*- coding: utf-8 -*-
"""政策知识库：标题+正文按 ## 切块，关键词(BM25-ish) 检索，命中即附出处(文档名+版本)。
检索不到 → 返回 None，由上层转人工，绝不编造。

为什么先做关键词而不是 pgvector：pgvector 需要 embedding 模型，
mock 环境下没有真模型；关键词层必须能独立给出可复现的基准，
向量层作为可选的第二路（pgvector 可用时叠加），否则「RAG」在离线评测里无法自证。
"""
import math, os, re

VER = re.compile(r"_v(\d+)")
DOC = re.compile(r"^(.*)_v\d+\.md$")


def load(dirp):
    chunks = []
    for fn in sorted(os.listdir(dirp)):
        if not fn.endswith(".md"):
            continue
        ver = int(VER.search(fn).group(1)) if VER.search(fn) else 1
        base = DOC.match(fn)
        name = base.group(1) if base else fn[:-3]
        with open(os.path.join(dirp, fn), encoding="utf-8") as fh:
            txt = fh.read()
        title = ""
        for part in re.split(r"^## ", txt, flags=re.M)[1:]:
            head, _, body = part.partition("\n")
            chunks.append({"doc": name, "version": ver, "section": head.strip(),
                           "text": body.strip()})
    return chunks


STOP = ["什么时候", "什么", "多久", "怎么", "怎样", "是否", "需不需要", "要不要",
        "吗", "呢", "啊", "请问", "我想问", "想问", "一下", "可以", "能不能", "有没有"]


# ★ 同义扩展：客户问「工资」、政策写「报酬」，字面零重叠 → 召回 MISS。
# 这不是模型不够强，是词表不同；必须显式扩，否则「检索不到就转人工」
# 会把大量本可回答的问题推给人工（转人工率是验收隐含项）。
SYN = {"工资": "报酬 结算", "薪水": "报酬 结算", "薪资": "报酬 结算",
       "钱": "报酬 结算", "发钱": "发放 报酬", "发工资": "发放 报酬 结算",
       "押金": "收费 报名费", "扣钱": "收费", "退费": "收费",
       "到岗": "到站 上岗 面试", "上岗": "到站 面试", "上班": "上岗 到站",
       "健康证": "健康证 入职", "证件": "证件 核验", "试用": "试岗",
       "站点": "站点 名额", "选站": "站点 名额"}


def clean_q(q):
    for w in sorted(STOP, key=len, reverse=True):
        q = q.replace(w, " ")
    out = []
    for w, exp in SYN.items():
        if w in q:
            out.append(exp)
    return q + " " + " ".join(out)


def toks(s):
    s = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", " ", s)
    out = []
    for w in s.split():
        if re.match(r"^[0-9a-zA-Z]+$", w):
            out.append(w.lower())
        else:
            out += [w[i:i + 2] for i in range(len(w) - 1)] or [w]
    return out


def score(q, ch, avg, N, df):
    ts = toks(ch["section"] + " " + ch["text"])
    if not ts:
        return 0.0
    tf = {}
    for t in ts:
        tf[t] = tf.get(t, 0) + 1
    s = 0.0
    for t in toks(clean_q(q)):
        if t not in tf:
            continue
        idf = math.log(1 + (N - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5))
        s += idf * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * len(ts) / avg))
    return s


def search(chunks, q, topk=1, min_score=1.2):
    """★ 同一 section 多版本时只留版本最高的那份：v2 覆盖 v1，
    否则「到岗时间」会答成 v1 的 3 日（客户按 v2 验收，答旧值是错答）。"""
    df = {}
    for ch in chunks:
        for t in set(toks(ch["section"] + " " + ch["text"])):
            df[t] = df.get(t, 0) + 1
    avg = sum(len(toks(c["text"])) for c in chunks) / max(1, len(chunks))
    best = {}
    for c in chunks:
        k = (c["doc"], c["section"])
        if k not in best or c["version"] > best[k]["version"]:
            best[k] = c
    cand = list(best.values())
    ranked = sorted(((score(q, c, avg, len(cand), df), c) for c in cand),
                    key=lambda x: -x[0])
    if not ranked or ranked[0][0] < min_score:
        return []
    return [(s, c) for s, c in ranked[:topk] if s >= min_score]
