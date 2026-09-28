# -*- coding: utf-8 -*-
"""用用户名签发和解析 JWT。"""

from datetime import datetime
from datetime import timedelta
from datetime import timezone

import jwt


class JwtError(Exception):
    """令牌签名不对或已经过期。"""


class JwtToken:
    """用户名令牌。载荷里只有用户名和过期时间。"""

    def __init__(self, secret: str, expires_minutes: int) -> None:
        """保存签名密钥和有效分钟数。"""
        self._secret = secret
        self._expires_minutes = expires_minutes

    def sign(self, username: str) -> str:
        """用用户名签发令牌。"""
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self._expires_minutes)
        token = jwt.encode(
            {"sub": username, "exp": expires_at},
            self._secret,
            algorithm="HS256",
        )
        return token

    def parse(self, token: str) -> str:
        """解析令牌，只返回用户名。签名不对或过期时失败。"""
        try:
            payload = jwt.decode(token, self._secret, algorithms=["HS256"])
        except jwt.PyJWTError as error:
            raise JwtError("令牌无效") from error
        username = payload.get("sub")
        if not isinstance(username, str) or not username:
            raise JwtError("令牌无效")
        return username
