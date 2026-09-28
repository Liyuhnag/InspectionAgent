# -*- coding: utf-8 -*-
"""应用入口。启动时建用户表，并挂上注册接口。"""

from fastapi import FastAPI
from redis import Redis
from sqlalchemy.engine import Engine

from app.api.routes.register import register_router
from app.config.settings import DEV_CONFIG
from app.config.settings import AppSettings
from app.db.mysql import mysql_engine
from app.db.redis_client import redis_client
from app.users.registration import Registration
from app.users.user_model import User


def create_app(engine: Engine | None = None, codes: Redis | None = None) -> FastAPI:
    """创建应用。未传入连接时使用开发库。"""
    settings = None
    if engine is None or codes is None:
        settings = AppSettings.load(DEV_CONFIG)
    if engine is None:
        engine = mysql_engine(settings.mysql)
    if codes is None:
        codes = redis_client(settings.redis)
    User.create_table(engine)
    app = FastAPI()
    app.include_router(register_router(Registration(engine, codes)))
    return app
