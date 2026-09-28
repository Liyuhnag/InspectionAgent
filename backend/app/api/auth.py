# -*- coding: utf-8 -*-
"""默认鉴权。公开接口写在排除名单里。"""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp
from starlette.types import Receive
from starlette.types import Scope
from starlette.types import Send

from app.users.login import InvalidSession
from app.users.login import Login

TOKEN_HEADER = "satoken"
PUBLIC_ROUTES = frozenset(
    {
        ("POST", "/verification-codes"),
        ("POST", "/users"),
        ("POST", "/session"),
        ("DELETE", "/session"),
    }
)


def is_public(method: str, path: str) -> bool:
    """注册、发送验证码、登录和退出不鉴权。文档和预检也不鉴权。"""
    if method == "OPTIONS":
        return True
    if path == "/openapi.json" or path == "/redoc" or path.startswith("/docs"):
        return True
    return (method, path) in PUBLIC_ROUTES


class AuthMiddleware:
    """除排除名单外，先用 satoken 解析当前用户。"""

    def __init__(self, app: ASGIApp, login: Login) -> None:
        self._app = app
        self._login = login

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """公开请求直接进入接口。其余请求先鉴权，用户名放进请求状态。"""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        method = scope.get("method", "")
        path = scope.get("path", "")
        if not isinstance(method, str) or not isinstance(path, str) or is_public(method, path):
            await self._app(scope, receive, send)
            return
        try:
            username = self._login.current_username(_header(scope, TOKEN_HEADER))
        except InvalidSession:
            response = JSONResponse(status_code=401, content={"detail": "未登录"})
            await response(scope, receive, send)
            return
        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            state["username"] = username
        await self._app(scope, receive, send)


def _header(scope: Scope, name: str) -> str:
    """读取单个请求头。没有时返回空字符串。"""
    raw_headers = scope.get("headers", [])
    if not isinstance(raw_headers, list):
        return ""
    target = name.lower().encode("latin-1")
    for item in raw_headers:
        if not isinstance(item, tuple) or len(item) != 2:
            continue
        key, value = item
        if key == target and isinstance(value, bytes):
            return value.decode("latin-1")
    return ""
