# -*- coding: utf-8 -*-
"""测试连接 dev.yaml 里的测试 Redis。"""

import pytest
from redis import Redis

from app.config.settings import DEV_CONFIG
from app.config.settings import AppSettings
from app.config.settings import ConfigError
from app.db.redis_client import redis_client


def open_test_redis() -> Redis:
    """打开同一台 Redis 上的测试库。没有配置或连不上时跳过当前用例。"""
    if not DEV_CONFIG.is_file():
        pytest.skip("没有开发配置")
    try:
        settings = AppSettings.load(DEV_CONFIG).test_redis()
        client = redis_client(settings)
        client.ping()
    except ConfigError:
        pytest.skip("测试环境配置不完整")
    except Exception:
        # 测试 Redis 连不上时跳过，不把环境问题当成用例失败。
        pytest.skip("测试 Redis 不可用")
    return client
