# -*- coding: utf-8 -*-
"""登录。核对密码后签发随机会话，当前用户只认 Redis 里的记录。"""

import hashlib
import secrets

from redis import Redis
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.users.password import Password
from app.users.user_model import User

_unknown_password: Password | None = None


class InvalidCredentials(Exception):
    """用户名或密码不正确。"""


class InvalidSession(Exception):
    """登录态缺失、已过期，或用户已不存在。"""


def session_key(token: str) -> str:
    """用 token 的哈希做 Redis 键，不保存原文。"""
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"session:{digest}"


class Login:
    """按用户名和密码建立会话，并解析当前用户。"""

    def __init__(self, engine: Engine, sessions: Redis, ttl_seconds: int) -> None:
        self._engine = engine
        self._sessions = sessions
        self._ttl_seconds = ttl_seconds

    def authenticate(self, username: str, password: str) -> str:
        """密码正确时返回 token。用户不存在或密码错误时拒绝，两种失败没有区别。"""
        with Session(self._engine) as session:
            row = User.get(session, username)
        if row is None:
            _burn_unknown_password(password)
            raise InvalidCredentials()
        sealed = Password(salt=row.salt, password_hash=row.password_hash)
        if not sealed.matches(password):
            raise InvalidCredentials()
        token = secrets.token_urlsafe(32)
        self._sessions.set(session_key(token), username, ex=self._ttl_seconds)
        return token

    def current_username(self, token: str) -> str:
        """从 Redis 得到用户名，并把过期时间重新设满。记录不存在或用户已删除时拒绝。"""
        if not token:
            raise InvalidSession()
        key = session_key(token)
        username = self._sessions.get(key)
        if not isinstance(username, str) or not username:
            raise InvalidSession()
        with Session(self._engine) as session:
            if User.get(session, username) is None:
                self._sessions.delete(key)
                raise InvalidSession()
        self._sessions.expire(key, self._ttl_seconds)
        return username

    def logout(self, token: str) -> None:
        """删掉这条会话。没有 token 时什么都不做。"""
        if not token:
            return
        self._sessions.delete(session_key(token))


def _burn_unknown_password(password: str) -> None:
    """用户不存在时仍做一次核对，避免用响应时间区分用户名是否存在。"""
    global _unknown_password
    if _unknown_password is None:
        _unknown_password = Password.encrypt("unused")
    _unknown_password.matches(password)
