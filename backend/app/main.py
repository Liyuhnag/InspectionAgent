# -*- coding: utf-8 -*-
"""应用入口。启动时创建用户、聊天会话、Trace 和 Span 表，清理残留的 running 记录，并挂上业务接口。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from sqlalchemy.engine import Engine

from app.api.auth import AuthMiddleware
from app.api.routes.chat_sessions import chat_sessions_router
from app.api.routes.register import register_router
from app.api.routes.session import session_router
from app.api.routes.traces import traces_router
from app.chats.chat_reply import ChatReplyService
from app.chats.chat_session import ChatSession
from app.chats.span import Span
from app.chats.trace import Trace
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
    ChatSession.create_table(engine)
    Trace.create_table(engine)
    Span.create_table(engine)
    login = Login(engine, codes, session_ttl_seconds)
    replies = ChatReplyService(engine)
    replies.fail_stale_replies()
    app = FastAPI()
    app.add_middleware(AuthMiddleware, login=login)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_ORIGINS),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "satoken"],
    )
    app.include_router(register_router(Registration(engine, codes)))
    app.include_router(session_router(login))
    app.include_router(chat_sessions_router(engine))
    app.include_router(traces_router(engine, replies))
    return app
