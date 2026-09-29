# -*- coding: utf-8 -*-
"""按显式目标创建 MySQL 数据库并初始化应用表。"""

import argparse

from sqlalchemy import create_engine
from sqlalchemy import URL
from sqlalchemy.schema import CreateSchema

from app.chats.chat_session import ChatSession
from app.chats.trace import Trace
from app.config.settings import AppSettings
from app.config.settings import DEV_CONFIG
from app.config.settings import MysqlSettings
from app.db.mysql import mysql_engine
from app.users.user_model import User


class DatabaseCreator:
    """从开发配置读取连接信息，幂等创建数据库及其应用表。"""

    def __init__(self, settings: AppSettings) -> None:
        """保存开发和测试数据库的连接配置。"""
        self._settings = settings

    def create(self, target: str) -> str:
        """创建所选数据库并初始化当前项目的数据表。"""
        mysql = self._target_settings(target)
        self._create_database(mysql)
        engine = mysql_engine(mysql)
        try:
            User.create_table(engine)
            ChatSession.create_table(engine)
            Trace.create_table(engine)
        finally:
            engine.dispose()
        return mysql.database

    def _target_settings(self, target: str) -> MysqlSettings:
        """按显式目标返回开发库或测试库连接参数。"""
        if target == "development":
            return self._settings.mysql
        if target == "test":
            return self._settings.test_mysql()
        raise ValueError(f"不支持的数据库目标：{target}")

    def _create_database(self, mysql: MysqlSettings) -> None:
        """通过不指定默认数据库的连接幂等创建目标数据库。"""
        url = URL.create(
            drivername="mysql+pymysql",
            username=mysql.user,
            password=mysql.password,
            host=mysql.host,
            port=mysql.port,
            query={"charset": "utf8mb4"},
        )
        engine = create_engine(url)
        try:
            with engine.begin() as connection:
                connection.execute(CreateSchema(mysql.database, if_not_exists=True))
        finally:
            engine.dispose()


def _arguments() -> argparse.Namespace:
    """读取要创建的数据库目标，避免默认操作开发库。"""
    parser = argparse.ArgumentParser(description="创建项目 MySQL 数据库和应用表")
    parser.add_argument(
        "--target",
        choices=("development", "test"),
        required=True,
        help="明确选择 development 或 test",
    )
    return parser.parse_args()


def main() -> None:
    """读取本地配置并执行指定目标的数据库初始化。"""
    arguments = _arguments()
    creator = DatabaseCreator(AppSettings.load(DEV_CONFIG))
    database = creator.create(arguments.target)
    label = "开发" if arguments.target == "development" else "测试"
    print(f"{label}数据库及应用表已就绪：{database}")


if __name__ == "__main__":
    main()
