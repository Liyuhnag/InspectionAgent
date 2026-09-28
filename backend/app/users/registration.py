# -*- coding: utf-8 -*-
"""注册用户。验证码写入 Redis 和日志，核对正确后才落库。"""

import logging
import secrets

from redis import Redis
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.users.password import Password
from app.users.user_model import User

logger = logging.getLogger(__name__)
_CODE_TTL_SECONDS = 300


def verification_code_key(username: str) -> str:
    """验证码在 Redis 中的键。"""
    return f"register:code:{username}"


class UsernameAlreadyExists(Exception):
    """用户名已经注册。"""


class InvalidVerificationCode(Exception):
    """验证码和该用户名当前保存的不一致。"""


class Registration:
    """按用户名发送验证码，并在验证码正确时创建用户。"""

    def __init__(self, engine: Engine, codes: Redis) -> None:
        self._engine = engine
        self._codes = codes

    def send_code(self, username: str) -> None:
        """生成验证码写入 Redis，并写入日志。用户名已注册时拒绝。"""
        with Session(self._engine) as session:
            if User.get(session, username) is not None:
                raise UsernameAlreadyExists(username)
        code = f"{secrets.randbelow(1_000_000):06d}"
        self._codes.set(verification_code_key(username), code, ex=_CODE_TTL_SECONDS)
        logger.info("注册验证码 %s %s", username, code)

    def register(self, username: str, password: str, code: str) -> None:
        """验证码正确后写入用户。验证码错误或用户名已存在时拒绝，不改已有记录。"""
        if self._codes.get(verification_code_key(username)) != code:
            raise InvalidVerificationCode(username)
        sealed = Password.encrypt(password)
        with Session(self._engine) as session:
            try:
                User.create(
                    session,
                    username=username,
                    salt=sealed.salt,
                    password_hash=sealed.password_hash,
                )
            except IntegrityError as error:
                raise UsernameAlreadyExists(username) from error
        self._codes.delete(verification_code_key(username))
