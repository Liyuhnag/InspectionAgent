# -*- coding: utf-8 -*-
"""应用入口。启动时建用户表，并挂上注册和登录接口。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from sqlalchemy.engine import Engine

from app.api.routes.register import register_router
from app.api.routes.session import session_router
from app.config.settings import DEV_CONFIG
from app.config.settings import AppSettings
from app.db.mysql import mysql_engine
from app.db.redis_client import redis_client
from app.users.login import Login
from app.users.registration import Registration
from app.users.user_model import User

DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def create_app(
    engine: Engine | None = None,
    codes: Redis | None = None,
    session_ttl_seconds: int | None = None,
) -> FastAPI:
    """创建应用。未传入连接时使用开发库。"""
    settings = None
    if engine is None or codes is None or session_ttl_seconds is None:
        settings = AppSettings.load(DEV_CONFIG)
    if engine is None:
        engine = mysql_engine(settings.mysql)
    if codes is None:
        codes = redis_client(settings.redis)
    if session_ttl_seconds is None:
        session_ttl_seconds = settings.jwt.expires_minutes * 60
    User.create_table(engine)
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_ORIGINS),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "satoken"],
    )
    app.include_router(register_router(Registration(engine, codes)))
    app.include_router(session_router(Login(engine, codes, session_ttl_seconds)))
    return app
