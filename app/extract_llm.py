# -*- coding: utf-8 -*-
"""LLM 抽取层：一次调用抽取全部 7 个槽位，JSON 强约束，失败即返回 None。

设计要点（为什么不是「一句话一个请求」）：
  · 一次拿全 7 个字段 → token 更省、往返更少
  · 输出必须能 json.loads，解析失败一律当「模型不可用」，由上层降级到规则
  · **不做任何格式修正**：只做校验，不替模型补齐。模型给不出就让规则层兜
"""
import json, re, time, urllib.request

# span-first：年月/到岗/经验给原文片段，其余直接给值
FIELDS = ["name", "birth_raw", "area_text", "job_type", "has_ebike",
          "start_raw", "exp_raw"]

SYS = """你是骑手招聘报名表的**定位器**。任务不是换算，而是从用户这句话里
**原样摘出**相关词片段（span）。换算由程序完成，你只负责找对位置。

只输出一个 JSON 对象，不要解释、不要 Markdown 代码块。

{
  "name":      "人名，只到名字，去掉称谓动词；只有姓就只给姓；没有就 null",
  "birth_raw": "出生年月的**原文片段**，如 \"零一年三月\" / \"91.5\" / \"九七年的\"；没有就 null",
  "area_text": "地名，只保留地名本身，去掉住在/在/附近/那边/地铁口等动词方位词；没有就 null",
  "job_type":  "fulltime 或 parttime 或 undecided",
  "has_ebike": true / false / null,
  "start_raw": "到岗时间的**原文片段**，如 \"半个月后\" / \"这周日\" / \"明天一早\"；没有就 null",
  "exp_raw":   "配送经验的**原文片段**，如 \"三年半\" / \"干过一阵子\" / \"完全没有经验\"；没有就 null"
}

## 关键要求
1. **birth_raw / start_raw / exp_raw 必须是原文片段，不许自己换算或改写**
   用户说“送了三年半外卖”，输出 exp_raw="三年半"；
   绝对不要输出“3年配送经验”或“5年配送经验”——那是程序的工作。
   用户说“半个月后”，输出 start_raw="半个月后"，不要改成“两周后”。
2. job_type 可做常识归类：长期工/正式编制/正常班→fulltime；
   临时工/暑期工/打零工→parttime；都行/你安排/看情况→undecided
3. 用户没说的，一律 null。不许编造、不许推测。
4. 只输出 JSON。
"""


class LLMExtractor(object):
    def __init__(self, base_url, model, api_key=None, timeout_s=30, max_tokens=900):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or ""
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.calls = 0
        self.tokens = 0
        self.fails = 0
        self.last_error = None

    def extract(self, text):
        """返回 dict（可能含 null）或 None（模型不可用/输出不可解析）。"""
        out = self._call(text, self.max_tokens)
        if out is None and self.last_error == "empty_content":
            # ★ 2026-11-04 修：推理模型（如 deepseek-flash）会把 max_tokens 全花在
            #   reasoning 上，content 返回空串。实测 320 token 时「91.5.20」直接空返回，
            #   看起来像模型不认，其实是额度不够。这里翻倍重试一次。
            out = self._call(text, self.max_tokens * 2)
        return out

    def _call(self, text, budget):
        self.calls += 1
        body = json.dumps({
            "model": self.model, "temperature": 0, "max_tokens": budget,
            "messages": [{"role": "system", "content": SYS},
                         {"role": "user", "content": "这句话：%s" % text}],
        }).encode("utf-8")
        req = urllib.request.Request(self.base_url + "/chat/completions",
                                     data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", "Bearer " + self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                d = json.load(r)
        except Exception as e:
            self.fails += 1
            self.last_error = "%s" % type(e).__name__
            return None
        self.tokens += int((d.get("usage") or {}).get("total_tokens") or 0)
        raw = (d["choices"][0]["message"].get("content") or "").strip()
        if not raw:
            self.fails += 1
            self.last_error = "empty_content"      # 推理模型 max_tokens 太小会走这里
            return None
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            self.fails += 1
            self.last_error = "no_json"
            return None
        try:
            obj = json.loads(m.group(0))
        except Exception:
            self.fails += 1
            self.last_error = "bad_json"
            return None
        return {k: obj.get(k) for k in FIELDS}

    def stats(self):
        return {"model": self.model, "calls": self.calls, "tokens": self.tokens,
                "fails": self.fails, "last_error": self.last_error}
