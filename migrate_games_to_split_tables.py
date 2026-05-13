"""把旧版 `games` 单表 JSON 数据迁移到拆分表。

运行方式：

    python migrate_games_to_split_tables.py

脚本会先创建缺失的新表和索引，然后逐条读取旧 `games.state_json`，复用
`GameStore.save_game()` 写入拆分表。写入成功后，旧 `games` 行里的大 JSON 会被
压缩为空对象/数组，后续历史列表和统计不再搬运 MB 级状态。
"""

from __future__ import annotations

from sqlalchemy import desc, select

from app.db import SessionLocal, init_db
from app.models import GameRecord, GameStateRecord
from app.store import GameStore


def migrate_games_to_split_tables() -> dict[str, int]:
    init_db()
    store = GameStore()
    migrated = 0
    skipped = 0
    already_split = 0
    compacted = 0

    with SessionLocal() as session:
        game_ids = list(session.scalars(select(GameRecord.id).order_by(desc(GameRecord.updated_at))))

    for game_id in game_ids:
        should_count_as_compacted = False
        with SessionLocal() as session:
            existing_state = session.get(GameStateRecord, game_id)
            record = session.get(GameRecord, game_id)
            if record is None:
                skipped += 1
                continue
            if existing_state is not None and existing_state.state_json:
                state = existing_state.state_json
                if not isinstance(state, dict) or not state.get("action_log") and not state.get("snapshots"):
                    already_split += 1
                    continue
                should_count_as_compacted = True
            else:
                state = record.state_json
            if not isinstance(state, dict) or not state:
                skipped += 1
                continue

        store.save_game(state)
        if should_count_as_compacted:
            compacted += 1
        else:
            migrated += 1

    return {"migrated": migrated, "compacted": compacted, "already_split": already_split, "skipped": skipped}


def main() -> None:
    result = migrate_games_to_split_tables()
    print(
        "拆表迁移完成："
        f"迁移 {result['migrated']} 局，"
        f"压缩 {result['compacted']} 局，"
        f"已拆分 {result['already_split']} 局，"
        f"跳过 {result['skipped']} 局。"
    )


if __name__ == "__main__":
    main()
