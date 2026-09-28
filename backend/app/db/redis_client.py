# -*- coding: utf-8 -*-
"""按 Redis 配置创建客户端。"""

from redis import Redis

from app.config.settings import RedisSettings


def redis_client(settings: RedisSettings) -> Redis:
    """按连接参数创建客户端。创建时不访问 Redis。"""
    password = settings.password or None
    return Redis(
        host=settings.host,
        port=settings.port,
        password=password,
        db=settings.database,
        decode_responses=True,
    )
