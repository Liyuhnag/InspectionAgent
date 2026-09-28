# -*- coding: utf-8 -*-
from pathlib import Path

import pytest

from app.config.settings import ConfigError
from app.config.settings import JwtSettings
from app.config.settings import MysqlSettings


def test_缺少_mysql_字段时读取失败(tmp_path: Path) -> None:
    """缺字段的 MySQL 配置不能被当成可用连接。"""
    path = tmp_path / "mysql.yaml"
    path.write_text("host: 127.0.0.1\nport: 3306\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        MysqlSettings.load(path)



def test_mysql_文件不存在时读取失败(tmp_path: Path) -> None:
    """配置文件不存在时读取失败。"""
    with pytest.raises(ConfigError):
        MysqlSettings.load(tmp_path / "missing.yaml")



def test_可以读取完整的_mysql_配置(tmp_path: Path) -> None:
    """完整的 MySQL 配置能读出每个字段。"""
    path = tmp_path / "mysql.yaml"
    path.write_text(
        "host: 127.0.0.1\nport: 3306\ndatabase: inspection\nuser: root\npassword: secret\n",
        encoding="utf-8",
    )
    settings = MysqlSettings.load(path)
    assert settings.host == "127.0.0.1"
    assert settings.port == 3306
    assert settings.database == "inspection"
    assert settings.user == "root"
    assert settings.password == "secret"



def test_缺少_jwt_字段时读取失败(tmp_path: Path) -> None:
    """缺字段的 JWT 配置不能被当成可用签名参数。"""
    path = tmp_path / "jwt.yaml"
    path.write_text("secret: key\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        JwtSettings.load(path)



def test_可以读取完整的_jwt_配置(tmp_path: Path) -> None:
    """完整的 JWT 配置能读出密钥和过期时间。"""
    path = tmp_path / "jwt.yaml"
    path.write_text("secret: key\nexpires_minutes: 60\n", encoding="utf-8")
    settings = JwtSettings.load(path)
    assert settings.secret == "key"
    assert settings.expires_minutes == 60
