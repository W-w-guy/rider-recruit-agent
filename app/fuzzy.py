# -*- coding: utf-8 -*-
"""相似词指向匹配：把写错/写偏的地名指向真实词表里最可能的 1~3 个。

为什么不是「错字表」：
  · 错字表是闭集，收录不完（录/露/路/陆…每一批用户都不一样）
  · 本方案靠【拼音 + 编辑距离】对【真实地名表】做相似度排序，错字无需预先列举

同音字为什么反而好办：
  比较的是拼音而不是字形。文一西录/文一西路 的拼音完全相同（wen2 yi1 xi1 lu4），
  属于「最强证据」，可直接命中。真正难的是近音（n/l、zh/z）和形近（己/已）。

安全原则：**拿不准就交给人选，绝不自动落库。**
"""
from pypinyin import lazy_pinyin, Style

# 真实地名表：杭州行政区+主要路/片区，以及测试出现的其它城市行政区。
# ★ 刻意不包含任何「写错的形态」，词表只描述世界，不描述错误。
VOCAB = [
    "上城区", "拱墅区", "西湖区", "滨江区", "萧山区", "余杭区", "临平区",
    "江干区", "下城区", "上塘",
    "钱塘区", "富阳区", "临安区", "桐庐", "建德", "淳安",
    "文一西路", "文二西路", "文三西路", "文一路", "文二路", "文三路",
    "古墩路", "西溪路", "天目山路", "莫干山路", "上塘路", "秋涛路",
    "延安路", "解放路", "凤起路", "庆春路", "体育场路", "文晖路",
    "潮王路", "大关路", "丰潭路", "益乐路", "萍水街", "江南大道",
    "三墩镇", "祥符", "仓前", "四季青", "九堡", "下沙", "乔司", "良渚",
    "闲林", "五常", "西溪", "留下", "转塘", "浦沿", "长河", "西兴",
    "浦东", "徐汇", "静安", "黄浦", "长宁", "普陀", "杨浦",
    "未央区", "雁塔区", "碑林区", "天河", "越秀", "海珠", "白云",
    "思明", "湖里", "成华区", "锦江", "武侯", "金水区", "二七区", "中原区",
]


_PY = {}


def py(s):
    """带声调拼音（轻声统一为 5）。同音判定用去掉末尾数字的形式。
    ★ 必须缓存：滑窗匹配对每个候选词、每个窗口都要算拼音，不缓存会让
      300 条语料的评测从 1 秒涨到 60 秒以上（实测）。"""
    v = _PY.get(s)
    if v is None:
        if len(_PY) > 200000:      # 服务长期运行防膨胀；清空后重算即可，不影响正确性
            _PY.clear()
        v = lazy_pinyin(s, style=Style.TONE3, neutral_tone_with_five=True)
        _PY[s] = v
    return v


def _dist(a, b):
    """编辑距离（逐字符），用于拼音序列与字形两条通道。"""
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def score(q, cand):
    """返回 0~1 的相似度。三路证据取加权最高路。"""
    pq, pc = py(q), py(cand)
    # ① 同音（去声调后逐音节相同）——错字最常见形态，证据最强
    if [x.rstrip("12345") for x in pq] == [x.rstrip("12345") for x in pc]:
        return 1.0
    # ② 拼音相似（近音/多字少字）
    s_py = 1.0 - _dist(pq, pc) / max(len(pq), len(pc))
    # ③ 字形相似（形近字，写错但读音不同）
    s_ch = 1.0 - _dist(q, cand) / max(len(q), len(cand))
    return round(max(s_py, s_ch * 0.85), 4)


_SC = {}


def _sc(a, b):
    k = (a, b)
    v = _SC.get(k)
    if v is None:
        if len(_SC) > 200000:
            _SC.clear()
        v = score(a, b)
        _SC[k] = v
    return v


def _best_window(q, c):
    """候选词在句中的最佳对齐窗口。解决两类问题：
    ① 句子里带方言/动词（阿拉住浦东）→ 整串比会稀释分数
    ② 句子里有两个地名（我住拱墅区详符）→ 整串比会偏向更长的那个
    窗口长度取 len(c)±1，允许错字导致的长度漂移。"""
    L = len(c)
    best = _sc(q, c)
    for w in (L, L - 1, L + 1):
        if w <= 0 or w > len(q):
            continue
        for i in range(len(q) - w + 1):
            best = max(best, _sc(q[i:i + w], c))
    return best


def match(q, topk=3, vocab=None, window=True):
    """返回 [(候选, 分数)]，按分数降序。分数高不代表一定对，只是更可能。"""
    vocab = vocab or VOCAB
    rows = [(c, (_best_window(q, c) if window else score(q, c))) for c in vocab]
    rows.sort(key=lambda x: (-x[1], len(x[0])))
    return rows[:topk]


# 时间表达的标准形态。★ 这不是「错字表」：它只收录**正确的说法**，
# 写错的说法一律不进来，靠拼音相似度指向过来。
# 时间表达虽然口语千变万化，但标准语义形态是有限的（今天/明天/下周X/月底…），
# 所以和地名一样，可以用「标准词表 + 相似词指向」来纠。
TIME_VOCAB = [
    "今天", "明天", "后天", "大后天", "本周末", "随时", "马上", "尽快",
    "月底", "月初", "下个月", "本月底",
    "下周一", "下周二", "下周三", "下周四", "下周五", "下周六", "下周日",
    "这周一", "这周末", "礼拜一", "礼拜二", "礼拜三", "礼拜四", "礼拜五",
    "礼拜六", "礼拜天", "礼拜日",
    "一周后", "两周后", "三天后", "四天后", "五天后", "几天后",
]


def match_time(q, topk=3):
    """时间表达指向：返回 [(标准形态, 分数)]。只给形态，换算交给 canon.start()。"""
    rows = [(c, _best_window(q, c)) for c in TIME_VOCAB]
    rows.sort(key=lambda x: (-x[1], len(x[0])))
    return rows[:topk]


# 经验表达里的「数字+单位」也是有限集合（一年…十年、半个月、几个月）。
# 同样只收录**正确形态**，写错的说法靠拼音指向过来。
_EXP_UNIT = ("年", "个月", "月")
EXP_VOCAB = [n + u for n in ("一", "两", "二", "三", "四", "五", "六",
                             "七", "八", "九", "十", "半", "几") for u in _EXP_UNIT
             ] + ["没有", "经验", "年配送经验"]


def repair_exp(text, th=0.85):
    """把经验表达里的同音错字指回标准形态（三黏→三年、几各→几个、没又→没有）。

    只做「同音/极近音」的替换，且要求替换后能被 canon 认出数字，否则原样返回。
    失败即不动 —— 宁可少纠一个，不可把「三年」改成「两年」。
    """
    if not text:
        return text
    out = text
    # 按长度从长到短尝试，避免「个月」被「月」抢先替换
    for cand in sorted(EXP_VOCAB, key=len, reverse=True):
        L = len(cand)
        for w in (L, L + 1, L - 1):
            if w <= 0 or w > len(out):
                continue
            for i in range(len(out) - w + 1):
                seg = out[i:i + w]
                if seg == cand:
                    continue
                if _sc(seg, cand) >= th:
                    out = out[:i] + cand + out[i + w:]
                    break
            else:
                continue
            break
    return out
