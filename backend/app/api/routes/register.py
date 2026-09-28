# -*- coding: utf-8 -*-
"""注册接口。只校验入参并调用用户模块。"""

from fastapi import APIRouter
from fastapi import HTTPException
from pydantic import BaseModel
from pydantic import field_validator

from app.users.registration import InvalidVerificationCode
from app.users.registration import Registration
from app.users.registration import UsernameAlreadyExists


class SendCodeBody(BaseModel):
    """发送验证码的入参。"""

    username: str

    @field_validator("username")
    @classmethod
    def username_present(cls, value: str) -> str:
        """去掉空白，空用户名拒绝。"""
        stripped = value.strip()
        if not stripped:
            raise ValueError("用户名为空")
        return stripped


class RegisterBody(BaseModel):
    """注册入参。"""

    username: str
    password: str
    code: str

    @field_validator("username", "password", "code")
    @classmethod
    def value_present(cls, value: str) -> str:
        """去掉空白，空字段拒绝。"""
        stripped = value.strip()
        if not stripped:
            raise ValueError("不能为空")
        return stripped


def register_router(registration: Registration) -> APIRouter:
    """挂上发送验证码和注册两个接口。"""
    router = APIRouter()

    @router.post("/verification-codes")
    def send_code(body: SendCodeBody) -> dict[str, str]:
        """发送验证码接口。"""
        try:
            registration.send_code(body.username)
        except UsernameAlreadyExists:
            raise HTTPException(status_code=400, detail="用户名已存在")
        return {"message": "已发送"}

    @router.post("/users")
    def register(body: RegisterBody) -> dict[str, str]:
        """验证码正确时创建用户。"""
        try:
            registration.register(body.username, body.password, body.code)
        except InvalidVerificationCode:
            raise HTTPException(status_code=400, detail="验证码错误")
        except UsernameAlreadyExists:
            raise HTTPException(status_code=400, detail="用户名已存在")
        return {"message": "用户已创建"}

    return router
