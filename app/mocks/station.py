# -*- coding: utf-8 -*-
"""任务 3（站点/预约）的 mock。契约要求「按本契约自己写 mock，不要等别人」。"""
import math

STATIONS = [
    {"id": "st_hz_01", "name": "文一西路站", "lat": 30.2870, "lng": 120.0760, "open_quota": 12},
    {"id": "st_hz_02", "name": "古墩路站", "lat": 30.2960, "lng": 120.0900, "open_quota": 5},
    {"id": "st_hz_03", "name": "三墩镇站", "lat": 30.3120, "lng": 120.0620, "open_quota": 0},
    {"id": "st_hz_04", "name": "西溪路站", "lat": 30.2740, "lng": 120.1150, "open_quota": 8},
]
_BOOK = {}


def _dist(a, b, c, d):
    r = 6371.0
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = p2 - p1, math.radians(d - b)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def query(lat=30.2870, lng=120.0760, limit=3):
    """按距离排序，且只返回还有名额的站点（名额 0 的不推荐）。"""
    rows = []
    for s in STATIONS:
        if s["open_quota"] <= 0:
            continue
        rows.append(dict(s, distance_km=round(_dist(lat, lng, s["lat"], s["lng"]), 2)))
    rows.sort(key=lambda x: x["distance_km"])
    return rows[:limit]


def slots(station_id, day="2026-11-06"):
    return {"station_id": station_id,
            "slots": ["%sT09:00" % day, "%sT10:30" % day, "%sT14:00" % day]}


def book(candidate_id, station_id, slot_start):
    key = (candidate_id, station_id)
    if key in _BOOK:
        return _BOOK[key]          # 幂等：同人同站不重复占名额
    for s in STATIONS:
        if s["id"] == station_id:
            if s["open_quota"] <= 0:
                raise ValueError("quota_exhausted")
            s["open_quota"] -= 1
            break
    else:
        raise ValueError("station_not_found")
    b = {"id": "bk_%d" % (len(_BOOK) + 1), "candidate_id": candidate_id,
         "station_id": station_id, "slot_start": slot_start, "status": "booked"}
    _BOOK[key] = b
    return b


def reset():
    _BOOK.clear()
    for i, q in enumerate([12, 5, 0, 8]):
        STATIONS[i]["open_quota"] = q
