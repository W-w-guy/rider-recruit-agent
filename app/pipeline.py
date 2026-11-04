# -*- coding: utf-8 -*-
"""抽取流水线：归一化 → LLM 抽取 → 规则校验 → 失败降级到规则。

为什么这四步缺一不可：
  ①归一化  模型看到干净文本（去零宽、全角转半角、繁转简），省 token 也更稳
  ②LLM     语义理解（「免贵姓李」「长期工」「我有美团的车」规则认不出）
  ③规则校验 模型会幻觉出不存在的年月/不合法枚举，**这一步是护栏不是装饰**
  ④降级    模型超时/超预算/输出不可解析时退回规则，报名流程不中断
"""
import re

from . import canon, fuzzy, slots

VALID_YEAR = (1940, 2020)

# ---------------- 归一化（不是校验）----------------
# ★ 2026-11-04 修：原 validate() 对 start_text / experience_text 采取「格式不符就丢弃」，
#   结果模型答对的「跑了五年饿了么」被扔掉（模型给的是原话，不是规范值）。
#   正确做法是【先归一化，再判断能不能用】，而不是直接用格式当闸门。
_START_RULES = [
    (r"礼拜天|礼拜日|周日|周天|星期日", "本周末"),
    (r"本周末|这周(末|六|日)|周末", "本周末"),
    (r"今天|今日", "今天"), (r"明天|明日", "明天"), (r"后天", "后天"),
    (r"随时|随时都行", "随时"), (r"马上|立刻|立即", "马上"),
    (r"尽快|越快越好", "尽快"), (r"月底", "月底"), (r"下个?月", "下个月"),
]
_WEEK = {"一": "下周一", "二": "下周二", "三": "下周三", "四": "下周四",
         "五": "下周五", "六": "下周六", "日": "下周日", "天": "下周日"}
_CN = {"零": 0, "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
       "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cnint(s):
    if s.isdigit():
        return int(s)
    if s in _CN:
        return _CN[s]
    if "十" in s:
        a, _, b = s.partition("十")
        return (_CN.get(a, 1) if a else 1) * 10 + (_CN.get(b, 0) if b else 0)
    return None


def norm_start(v):
    v = slots.norm(v).strip()
    m = re.search(r"下周\s*([一二三四五六日天1-7])", v)
    if m:
        c = m.group(1)
        c = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五",
             "6": "六", "7": "日"}.get(c, c)
        return _WEEK[c]
    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", v)
    if m:
        return "%d月%d日" % (int(m.group(1)), int(m.group(2)))
    for pat, canon in _START_RULES:
        if re.search(pat, v):
            return canon
    m = re.search(r"([一两二三四五六七八九十\d])\s*周后", v)
    if m:
        n = _cnint(m.group(1))
        return "一周后" if n in (None, 1) else "%d周后" % n
    m = re.search(r"([一两二三四五六七八九十\d])\s*天(以)?后", v)
    if m:
        n = _cnint(m.group(1))
        if n == 1:
            return "明天"
        # ★ 2026-11-04 修：模型给「3天后」、规则给「三天后」，同一含义两种写法
        #   会让「准确率」凭空掉分。统一成中文数字。
        CN = "零一二三四五六七八九十"
        return (CN[n] if n and n < 11 else str(n)) + "天后"
    return v[:16] if len(v) <= 16 else None


def norm_exp(v):
    v = slots.norm(v).strip()
    if re.search(r"没(有)?(干过|做过|跑过|经验)|新手|第一次|零经验|"
                 r"(一点|任何|毫无)\s*经验\s*都?\s*(没有|无)|经验都没有|从没(送|干|做)过", v):
        return "无经验"
    m = re.search(r"([一两二三四五六七八九十\d])\s*年", v)
    if m:
        n = _cnint(m.group(1))
        if n:
            return "%d年配送经验" % n
    m = re.search(r"([一两二三四五六七八九十\d]{1,2})\s*个?月", v)
    if m and re.search(r"干过|做过|跑过|送过|配送|外卖|骑手|美团|饿了么", v):
        return "有配送经验"          # 「做过几个月」不足 1 年，归到有经验
    if re.search(r"干过|做过|跑过|送过|配送|外卖|骑手|美团|饿了么|老骑手", v):
        return "有配送经验"
    return None


_LANDMARK = re.compile(r"(地铁口|地铁站|地铁|站台|路口|旁边|附近|那边|这边|这块|一带|周围|门口)$")


def norm_area(v):
    v = slots.norm(v).strip()
    for _ in range(3):
        n2 = _LANDMARK.sub("", v)
        if n2 == v:
            break
        v = n2
    return v[:24] or None


def validate(obj):
    """模型输出（span-first）→ 规范值。

    分工原则：
      · 模型负责「定位」：这段话说的是哪几个字
      · 本函数负责「换算」：三年半 → 3年配送经验 / 半个月后 → 两周后（S12）
        实测证明换算交给模型会出错（三年半曾被判成 5 年），交给确定性代码不会。
    任何一项不合规 → 该项置 None（宁缺勿错，由上层追问）。
    """
    out = {}
    name = obj.get("name")
    if isinstance(name, str) and name.strip():
        n = slots.norm(name).strip()
        n = re.sub(r"[^\u4e00-\u9fa5A-Za-z·]", "", n)
        if 1 <= len(n) <= 6:
            out["name"] = n

    birth = canon.birth(obj.get("birth_raw")) if obj.get("birth_raw") else None
    if birth:
        y = int(birth[:4])
        if VALID_YEAR[0] <= y <= VALID_YEAR[1]:
            out["birth_ym"] = birth

    area = obj.get("area_text")
    if isinstance(area, str) and area.strip():
        a = canon.area(area)
        if a:
            out["area_text"] = a

    job = obj.get("job_type")
    if job in ("fulltime", "parttime", "undecided"):
        out["job_type"] = job
    elif isinstance(job, str) and job.strip():
        jv, _ = canon.job(job)
        if jv:
            out["job_type"] = jv

    bike = obj.get("has_ebike")
    if isinstance(bike, bool):
        out["has_ebike"] = bike
    elif isinstance(bike, str):
        bv, _ = canon.bike(bike)
        if bv is not None:
            out["has_ebike"] = bv

    st, sco = canon.start(obj.get("start_raw")) if obj.get("start_raw") else (None, None)
    if st:
        out["start_text"] = st
        out["_code_start"] = sco
    ex, eco = canon.exp(obj.get("exp_raw")) if obj.get("exp_raw") else (None, None)
    if ex:
        out["experience_text"] = ex
        out["_code_exp"] = eco
    return out


# 位置语境词：普通话 + 方言（系/嘅/搁/呆）+ 常见动词。
# 只用于「规则没抽到地名、要从整句再捞一次」这一条路径，防止把时间/经验句当地名。
_AREA_CTX = re.compile(r"住|在|位于|地址|附近|那边|这边|这带|那块|那儿|窝|驻|到|"
                       r"系|嘅|搁|呆|赖|蹲")


def resolve_time(raw, auto_th=0.85, gap_th=0.15):
    """到岗时间相似词指向。规则：同音/近音指向标准形态，换算仍交给 canon.start()。

    ★ 为什么时间也能这么做：地名有官方词表，时间没有，但**标准语义形态是有限的**
      （今天/明天/下周X/月底/随时…），而用户的错法几乎都是同音写错
      （名天→明天、下粥一→下周一、后田→后天、月低→月底），拼音一比就中。
    ★ 拿不准一律不认，返回 None 让系统照常追问。
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    if canon.start(raw)[0]:              # 已经能被 canon 认出来，不必再猜
        return None
    m = fuzzy.match_time(raw, 3)
    if not m or m[0][1] < auto_th:
        return None
    gap = m[0][1] - (m[1][1] if len(m) > 1 else 0.0)
    if gap < gap_th:
        return None
    return canon.start(m[0][0])[0] or m[0][0]


def resolve_area(raw, auto_th=0.85, gap_th=0.15, show_th=0.6, from_sentence=False):
    """地名解析成真实地名；拿不准就返回 (None, 前三个候选)。

    为什么要有这一步：地名是有闭集词表的东西（真实站点/行政区），
    所以「写错一个字」可以被词表纠正，不需要预先列举错字。
    时间/经验没有这种词表，不适用，只能靠模型。

    为什么拿不准要交给人：实测「我住拱墅区详符」里祥符与拱墅区都是真实地名、
    拼音证据都满分（差=0），算法无法分辨到底问哪一个 —— 猜错就把人派到错的站点。
    """
    raw = (raw or "").strip()
    if not raw:
        return None, []
    if raw in fuzzy.VOCAB:                       # 本来就是标准地名，不动
        return raw, []
    if not from_sentence:
        # ★ 抽出来的值里已经含有真实地名 → 保留原值。
        #   实测事故：规则给出「留下街道」「转塘街道」，模糊匹配把它们改写成「留下」
        #   「转塘」，精度掉了，而合同要求的正是「到街道级」。**纠正错字不能顺手降精度。**
        for c in fuzzy.VOCAB:
            if c in raw:
                return raw, []
    m = fuzzy.match(raw, 3)
    if not m:
        return None, []
    gap = m[0][1] - (m[1][1] if len(m) > 1 else 0.0)
    if m[0][1] >= auto_th and gap >= gap_th:
        return m[0][0], []
    # ★ 展示下限：低于 show_th 的候选是噪音（「明天能到」会匹配出「天河 0.5」），
    #   宁可不给选项，让系统照常追问，也不能把人引到错的地名上。
    if m[0][1] < show_th:
        return None, []
    return None, [(c, round(sc, 2)) for c, sc in m]


class Pipeline(object):
    def __init__(self, llm=None):
        self.llm = llm
        self.stats = {"llm_used": 0, "llm_ok": 0, "llm_fail": 0, "rule_fallback": 0}
        self.last_codes = {}
        self.last_masked = ""
        self.pending_choice = []

    def _area(self, merged, clean):
        """地名相似词指向：写错/写偏的地名对到真实地名表。两个入口都必须过这里，
        ★ 否则纯规则模式（llm=None）会提前 return，这条后处理永远跑不到。"""
        self.pending_choice = []
        if merged.get("area_text"):
            v, opts = resolve_area(merged["area_text"])
            if v:
                merged["area_text"] = v
            else:
                self.pending_choice = opts      # 交给人选，绝不自动落库
        if not merged.get("start_text"):
            v = resolve_time(clean)
            if v:
                merged["start_text"] = v
        if not merged.get("area_text"):
            # 规则因错字整条失配（文一西录：地址必须带 路/街/道）→ 用原句再试一次。
            # 阈值不放宽：没有真实地名能到 0.85 的句子（如「我要干长期的」）一律不动。
            # ★ 从整句捞地名必须要求「位置语境」，否则会误伤：
            #   「下个里拜一」（下周一的错字）会被匹配成地名「下个里」。
            #   地名在口语里几乎总跟着 住/在/位于/附近 之类的词。
            if _AREA_CTX.search(clean):
                v, opts = resolve_area(clean, from_sentence=True)
                if v:
                    merged["area_text"] = v
                elif opts:
                    self.pending_choice = opts
        return merged

    def extract_all(self, text):
        """返回 (fields_dict, source)。source ∈ {llm, rule, hybrid}"""
        clean = slots.norm(text)
        rule_all = {}
        for f in slots.FIELDS:
            v = slots.extract(clean, f)
            if v is not None:
                rule_all[f] = v
        if self.llm is None:
            self.stats["rule_fallback"] += 1
            self.pending_choice = []
            return self._area(rule_all, clean), "rule"
        self.stats["llm_used"] += 1
        # ★ 2026-11-04 修（验收第4条）：送进模型的必须是【脱敏后】的文本。
        #   原来这里直接把 clean 交给模型，手机号/身份证原值会进入请求体 ——
        #   而 slots.mask() 只在 Session.say() 里被调用，Pipeline 这条路径漏了。
        #   靠"代码看起来会脱敏"不算，必须由抓包断言证明。
        masked, _kinds = slots.mask(clean)
        self.last_masked = masked
        raw = self.llm.extract(masked)
        if raw is None:
            self.stats["llm_fail"] += 1
            self.stats["rule_fallback"] += 1
            return self._area(rule_all, clean), "rule"
        self.stats["llm_ok"] += 1
        llm_ok_all = validate(raw)
        self.last_codes = {k: v for k, v in llm_ok_all.items() if k.startswith("_")}
        llm_ok = {k: v for k, v in llm_ok_all.items() if not k.startswith("_")}
        # 合并：模型给了就用模型（语义更强），模型没给的用规则兜
        merged = dict(rule_all)
        merged.update(llm_ok)
        merged = self._area(merged, clean)
        src = "hybrid" if (llm_ok and rule_all) else ("llm" if llm_ok else "rule")
        return merged, src

    def extract_one(self, text, field):
        got, src = self.extract_all(text)
        return got.get(field), src
