"""数据库连接和初始化层。

系统当前以 MySQL 作为主数据库，通过 SQLAlchemy ORM 读写。这里集中处理
连接池参数、自动建库和 Session 工厂，避免 API 层或规则引擎直接关心数据库
驱动细节。`ensure_mysql_database()` 会在应用启动时自动创建 `mahjong` 数据库，
因此首次启动只要 MySQL 服务和账号密码正确即可。
"""

from __future__ import annotations

import re

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的声明基类。"""

    pass


def build_engine_options(database_url: str | URL) -> dict:
    """根据数据库类型生成 SQLAlchemy engine 参数。

    MySQL 连接容易遇到空闲连接断开，所以开启 `pool_pre_ping` 和连接回收；
    其他数据库保持最小配置，方便测试或临时迁移。
    """

    url = make_url(database_url)
    options: dict = {"future": True}
    if url.get_backend_name() == "mysql":
        options.update(
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    return options


def ensure_mysql_database() -> None:
    """在正式连接业务库前，先用无库连接创建 MySQL 数据库。"""

    url = make_url(settings.database_url)
    if url.get_backend_name() != "mysql" or not url.database:
        return

    if not re.fullmatch(r"[0-9A-Za-z_]+", url.database):
        raise ValueError(f"不支持的 MySQL 数据库名: {url.database}")

    bootstrap_url = url.set(database="")
    bootstrap_engine = create_engine(bootstrap_url, **build_engine_options(bootstrap_url))
    try:
        with bootstrap_engine.connect() as connection:
            autocommit_connection = connection.execution_options(isolation_level="AUTOCOMMIT")
            autocommit_connection.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{url.database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    finally:
        bootstrap_engine.dispose()


engine = create_engine(settings.database_url, **build_engine_options(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """导入模型并创建缺失的数据表。"""

    import app.models  # noqa: F401

    ensure_mysql_database()
    Base.metadata.create_all(bind=engine)
    ensure_runtime_indexes()


def ensure_runtime_indexes() -> None:
    """为旧库补上 create_all 不会自动添加的查询索引。

    SQLAlchemy 的 `create_all()` 只会创建缺失表，不会修改已存在的 `games` 表。
    当前历史列表和统计都依赖 `updated_at/status/player_name`，旧库没有这些组合索引时，
    MySQL 可能在排序大 JSON 行时触发 sort buffer 压力。
    """

    inspector = inspect(engine)
    if "games" not in inspector.get_table_names():
        return

    existing_names = {item["name"] for item in inspector.get_indexes("games")}
    index_sql = {
        "ix_games_updated_at": "CREATE INDEX ix_games_updated_at ON games (updated_at)",
        "ix_games_status_updated_at": "CREATE INDEX ix_games_status_updated_at ON games (status, updated_at)",
        "ix_games_player_status_updated_at": (
            "CREATE INDEX ix_games_player_status_updated_at ON games (player_name, status, updated_at)"
        ),
    }
    with engine.begin() as connection:
        for index_name, sql in index_sql.items():
            if index_name not in existing_names:
                connection.execute(text(sql))
