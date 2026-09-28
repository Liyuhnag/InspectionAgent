# -*- coding: utf-8 -*-
"""用户表。"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from app.db.crud_model import CrudModel


class User(CrudModel):
    """已注册用户。用户名是主键。"""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), primary_key=True)
    salt: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
