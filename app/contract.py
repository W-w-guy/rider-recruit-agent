# -*- coding: utf-8 -*-
"""共用接口契约 v1 的模型（只落本任务用得到的那部分）。"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

JOB = Literal["fulltime", "parttime", "undecided"]
STATUS = Literal["new", "collecting", "complete", "booked", "interviewed",
                 "hired", "rejected", "handoff"]
ACTION = Literal["show_stations", "booking_confirmed", "handoff", "end_minor"]


class Candidate(BaseModel):
    id: str
    name_token: Optional[str] = None
    phone_token: Optional[str] = None
    birth_ym: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}$")
    area_text: Optional[str] = None
    job_type: Optional[JOB] = None
    has_ebike: Optional[bool] = None
    start_text: Optional[str] = None
    experience_text: Optional[str] = None
    health_cert: Literal["none", "holding", "processing", "unknown"] = "unknown"
    source_channel: str = "agent_chat"
    station_id: Optional[str] = None
    status: STATUS = "collecting"
    consent_version: Optional[str] = None
    consent_at: Optional[str] = None
    retention_until: Optional[str] = None
    created_at: str
    updated_at: str


class Progress(BaseModel):
    done: int
    total: int
    fields: List[str]


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    reply: str
    quick_replies: List[str] = []
    progress: Progress
    actions: List[ACTION] = []
    citations: List[dict] = []
    degraded: bool = False
    tokens: dict = {}
    ms: float = 0.0
    # ★ 收齐 7 项时一并返回（契约只说 actions 里有 show_stations，
    #   但不给站点/候选人摘要，前端还得再发两次请求 —— 这里顺带给出，
    #   多的字段不影响契约兼容）。原先漏声明会被 response_model 静默剥掉，
    #   测试才会 KeyError: 'candidate'。
    candidate: Optional[dict] = None
    stations: Optional[List[dict]] = None


class SessionOut(BaseModel):
    session_id: str


class Station(BaseModel):
    id: str
    name: str
    lat: float
    lng: float
    open_quota: int
