# -*- coding: utf-8 -*-
"""契约：错误体统一 {code, message}。"""
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, code, message, status=400):
        self.code = code
        self.message = message
        self.status = status


def install(app):
    @app.exception_handler(ApiError)
    async def _h(req, exc: ApiError):
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=exc.status)
