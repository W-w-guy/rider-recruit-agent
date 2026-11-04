# -*- coding: utf-8 -*-
"""任务1核心：7 槽位状态机 + 抽取（规则版，可换 LLM）。"""
import re, datetime

FIELDS = ["name", "birth_ym", "area_text", "job_type", "has_ebike",
          "start_text", "experience_text"]
ASK = {"name": "怎么称呼您？", "birth_ym": "请问您的出生年月（如 1991-05）？",
       "area_text": "您住哪个区域（到街道就行）？", "job_type": "想做全职还是兼职？",
       "has_ebike": "有自己的电动车吗？", "start_text": "最快什么时候能到岗？",
       "experience_text": "以前做过配送吗？做了多久？"}

_FULL = {ord(c): ord(c) - 0xFEE0 for c in "０１２３４５６７８９"}
_CN = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
       "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def norm(s):
    s = str(s).translate(_FULL)
    s = re.sub(r"[\u200b-\u200d\ufeff]", "", s)
    return s.strip()


def _cn2int(t):
    if t.isdigit():
        return int(t)
    if t in _CN:
        return _CN[t]
    if t.startswith("十"):
        return 10 + _CN.get(t[1], 0) if len(t) > 1 else 10
    if "十" in t:
        a, b = t.split("十")
        return _CN.get(a, 1) * 10 + (_CN.get(b, 0) if b else 0)
    return None


def extract_birth(t):
    t = norm(t)
    m = re.search(r"(19|20)(\d{2})\s*[-/年\.]\s*(\d{1,2})", t)
    if m:
        return "%s%s-%02d" % (m.group(1), m.group(2), int(m.group(3)))
    # ★ 口语插入语：1995年生的，1月 / 95年出生 3月份 —— 年份与月份之间夹字
    m = re.search(r"(19|20)?(\d{2})\s*年(?:出生|生的|生)?[^0-9]{0,4}(\d{1,2})\s*月", t)
    if m:
        y = int(m.group(2))
        y = y + (1900 if y >= 50 else 2000)
        mo = int(m.group(3))
        if 1 <= mo <= 12:
            return "%d-%02d" % (y, mo)
    m = re.search(r"([0-9]{2}|[一二三四五六七八九][零一二三四五六七八九])\s*年\s*(?:的)?\s*([0-9]{1,2}|[一二三四五六七八九十]{1,3})\s*月", t)
    if m:
        y = _cn2int(m.group(1)); mo = _cn2int(m.group(2))
        if y and mo and 1 <= mo <= 12:
            return "%d-%02d" % (1900 + y if y >= 50 else 2000 + y, mo)
    m = re.search(r"(\d{4})年?(\d{2})月?", t)
    if m:
        return "%s-%s" % (m.group(1), m.group(2))
    return None


def age_of(birth_ym, today=None):
    today = today or datetime.date.today()
    y, m = [int(x) for x in birth_ym.split("-")]
    return today.year - y - ((today.month, today.day) < (m, 15))


def extract(t, field):
    t = norm(t)
    if field == "name":
        m = re.search(r"(?:我叫|叫我|名字叫|是)\s*([\u4e00-\u9fa5]{1,4})", t)
        if m and m.group(1) not in ("全职", "兼职", "女的", "男的"):
            return m.group(1)
        m = re.search(r"我姓([\u4e00-\u9fa5])", t)
        return m.group(1) + "**" if m else None
    if field == "birth_ym":
        return extract_birth(t)
    if field == "area_text":
        m = re.search(r"([\u4e00-\u9fa5]{2,}(?:区|县|市))?([\u4e00-\u9fa5]{2,}(?:路|街|道|镇|村|小区|苑|里|巷))", t)
        if m:
            v = (m.group(1) or "") + m.group(2)
            # ★ 抽掉前导动词：住文一西路 → 文一西路（上一系列单踩过：地址召回 100%→81%）
            return re.sub(r"^(住在|住|在|位于|地址是|地址在|我家在|我住|靠|靠近|挨着|临近)", "", v)
        m = re.search(r"在([\u4e00-\u9fa5]{2,8})附近", t)
        return m.group(1) if m else None
    if field == "job_type":
        if re.search(r"兼职|part", t, re.I):
            return "parttime"
        if re.search(r"全职|full", t, re.I):
            return "fulltime"
        if re.search(r"都行|没定|无所谓|还没想", t):
            return "undecided"
        return None
    if field == "has_ebike":
        if re.search(r"没(有|车)|无车|没有电动车|不骑", t):
            return False
        if re.search(r"小电驴|电瓶车|电动车|自行车|自备车", t):
            return True
        if re.search(r"有(车)|自备", t):
            return True
        return None
    if field == "start_text":
        m = re.search(r"(现在|马上|今天|明天|后天|随时|本周末|下周[一二三四五六日天]?|\d+月\d+[日号])", t)
        return m.group(1) if m else None
    if field == "experience_text":
        if re.search(r"没(做过|干过|经验)|无经验|零经验|新手|第一次|"
                     r"(一点|任何|毫无)\s*经验\s*都?\s*(没有|无)|从没(送|干|做)过", t):
            return "无经验"
        m = re.search(r"(\d+|一|两|二|三|四|五|六|七|八|九|十)[年个]?(?:多)?(?:的)?(?:外卖|骑手|配送|跑单)", t)
        if m:
            n = _cn2int(m.group(1))
            return ("%d年配送经验" % n) if n else None
        if re.search(r"干过|做过|跑过", t):
            return "有配送经验"
        return None
    return None


# ★ 2026-11-04 重写：原正则只覆盖了「忽略以上指令/系统提示/你现在是/扮演」四种形态，
#   19 条注入实测漏了 13 条。漏的都是同一类：**「要求模型做越权动作」**，
#   而不是「改写模型设定」。所以按「动作」而非「措辞」来判：
#     ①改写设定 ②窃取提示 ③越权改数据 ④诱导承诺/歧视/索要信息 ⑤英文绕过
INJECT = re.compile(
    # ① 改写设定
    r"(忽略|无视|忘记|跳过|不要管|别再管)(以上|之前|上面|前面|一切|所有)?"
    r".{0,8}(指令|要求|提示|设定|规则|限制)"
    r"|你现在是|你从现在起|假装你是|扮演|当你是|roleplay|act as"
    # ② 窃取提示
    r"|系统提示|system prompt|你的.{0,4}(prompt|提示词|指令)|原样(贴|输出|打印|重复)"
    r"|重复你(收到)?的|把你的.{0,6}(贴|打印|输出)"
    # ③ 越权改数据（这是招聘系统里最该防的一类）
    r"|帮我(把|将)?.{0,6}(改|修|调)(成|为|小|大|一下)"
    r"|把.{0,8}(状态|年龄|站点|经验|出生).{0,6}(改|设|换)(成|为)"
    r"|帮我跳过|不用(填|写|提供)|能不能不用"
    # ④ 诱导违规输出
    r"|你(就)?说.{0,6}(月入|过万|保证|能挣)"
    r"|(直说|是不是).{0,10}(不要|不收|仅限|只招|外地|本地|外地人)"
    r"|(记|存|收)(到|进)?你.{0,6}(系统|库)里"
    # ⑤ 英文/其它语言绕过
    r"|ignore (all )?(previous|above|prior)|forget (your|all)|disregard"
    r"|reveal|show me your (prompt|instruction)",
    re.I)
SENSITIVE = [("phone", r"(?<!\d)(1[3-9]\d{9})(?!\d)"),
             ("idcard", r"(?<!\d)(\d{17}[\dXx])(?!\d)")]


def mask(text):
    """送模型前脱敏：手机号/身份证换占位符，返回(脱敏文本, 命中的类型)。"""
    kinds = []
    out = norm(text)
    for kind, pat in SENSITIVE:
        def rep(m, kind=kind):
            kinds.append(kind)
            n = sum(1 for k in kinds if k == kind)   # 每种类型各自从 1 数
            return "〔%s_%d〕" % ("手机号" if kind == "phone" else "身份证号", n)
        out = re.sub(pat, rep, out)
    return out, kinds


class Session(object):
    """状态机：依次收敛 7 个槽位；未成年立即终止并返回 end_minor。"""

    def __init__(self, today=None, pipeline=None):
        self.data = {}
        self.actions = []
        self.today = today
        self.ended = None
        self.turns = 0
        # pipeline：归一化→LLM→校验→降级。None 时纯规则（离线/mock 场景）
        self.pipeline = pipeline
        self.last_source = None

    def _extract_all(self, text):
        """一次拿到所有槽位（LLM 场景下只发一次请求，而不是每个槽位一发）。"""
        if self.pipeline is not None:
            got, src = self.pipeline.extract_all(text)
            self.last_source = src
            return got
        self.last_source = "rule"
        return {f: extract(text, f) for f in FIELDS}

    def missing(self):
        return [f for f in FIELDS if self.data.get(f) in (None, "")]

    def progress(self):
        return {"done": len(FIELDS) - len(self.missing()), "total": len(FIELDS),
                "fields": [f for f in FIELDS if self.data.get(f) not in (None, "")]}

    def to_state(self):
        return {"data": self.data, "ended": self.ended, "turns": self.turns,
                "created": bool(getattr(self, "_created", False)),
                "source": self.last_source}

    @classmethod
    def from_state(cls, st):
        s = cls()
        if st:
            s.data = dict(st.get("data") or {})
            s.ended = st.get("ended")
            s.turns = int(st.get("turns") or 0)
            s._created = bool(st.get("created"))
        return s

    def say(self, text):
        self.turns += 1
        self.actions = []
        clean, kinds = mask(text)
        got = self._extract_all(clean)
        if INJECT.search(clean):
            return {"reply": "我只负责骑手报名，其它要求帮不上忙。继续报名吧。",
                    "quick_replies": [], "progress": self.progress(), "actions": ["handoff"]}
        if kinds:
            self.actions.append("masked_sensitive")
        target = self.missing()[0] if self.missing() else None
        if self.ended:
            return {"reply": "报名已结束。", "quick_replies": [], "progress": self.progress(),
                    "actions": self.actions or ["end_minor"]}
        if target:
            v = got.get(target)
            if v not in (None, ""):
                # ★ 未成年检查必须在【落库之前】：先写 data 再判，会让
                #   progress 显示 2/7、且 birth_ym 留在会话状态里 —— 等于把未成年人
                #   的出生年月存进了系统。契约要求「识别后终止、不再追问」，
                #   隐含「不保留该字段」，所以这里先判后写。
                if target == "birth_ym" and age_of(v, self.today) < 18:
                    self.ended = "end_minor"
                    self.actions.append("end_minor")
                    return {"reply": "抱歉，未满 18 周岁无法登记，报名到此结束。",
                            "quick_replies": [], "progress": self.progress(),
                            "actions": self.actions}
                self.data[target] = v
                nxt = self.missing()
                self.actions.append("show_stations") if not nxt else None
                return {"reply": ("已记录%s。" % target) + ("接下来：" + ASK[nxt[0]] if nxt else "7 项已齐，可预约到站面试。"),
                        "quick_replies": [], "progress": self.progress(),
                        "actions": self.actions}
        if target:
            # ★ 兜底：问 A 时用户答了 B（很常见），不能把 B 丢掉并无限重问 A。
            for f2 in self.missing():
                if f2 == target:
                    continue
                v2 = got.get(f2)
                if v2 not in (None, "") and f2 != "name":
                    if f2 == "birth_ym" and age_of(v2, self.today) < 18:
                        self.ended = "end_minor"
                        self.actions.append("end_minor")
                        return {"reply": "抱歉，未满 18 周岁无法登记，报名到此结束。",
                                "quick_replies": [], "progress": self.progress(),
                                "actions": self.actions}
                    self.data[f2] = v2
                    nxt = self.missing()
                    return {"reply": "已记录%s。接下来：%s" % (f2, ASK[nxt[0]] if nxt else "已齐。"),
                            "quick_replies": [], "progress": self.progress(),
                            "actions": self.actions}
        if kinds:
            return {"reply": "这些信息我没有记录，也不用发给我；报名不需要身份证号或银行卡。",
                    "quick_replies": [], "progress": self.progress(), "actions": self.actions}
        nxt = self.missing()
        return {"reply": ("没听清，" + ASK[nxt[0]]) if nxt else "已齐。",
                "quick_replies": [], "progress": self.progress(), "actions": self.actions}
