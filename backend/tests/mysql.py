# -*- coding: utf-8 -*-
"""测试连接 dev.yaml 里的测试库。"""

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.config.settings import AppSettings
from app.config.settings import ConfigError
from app.config.settings import MysqlSettings
from app.config.settings import DEV_CONFIG
from app.db.engine import mysql_engine


def open_test_database() -> tuple[MysqlSettings, Engine]:
    """打开同一台 MySQL 上的测试库。没有配置或连不上时跳过当前用例。"""
    if not DEV_CONFIG.is_file():
        pytest.skip("没有开发配置")
    try:
        settings = AppSettings.load(DEV_CONFIG).test_mysql()
        engine = mysql_engine(settings)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except ConfigError:
        pytest.skip("测试环境配置不完整")
    except Exception:
        # 测试库连不上时跳过，不把环境问题当成用例失败。
        pytest.skip("测试库不可用")
    return settings, engine
