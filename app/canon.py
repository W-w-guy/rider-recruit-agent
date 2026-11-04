# -*- coding: utf-8 -*-
"""canonical 归一化层：把各种写法归并到一个序号下的统一说法。

设计依据（本项目的核心教训）：
  · 模型擅长「定位」（这句话里哪个片段是工作时间），不擅长「换算」（三年半 → 5 年，实测错）
  · 所以让模型输出原始 span，把算术/换算交给这里的确定性代码
  · 表外写法一律返回 None → 上层追问，绝不猜测。**宁可问一句，不可写错一条**

与 v1 的差别：v1 用正则边解析边归一化，规则散落在各处；
现在集中在一张表里，序号可被测试与审计引用（如「S12」= 两周后/半个月后/14天后）。
"""
import json, os, re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE = {}


def load():
    global _CACHE
    if not _CACHE:
        with open(os.path.join(HERE, "data", "CANON.json"), encoding="utf-8") as f:
            _CACHE = json.load(f)
    return _CACHE


CN_D = {"零": 0, "〇": 0, "一": 1, "壹": 1, "二": 2, "两": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def cn2int(s):
    s = str(s).strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if "十" in s:
        a, _, b = s.partition("十")
        hi = CN_D.get(a, 1) if a else 1
        lo = CN_D.get(b, 0) if b else 0
        return hi * 10 + lo
    if all(c in CN_D for c in s):
        return int("".join(str(CN_D[c]) for c in s)) if len(s) > 1 else CN_D[s]
    return None


def _lookup(kind, text):
    """在等价类表里查；返回 (序号, 统一说法) 或 (None, None)。"""
    t = re.sub(r"\s+", "", str(text or ""))
    table = load().get(kind, {})
    best = (None, None)
    for code, item in table.items():
        for form in item["forms"]:
            if form and form in t:
                if best[0] is None or len(form) > len(best[2] if len(best) > 2 else ""):
                    best = (code, item["canon"], form)
    return (best[0], best[1]) if best[0] else (None, None)


# ---------------- start_text ----------------
_WEEK = {"一": "下周一", "二": "下周二", "三": "下周三", "四": "下周四",
         "五": "下周五", "六": "下周六", "日": "下周日", "天": "下周日"}


def start(v):
    """返回 (canon值, 序号)。识别不了返回 (None, None)。"""
    t = re.sub(r"\s+", "", str(v or ""))
    if not t:
        return None, None
    m = re.search(r"下周\s*([一二三四五六日天1-7])", t)
    if m:
        c = m.group(1)
        c = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六", "7": "日"}.get(c, c)
        return _WEEK[c], "S08"
    m = re.search(r"下周\s*[一二三四五六日天]", t)
    if m:
        return None, None
    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", t)
    if m:
        return "%d月%d日" % (int(m.group(1)), int(m.group(2))), "S15"
    # ★ 先查等价类表再走数值正则：否则「两周后」会被正则先吃成「2周后」，
    #   而表里 S12 明确把 两周后/半个月后/14天后 归为同一类。表优先=口径唯一。
    code, val = _lookup("start_text", t)
    if code:
        if code == "S08" and val == "下周X":
            # 表里 S08 的统一说法是占位符「下周X」，命中后从原文取具体的星期几
            m2 = re.search(r"([一二三四五六日天])", t)
            if m2:
                return _WEEK[m2.group(1)], "S08"
        return val, code
    m = re.search(r"([一两二三四五六七八九十\d])\s*周\s*(以)?后", t)
    if m:
        n = cn2int(m.group(1)) or 1
        return ("一周后", "S09") if n == 1 else ("%d周后" % n, "S09")
    m = re.search(r"([一两二三四五六七八九十\d])\s*天\s*(以)?后", t)
    if m:
        n = cn2int(m.group(1))
        if n == 1:
            return "明天", "S02"
        if n == 2:
            return "两天后", "S10"
        if n == 3:
            return "三天后", "S11"
        return "%d天后" % n, "S11"
    return None, None


# ---------------- experience_text ----------------
def exp(v):
    """三年半 → 3年配送经验（向下取整，且明确不算 4 或 5）。"""
    t = re.sub(r"\s+", "", str(v or ""))
    if not t:
        return None, None
    if re.search(r"没(有)?(干过|做过|跑过|送过|经验)|新手|第一次|零经验|"
                 r"(一点|任何|毫无)\s*经验\s*都?\s*(没有|无)|从没|无经验", t):
        return "无经验", "E00"
    m = re.search(r"([一两二三四五六七八九十\d]+)\s*年\s*(半)?", t)
    if m:
        n = cn2int(m.group(1))
        if n:
            return "%d年配送经验" % n, "E01"
    m = re.search(r"([一两二三四五六七八九十\d]{1,2})\s*个?月", t)
    if m and re.search(r"干过|做过|跑过|送过|配送|外卖|骑手|美团|饿了么|达达", t):
        return "有配送经验", "E01"      # 不足一年，归到有经验
    if re.search(r"干过|做过|跑过|送过|配送|外卖|骑手|美团|饿了么|达达|老骑手", t):
        return "有配送经验", "E01"
    return None, None


# ---------------- job_type / has_ebike / area ----------------
def job(v):
    code, val = _lookup("job_type", v)
    return val, code


def bike(v):
    if isinstance(v, bool):
        return v, ("B01" if v else "B02")
    code, val = _lookup("has_ebike", v)
    return val, code


def area(v):
    t = re.sub(r"\s+", "", str(v or ""))
    if not t:
        return None
    for suf in sorted(load().get("area_suffix_drop", []), key=len, reverse=True):
        if t.endswith(suf):
            t = t[: -len(suf)]
    for pre in ("住在", "我住", "我家在", "地址是", "位于", "在", "靠", "靠近"):
        if t.startswith(pre):
            t = t[len(pre):]
            break
    return t or None


# ---------------- birth_ym ----------------
def birth(v, year_hint=None):
    """支持 2020 年代与 19xx；只给年份时按 -01（在标文里声明该约定）。"""
    t = re.sub(r"\s+", "", str(v or ""))
    if not t:
        return None
    m = re.search(r"((?:19|20)\d{2})[-/.年](\d{1,2})", t)
    if m and 1 <= int(m.group(2)) <= 12:
        return "%s-%02d" % (m.group(1), int(m.group(2)))
    m = re.search(r"([零〇一二三四五六七八九十]{2,4}|\d{2,4})年"
                  r"[^0-9零〇一二三四五六七八九十]{0,6}([一二三四五六七八九十]{1,3}|\d{1,2})月", t)
    if m:
        y = _year(m.group(1))
        mo = cn2int(m.group(2))
        if y and mo and 1 <= mo <= 12:
            return "%d-%02d" % (y, mo)
    m = re.search(r"((?:19|20)\d{2})\s*年?", t)
    if m:
        return "%s-01" % m.group(1)
    m = re.search(r"([零〇一二三四五六七八九十]{2,4}|\d{2})\s*年?", t)
    if m:
        y = _year(m.group(1))
        if y:
            return "%d-01" % y
    return None


def _year(raw):
    """两位年/中文年 → 四位年。51-99 → 19xx；00-50 → 20xx。"""
    y = cn2int(raw)
    if y is None:
        return None
    if y >= 1000:
        return y
    return 1900 + y if y >= 51 else 2000 + y
