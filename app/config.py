# -*- coding: utf-8 -*-
"""配置：全部走环境变量，默认值保证「不配任何东西也能起」。"""
import os


def env(k, d=None):
    v = os.environ.get(k)
    return d if v in (None, "") else v


class Config(object):
    policy_dir = env("POLICY_DIR", "policy")
    database_url = env("DATABASE_URL", "")          # 空 = 内存后端（评测/CI 用）
    redis_url = env("REDIS_URL", "")
    model_base_url = env("MODEL_BASE_URL", "")      # 空 = mock 模型
    model_name = env("MODEL_NAME", "mock-rule-v1")
    model_api_key = env("MODEL_API_KEY", "")        # 客户自带；不落盘、不进日志
    extract_llm = env("EXTRACT_LLM", "auto")        # auto=配了key就用，off=强制规则
    model_timeout_ms = int(env("MODEL_TIMEOUT_MS", "3000"))
    model_fallback = env("MODEL_FALLBACK", "form")  # form = 降级为表单式问答
    vault_url = env("VAULT_URL", "")                # 空 = 内置 mock（任务5）
    station_url = env("STATION_URL", "")            # 空 = 内置 mock（任务3）
    webhook_secret = env("WEBHOOK_SECRET", "dev-secret")
    jwt_secret = env("JWT_SECRET", "dev-jwt-secret")
    retention_days = int(env("RETENTION_DAYS", "90"))


CFG = Config()
