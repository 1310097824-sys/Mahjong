from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base, build_engine_options, ensure_mysql_database
from app.models import GameRecord


def copy_record(record: GameRecord) -> dict:
    return {
        "id": record.id,
        "player_name": record.player_name,
        "mode": record.mode,
        "round_length": record.round_length,
        "status": record.status,
        "summary_json": record.summary_json,
        "state_json": record.state_json,
        "action_log_json": record.action_log_json,
        "snapshots_json": record.snapshots_json,
        "result_json": record.result_json,
        "notes": record.notes,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def load_sqlite_records(sqlite_url: str) -> list[GameRecord]:
    sqlite_engine = create_engine(sqlite_url, future=True)
    sqlite_session = sessionmaker(bind=sqlite_engine, autoflush=False, expire_on_commit=False, future=True)
    try:
        with sqlite_session() as session:
            return list(session.scalars(select(GameRecord)))
    finally:
        sqlite_engine.dispose()


def upsert_mysql_records(records: Iterable[GameRecord]) -> tuple[int, int]:
    ensure_mysql_database()
    mysql_engine = create_engine(settings.database_url, **build_engine_options(settings.database_url))
    mysql_session = sessionmaker(bind=mysql_engine, autoflush=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=mysql_engine)

    inserted = 0
    updated = 0
    try:
        with mysql_session() as session:
            for record in records:
                payload = copy_record(record)
                existing = session.get(GameRecord, record.id)
                if existing is None:
                    session.add(GameRecord(**payload))
                    inserted += 1
                    continue

                for key, value in payload.items():
                    setattr(existing, key, value)
                updated += 1

            session.commit()
    finally:
        mysql_engine.dispose()

    return inserted, updated


def main() -> None:
    if not settings.database_url.startswith("mysql+pymysql://"):
        raise RuntimeError(f"当前 DATABASE_URL 不是 MySQL: {settings.database_url}")

    records = load_sqlite_records(settings.legacy_sqlite_url)
    inserted, updated = upsert_mysql_records(records)
    print(
        f"SQLite -> MySQL 迁移完成，共 {len(records)} 条记录，"
        f"新增 {inserted} 条，更新 {updated} 条。"
    )


if __name__ == "__main__":
    main()
