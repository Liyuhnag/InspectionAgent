# -*- coding: utf-8 -*-
from pathlib import Path

import pytest

from app.config.settings import AppSettings
from app.config.settings import ConfigError


def _write(path: Path, text: str) -> None:
    """把一段环境配置写到临时文件。"""
    path.write_text(text, encoding="utf-8")


def test_缺少数据库字段时读取失败(tmp_path: Path) -> None:
    """同一份配置里，数据库缺字段就不能使用。"""
    path = tmp_path / "dev.yaml"
    _write(path, "mysql:\n  host: 127.0.0.1\n  port: 3306\njwt:\n  secret: key\n  expires_minutes: 60\n")
    with pytest.raises(ConfigError):
        AppSettings.load(path)


def test_缺少_jwt_字段时读取失败(tmp_path: Path) -> None:
    """同一份配置里，JWT 缺字段就不能使用。"""
    path = tmp_path / "dev.yaml"
    _write(
        path,
        "mysql:\n"
        "  host: 127.0.0.1\n"
        "  port: 3306\n"
        "  user: root\n"
        "  password: secret\n"
        "  database: inspection\n"
        "  test_database: inspection_test\n"
        "jwt:\n"
        "  secret: key\n",
    )
    with pytest.raises(ConfigError):
        AppSettings.load(path)


def test_配置文件不存在时读取失败(tmp_path: Path) -> None:
    """配置文件不存在时读取失败。"""
    with pytest.raises(ConfigError):
        AppSettings.load(tmp_path / "missing.yaml")


def test_同一台_mysql_使用不同的库(tmp_path: Path) -> None:
    """开发和测试共用主机、端口和账号，只是 database 不同。"""
    path = tmp_path / "dev.yaml"
    _write(
        path,
        "mysql:\n"
        "  host: 127.0.0.1\n"
        "  port: 3306\n"
        "  user: root\n"
        "  password: secret\n"
        "  database: inspection\n"
        "  test_database: inspection_test\n"
        "jwt:\n"
        "  secret: key\n"
        "  expires_minutes: 60\n",
    )
    settings = AppSettings.load(path)
    test_mysql = settings.test_mysql()
    assert settings.mysql.database == "inspection"
    assert test_mysql.database == "inspection_test"
    assert test_mysql.host == settings.mysql.host
    assert test_mysql.port == settings.mysql.port
    assert test_mysql.user == settings.mysql.user
    assert test_mysql.password == settings.mysql.password
    assert settings.jwt.secret == "key"
    assert settings.jwt.expires_minutes == 60
