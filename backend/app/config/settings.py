# -*- coding: utf-8 -*-
"""从 YAML 读取 MySQL 和 JWT 配置。"""

from pathlib import Path

import yaml


class ConfigError(Exception):
    """配置文件缺失或字段不完整。"""


class MysqlSettings:
    """MySQL 连接参数。"""

    def __init__(self, host: str, port: int, database: str, user: str, password: str) -> None:
        """保存已经校验过的连接参数。"""
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password

    @classmethod
    def load(cls, path: Path) -> "MysqlSettings":
        """从 YAML 读取连接参数，缺字段时失败。"""
        data = _read_mapping(path)
        _require(data, ("host", "port", "database", "user", "password"))
        return cls(
            host=str(data["host"]),
            port=int(data["port"]),
            database=str(data["database"]),
            user=str(data["user"]),
            password=str(data["password"]),
        )


class JwtSettings:
    """JWT 签名参数。"""

    def __init__(self, secret: str, expires_minutes: int) -> None:
        """保存已经校验过的签名参数。"""
        self.secret = secret
        self.expires_minutes = expires_minutes

    @classmethod
    def load(cls, path: Path) -> "JwtSettings":
        """从 YAML 读取签名参数，缺字段时失败。"""
        data = _read_mapping(path)
        _require(data, ("secret", "expires_minutes"))
        return cls(secret=str(data["secret"]), expires_minutes=int(data["expires_minutes"]))


def _read_mapping(path: Path) -> dict:
    """读出 YAML 映射。文件不存在或内容不是映射时失败。"""
    if not path.is_file():
        raise ConfigError(f"配置文件不存在：{path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ConfigError(f"配置文件内容无效：{path}")
    return loaded


def _require(data: dict, names: tuple) -> None:
    """确认每个字段都有非空值。"""
    for name in names:
        if name not in data or data[name] in ("", None):
            raise ConfigError(f"缺少配置字段：{name}")
