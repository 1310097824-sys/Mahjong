"""对局持久化仓库。

`GameStore` 是 API 层和数据库模型之间的薄封装：API 不直接操作 SQLAlchemy
Session，而是通过这里完成保存、读取、删除、回放和玩家统计。这样未来要把
单表 JSON 存储拆成多表牌谱，也只需要优先改这个仓库层。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import Select, delete, desc, func, select

from app.db import SessionLocal
from app.models import (
    GameActionRecord,
    GamePlayerRecord,
    GameRecord,
    GameReplaySnapshotRecord,
    GameResultRecord,
    GameStateRecord,
)


def player_name_aliases(player_name: str) -> set[str]:
    """兼容旧版本默认玩家名，避免统计里“Guest”和“访客”分裂。"""

    normalized = (player_name or "").strip() or "访客"
    aliases = {normalized}
    # 旧版本默认玩家名是 Guest，但前端会显示成“访客”。统计时把两者视为同一个默认玩家。
    if normalized in {"访客", "Guest"}:
        aliases.update({"访客", "Guest"})
    return aliases


def coerce_int(value: Any) -> int | None:
    """把结算 JSON 里的点数/名次安全转换为整数。"""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def compact_runtime_state(game: dict[str, Any]) -> dict[str, Any]:
    """Return a recoverable game state without duplicating replay history.

    `action_log` and `snapshots` are stored in append-only detail tables. Keeping
    them inside `game_states.state_json` as well makes every save rewrite several
    megabytes late in a hand, so the runtime state only keeps lightweight
    placeholders and is hydrated again when a game is loaded.
    """

    state = deepcopy(game)
    state["action_log"] = []
    state["snapshots"] = []
    return state


def hydrate_runtime_state(
    state: dict[str, Any],
    actions: list[dict[str, Any]] | None,
    snapshots: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Rebuild the in-memory game dict from compact state plus detail rows."""

    hydrated = deepcopy(state)
    if actions is not None:
        hydrated["action_log"] = actions
    else:
        hydrated.setdefault("action_log", [])
    if snapshots is not None:
        hydrated["snapshots"] = snapshots
    else:
        hydrated.setdefault("snapshots", [])
    return hydrated


def human_placement_from_summary(summary: dict[str, Any], result: dict[str, Any], aliases: set[str]) -> dict[str, Any] | None:
    """从摘要或结算结果中提取人类玩家的名次与点数。"""

    placements_data = result.get("placements") or summary.get("placements") or []
    if not isinstance(placements_data, list):
        return None

    human_items = [item for item in placements_data if isinstance(item, dict) and item.get("is_human")]
    if not human_items:
        human_items = [
            item
            for item in placements_data
            if isinstance(item, dict) and str(item.get("name", "")).strip() in aliases
        ]
    if not human_items:
        return None

    item = human_items[0]
    placement = coerce_int(item.get("placement"))
    points = coerce_int(item.get("points"))
    if placement is None or points is None:
        return None
    return {"placement": placement, "points": points}


class GameStore:
    """封装所有对 `games` 表的读写操作。"""

    def save_game(self, game: dict[str, Any]) -> None:
        with SessionLocal() as session:
            record = session.get(GameRecord, game["game_id"])
            result_summary = game.get("result_summary") or {}
            summary = {
                "game_id": game["game_id"],
                "player_name": game["player_name"],
                "mode": game["mode"],
                "round_length": game["round_length"],
                "rule_profile": game.get("rule_profile", "RANKED"),
                "minimum_han": game.get("minimum_han", 1),
                "aka_dora_count": game.get("aka_dora_count"),
                "sanma_scoring_mode": game.get("sanma_scoring_mode", "TSUMO_LOSS"),
                "status": game["status"],
                "round_label": game["public_state"]["round_label"],
                "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
                "points": [player["points"] for player in game["players"]],
                "placements": result_summary.get("placements", []),
            }
            if record is None:
                record = GameRecord(
                    id=game["game_id"],
                    player_name=game["player_name"],
                    mode=game["mode"],
                    round_length=game["round_length"],
                    status=game["status"],
                    summary_json=summary,
                    # 新版本把大对象拆到子表。旧字段保留空值，兼容旧表结构和旧代码。
                    state_json={},
                    action_log_json=[],
                    snapshots_json=[],
                    result_json=result_summary or None,
                )
                session.add(record)
            else:
                record.player_name = game["player_name"]
                record.mode = game["mode"]
                record.round_length = game["round_length"]
                record.status = game["status"]
                record.summary_json = summary
                record.state_json = {}
                record.action_log_json = []
                record.snapshots_json = []
                record.result_json = result_summary or None
                record.updated_at = datetime.utcnow()
            # The split tables have foreign keys to `games.id`. Flush the parent
            # row first so a newly created game exists before action/snapshot
            # child rows are inserted in the same transaction.
            session.flush()
            self._sync_split_records(session, game, result_summary)
            session.commit()

    def load_game(self, game_id: str) -> dict[str, Any] | None:
        with SessionLocal() as session:
            state_record = session.get(GameStateRecord, game_id)
            if state_record is not None and state_record.state_json:
                actions = self._read_action_log(session, game_id)
                snapshots = self._read_replay_snapshots(session, game_id)
                return hydrate_runtime_state(state_record.state_json, actions, snapshots)

            # 兼容 v2.2 之前的历史数据：旧数据仍在 games.state_json。
            record = session.get(GameRecord, game_id)
            return None if record is None else record.state_json

    def delete_game(self, game_id: str) -> bool:
        with SessionLocal() as session:
            record = session.get(GameRecord, game_id)
            if record is None:
                return False
            self._delete_split_records(session, game_id)
            session.delete(record)
            session.commit()
            return True

    def list_games(self, limit: int = 20) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            stmt: Select[tuple[dict[str, Any]]] = (
                select(GameRecord.summary_json).order_by(desc(GameRecord.updated_at)).limit(limit)
            )
            return list(session.scalars(stmt).all())

    def get_replay(self, game_id: str) -> dict[str, Any] | None:
        with SessionLocal() as session:
            record = session.get(GameRecord, game_id)
            if record is None:
                return None
            snapshots = self._read_replay_snapshots(session, game_id)
            actions = self._read_action_log(session, game_id)
            if snapshots is None:
                snapshots = deepcopy(record.snapshots_json or [])
            if actions is None:
                actions = deepcopy(record.action_log_json or [])
            for snapshot in snapshots:
                state = snapshot.get("state") if isinstance(snapshot, dict) else None
                if isinstance(state, dict):
                    state["hint"] = None
            result_record = session.get(GameResultRecord, game_id)
            return {
                "game_id": record.id,
                "snapshots": snapshots,
                "actions": actions,
                "result": result_record.result_json if result_record is not None else record.result_json,
            }

    def get_player_stats(self, player_name: str) -> dict[str, Any]:
        aliases = player_name_aliases(player_name)
        with SessionLocal() as session:
            split_stmt = (
                select(GamePlayerRecord.placement, GamePlayerRecord.final_points)
                .join(GameRecord, GameRecord.id == GamePlayerRecord.game_id)
                .where(
                    GamePlayerRecord.name.in_(aliases),
                    GamePlayerRecord.is_human == True,  # noqa: E712
                    GameRecord.status == "FINISHED",
                    GamePlayerRecord.placement.is_not(None),
                    GamePlayerRecord.final_points.is_not(None),
                )
            )
            split_records = session.execute(split_stmt).all()
            if split_records:
                placements = [int(row.placement) for row in split_records]
                scores = [int(row.final_points) for row in split_records]
                return {
                    "player_name": (player_name or "").strip() or "访客",
                    "games_played": len(placements),
                    "avg_placement": round(sum(placements) / len(placements), 3),
                    "wins": sum(1 for placement in placements if placement == 1),
                    "best_score": max(scores),
                    "ignored_records": 0,
                }

            # 旧数据兜底：尚未迁移时继续从 games.summary_json/result_json 解析。
            stmt = select(GameRecord.summary_json, GameRecord.result_json).where(
                GameRecord.player_name.in_(aliases),
                GameRecord.status == "FINISHED",
            )
            records = session.execute(stmt).all()
            if not records:
                return {
                    "player_name": (player_name or "").strip() or "访客",
                    "games_played": 0,
                    "avg_placement": None,
                    "wins": 0,
                    "best_score": None,
                    "ignored_records": 0,
                }
            placements = []
            best_score = None
            wins = 0
            ignored_records = 0
            for summary_json, result_json in records:
                summary = summary_json if isinstance(summary_json, dict) else {}
                result = result_json if isinstance(result_json, dict) else {}
                human_result = human_placement_from_summary(summary, result, aliases)
                if human_result is None:
                    ignored_records += 1
                    continue

                placement = human_result["placement"]
                points = human_result["points"]
                placements.append(placement)
                if placement == 1:
                    wins += 1
                if best_score is None or points > best_score:
                    best_score = points
            avg_placement = round(sum(placements) / len(placements), 3) if placements else None
            return {
                "player_name": (player_name or "").strip() or "访客",
                "games_played": len(placements),
                "avg_placement": avg_placement,
                "wins": wins,
                "best_score": best_score,
                "ignored_records": ignored_records,
            }

    def _sync_split_records(self, session: Any, game: dict[str, Any], result_summary: dict[str, Any]) -> None:
        """Synchronize split tables with the current in-memory game.

        The expensive fields are handled as append-only streams. A late-round
        save used to delete and rewrite hundreds of actions and snapshots; now
        it keeps old rows in place and only inserts newly appended `seq` values.
        """

        game_id = game["game_id"]
        state_record = session.get(GameStateRecord, game_id)
        compact_state = compact_runtime_state(game)
        if state_record is None:
            session.add(GameStateRecord(game_id=game_id, state_json=compact_state))
        else:
            state_record.state_json = compact_state
            state_record.updated_at = datetime.utcnow()

        # Player rows are tiny and may change points/placement, so replacing
        # them keeps the logic simple without touching the heavy replay tables.
        session.execute(delete(GamePlayerRecord).where(GamePlayerRecord.game_id == game_id))
        placements = {
            int(item["seat"]): item
            for item in result_summary.get("placements", [])
            if isinstance(item, dict) and item.get("seat") is not None
        }
        for player in game.get("players", []):
            seat = int(player["seat"])
            placement = placements.get(seat, {})
            session.add(
                GamePlayerRecord(
                    game_id=game_id,
                    seat=seat,
                    name=player.get("name", ""),
                    is_human=bool(player.get("is_human", False)),
                    ai_level=int(player.get("ai_level", 0) or 0),
                    initial_points=None,
                    final_points=int(placement.get("points", player.get("points", 0))),
                    placement=coerce_int(placement.get("placement")),
                )
            )

        self._append_action_rows(session, game_id, game.get("action_log", []))
        self._append_snapshot_rows(session, game_id, game.get("snapshots", []))

        if result_summary:
            result_record = session.get(GameResultRecord, game_id)
            if result_record is None:
                session.add(
                    GameResultRecord(
                        game_id=game_id,
                        result_json=result_summary,
                        finished_at=str(result_summary.get("finished_at", "")),
                        leftover_riichi_bonus=coerce_int(result_summary.get("leftover_riichi_bonus")) or 0,
                    )
                )
            else:
                result_record.result_json = result_summary
                result_record.finished_at = str(result_summary.get("finished_at", ""))
                result_record.leftover_riichi_bonus = coerce_int(result_summary.get("leftover_riichi_bonus")) or 0
                result_record.updated_at = datetime.utcnow()
        else:
            session.execute(delete(GameResultRecord).where(GameResultRecord.game_id == game_id))

    def _append_action_rows(self, session: Any, game_id: str, action_log: list[Any]) -> None:
        """Append new action-log rows and rebuild only if the sequence regressed."""

        existing_count = (
            session.scalar(select(func.count()).select_from(GameActionRecord).where(GameActionRecord.game_id == game_id))
            or 0
        )
        max_seq = session.scalar(select(func.max(GameActionRecord.seq)).where(GameActionRecord.game_id == game_id)) or 0
        if max_seq > len(action_log) or existing_count != max_seq:
            session.execute(delete(GameActionRecord).where(GameActionRecord.game_id == game_id))
            max_seq = 0
        for entry in action_log:
            if not isinstance(entry, dict):
                continue
            seq = coerce_int(entry.get("seq"))
            if seq is None or seq <= max_seq:
                continue
            session.add(
                GameActionRecord(
                    game_id=game_id,
                    seq=seq,
                    seat=coerce_int(entry.get("seat")) or 0,
                    actor=str(entry.get("actor", "")),
                    action_type=str(entry.get("type", "")),
                    tile_label=str(entry.get("tile", "")),
                    round_label=str(entry.get("round", "")),
                    details=str(entry.get("details", "")),
                    state_hash=str(entry.get("state_hash", "")),
                    action_json=entry,
                )
            )

    def _append_snapshot_rows(self, session: Any, game_id: str, snapshots: list[Any]) -> None:
        """Append new replay snapshots and rebuild only if the sequence regressed."""

        existing_count = (
            session.scalar(
                select(func.count()).select_from(GameReplaySnapshotRecord).where(GameReplaySnapshotRecord.game_id == game_id)
            )
            or 0
        )
        max_seq = (
            session.scalar(
                select(func.max(GameReplaySnapshotRecord.seq)).where(GameReplaySnapshotRecord.game_id == game_id)
            )
            or 0
        )
        if max_seq > len(snapshots) or existing_count != max_seq:
            session.execute(delete(GameReplaySnapshotRecord).where(GameReplaySnapshotRecord.game_id == game_id))
            max_seq = 0
        for snapshot in snapshots:
            if not isinstance(snapshot, dict):
                continue
            seq = coerce_int(snapshot.get("seq"))
            if seq is None or seq <= max_seq:
                continue
            session.add(
                GameReplaySnapshotRecord(
                    game_id=game_id,
                    seq=seq,
                    action_type=str(snapshot.get("type", "")),
                    round_label=str(snapshot.get("round", "")),
                    snapshot_json=snapshot,
                )
            )

    def _read_action_log(self, session: Any, game_id: str) -> list[dict[str, Any]] | None:
        """Read split action rows, returning None when only legacy JSON exists."""

        records = list(
            session.scalars(
                select(GameActionRecord)
                .where(GameActionRecord.game_id == game_id)
                .order_by(GameActionRecord.seq)
            )
        )
        return [deepcopy(item.action_json) for item in records] if records else None

    def _read_replay_snapshots(self, session: Any, game_id: str) -> list[dict[str, Any]] | None:
        """Read split replay rows, returning None when only legacy JSON exists."""

        records = list(
            session.scalars(
                select(GameReplaySnapshotRecord)
                .where(GameReplaySnapshotRecord.game_id == game_id)
                .order_by(GameReplaySnapshotRecord.seq)
            )
        )
        return [deepcopy(item.snapshot_json) for item in records] if records else None

    def _delete_split_records(self, session: Any, game_id: str) -> None:
        """删除某局在拆分表中的旧记录。"""

        for model in (
            GameResultRecord,
            GameReplaySnapshotRecord,
            GameActionRecord,
            GamePlayerRecord,
            GameStateRecord,
        ):
            session.execute(delete(model).where(model.game_id == game_id))
