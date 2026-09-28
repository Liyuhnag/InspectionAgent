# -*- coding: utf-8 -*-
"""读取开发配置。测试和开发共用同一台 MySQL，只是 database 不同。"""

from pathlib import Path

import yaml

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEV_CONFIG = _BACKEND_ROOT / "config" / "dev.yaml"


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


class JwtSettings:
    """JWT 签名参数。"""

    def __init__(self, secret: str, expires_minutes: int) -> None:
        """保存已经校验过的签名参数。"""
        self.secret = secret
        self.expires_minutes = expires_minutes


class AppSettings:
    """开发配置。数据库和 JWT 写在同一个文件里。"""

    def __init__(self, mysql: MysqlSettings, test_database: str, jwt: JwtSettings) -> None:
        """保存开发库、测试库名和 JWT 参数。"""
        self.mysql = mysql
        self.jwt = jwt
        self._test_database = test_database

    def test_mysql(self) -> MysqlSettings:
        """同一台 MySQL 上的测试库。主机、端口、账号与开发库相同。"""
        return MysqlSettings(
            host=self.mysql.host,
            port=self.mysql.port,
            database=self._test_database,
            user=self.mysql.user,
            password=self.mysql.password,
        )

    @classmethod
    def load(cls, path: Path) -> "AppSettings":
        """读取开发配置。缺文件或缺字段时失败。"""
        data = _read_mapping(path)
        mysql_data = _section(data, "mysql")
        jwt_data = _section(data, "jwt")
        _require(mysql_data, ("host", "port", "user", "password", "database", "test_database"))
        _require(jwt_data, ("secret", "expires_minutes"))
        return cls(
            mysql=MysqlSettings(
                host=str(mysql_data["host"]),
                port=int(mysql_data["port"]),
                database=str(mysql_data["database"]),
                user=str(mysql_data["user"]),
                password=str(mysql_data["password"]),
            ),
            test_database=str(mysql_data["test_database"]),
            jwt=JwtSettings(
                secret=str(jwt_data["secret"]),
                expires_minutes=int(jwt_data["expires_minutes"]),
            ),
        )


def _read_mapping(path: Path) -> dict:
    """读出 YAML 映射。文件不存在或内容不是映射时失败。"""
    if not path.is_file():
        raise ConfigError(f"配置文件不存在：{path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ConfigError(f"配置文件内容无效：{path}")
    return loaded


def _section(data: dict, name: str) -> dict:
    """取出命名配置节。没有这一节时失败。"""
    section = data.get(name)
    if not isinstance(section, dict):
        raise ConfigError(f"缺少配置：{name}")
    return section


def _require(data: dict, names: tuple) -> None:
    """确认每个字段都有非空值。"""
    for name in names:
        if name not in data or data[name] in ("", None):
            raise ConfigError(f"缺少配置字段：{name}")
