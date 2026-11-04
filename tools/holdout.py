# -*- coding: utf-8 -*-
"""留出集：用【没为它们写过规则】的说法，测泛化而不是测自己。

合成集 100% 只说明「规则覆盖了自己造的说法」。这一份如实暴露边界。"""
import os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from app import slots                            # noqa: E402

C = [("name", "俺叫王强", "王强"), ("name", "大家都喊我小李", None),
     ("birth_ym", "九五年的五月", None), ("birth_ym", "我九一年生人，五月", None),
     ("birth_ym", "1991年5月", "1991-05"), ("area_text", "西溪路那边", None),
     ("area_text", "住在留下街道", "留下街道"), ("area_text", "靠三墩镇这边", "三墩镇"),
     ("job_type", "全职吧", "fulltime"), ("job_type", "兼职随便都行", "parttime"),
     ("has_ebike", "有辆小电驴", True), ("has_ebike", "车子还在买", None),
     ("start_text", "过两天就能来", None), ("start_text", "明天", "明天"),
     ("start_text", "下周一", "下周一"), ("experience_text", "跑过三年美团", None),
     ("experience_text", "干过两年外卖", "2年配送经验"),
     ("experience_text", "没干过", "无经验"),
     ("birth_ym", "２００１年３月", "2001-03"), ("has_ebike", "有电动车", True)]


def main():
    ok = tot = 0
    for f, u, want in C:
        got = slots.extract(u, f)
        if want is None:
            print("%-16s %-14s got=%-14s (不要求命中)" % (f, u, got))
            continue
        tot += 1
        good = got == want
        ok += good
        print("%-16s %-14s want=%-12s got=%-12s %s" % (f, u, want, got, "OK" if good else "MISS"))
    acc = 100.0 * ok / max(1, tot)
    print("\n留出集命中率: %d/%d = %.1f%%" % (ok, tot, acc))
    return 0 if acc >= 85 else 1


if __name__ == "__main__":
    sys.exit(main())
