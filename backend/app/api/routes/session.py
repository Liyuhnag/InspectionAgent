# -*- coding: utf-8 -*-
"""登录接口。只校验入参并调用用户模块。token 只在登录响应正文里出现一次。"""

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel
from pydantic import field_validator

from app.users.login import InvalidCredentials
from app.users.login import InvalidSession
from app.users.login import Login

TOKEN_HEADER = "satoken"


class LoginBody(BaseModel):
    """登录入参。"""

    username: str
    password: str

    @field_validator("username", "password")
    @classmethod
    def value_present(cls, value: str) -> str:
        """去掉空白，空字段拒绝。"""
        stripped = value.strip()
        if not stripped:
            raise ValueError("不能为空")
        return stripped


def session_router(login: Login) -> APIRouter:
    """挂上登录、退出和当前用户。"""
    router = APIRouter()

    @router.post("/session")
    def login_user(body: LoginBody) -> dict[str, str]:
        """密码正确时返回 token。"""
        try:
            token = login.authenticate(body.username, body.password)
        except InvalidCredentials:
            raise HTTPException(status_code=401, detail="用户名或密码不正确")
        return {"message": "已登录", "token": token}

    @router.delete("/session")
    def logout(request: Request) -> dict[str, str]:
        """按请求头里的 token 删除会话。"""
        login.logout(request.headers.get(TOKEN_HEADER, ""))
        return {"message": "已退出"}

    @router.get("/session")
    def current_user(request: Request) -> dict[str, str]:
        """用户名只来自 satoken 头对应的会话。"""
        token = request.headers.get(TOKEN_HEADER, "")
        try:
            username = login.current_username(token)
        except InvalidSession:
            raise HTTPException(status_code=401, detail="未登录")
        return {"username": username}

    return router
