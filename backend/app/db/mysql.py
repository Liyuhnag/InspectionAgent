# -*- coding: utf-8 -*-
"""按 MySQL 配置创建 SQLAlchemy 引擎。"""

from sqlalchemy import URL
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config.settings import MysqlSettings


def mysql_engine(settings: MysqlSettings) -> Engine:
    """按连接参数创建引擎。创建时不访问数据库。"""
    url = URL.create(
        drivername="mysql+pymysql",
        username=settings.user,
        password=settings.password,
        host=settings.host,
        port=settings.port,
        database=settings.database,
        query={"charset": "utf8mb4"},
    )
    return create_engine(url)
