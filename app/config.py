"""后端运行配置入口。

这个模块只负责“把环境变量整理成系统可直接使用的配置对象”，不包含任何
业务规则。后端启动时会先读取根目录 `.env`，再构造 MySQL 连接串；如果用户
显式设置 `DATABASE_URL`，则以完整连接串为准。这样可以同时支持一键脚本、
手动启动和未来部署到服务器时的环境变量注入。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus


def load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()


def build_default_database_url() -> str:
    explicit_database_url = os.getenv("DATABASE_URL")
    if explicit_database_url:
        return explicit_database_url

    mysql_host = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port = os.getenv("MYSQL_PORT", "3306")
    mysql_user = os.getenv("MYSQL_USER", "root")
    mysql_password = os.getenv("MYSQL_PASSWORD", "")
    mysql_database = os.getenv("MYSQL_DATABASE", "mahjong")
    mysql_charset = os.getenv("MYSQL_CHARSET", "utf8mb4")

    encoded_user = quote_plus(mysql_user)
    encoded_password = quote_plus(mysql_password)
    auth_segment = encoded_user if not mysql_password else f"{encoded_user}:{encoded_password}"
    return f"mysql+pymysql://{auth_segment}@{mysql_host}:{mysql_port}/{mysql_database}?charset={mysql_charset}"


@dataclass(slots=True)
class Settings:
    app_name: str = "单人立直麻将"
    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "root")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "mahjong")
    mysql_charset: str = os.getenv("MYSQL_CHARSET", "utf8mb4")
    legacy_sqlite_url: str = os.getenv("LEGACY_SQLITE_DATABASE_URL", "sqlite:///./mahjong.db")
    database_url: str = field(default_factory=build_default_database_url)
    secret_key: str = os.getenv("SECRET_KEY", "mahjong-dev-secret")
    default_4p_points: int = 25000
    default_3p_points: int = 35000
    replay_tail_limit: int = 30


settings = Settings()
