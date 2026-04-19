from __future__ import annotations

import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def build_engine_options(database_url: str | URL) -> dict:
    url = make_url(database_url)
    options: dict = {"future": True}
    if url.get_backend_name() == "mysql":
        options.update(
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    return options


def ensure_mysql_database() -> None:
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
    import app.models  # noqa: F401

    ensure_mysql_database()
    Base.metadata.create_all(bind=engine)
