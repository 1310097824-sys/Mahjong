from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import Select, desc, func, select

from app.db import SessionLocal
from app.models import GameRecord


def player_name_aliases(player_name: str) -> set[str]:
    normalized = (player_name or "").strip() or "访客"
    aliases = {normalized}
    # 旧版本默认玩家名是 Guest，但前端会显示成“访客”。统计时把两者视为同一个默认玩家。
    if normalized in {"访客", "Guest"}:
        aliases.update({"访客", "Guest"})
    return aliases


def coerce_int(value: Any) -> int | None:
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


def human_placement_from_summary(summary: dict[str, Any], result: dict[str, Any], aliases: set[str]) -> dict[str, Any] | None:
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
                    state_json=game,
                    action_log_json=game["action_log"],
                    snapshots_json=game["snapshots"],
                    result_json=result_summary or None,
                )
                session.add(record)
            else:
                record.player_name = game["player_name"]
                record.mode = game["mode"]
                record.round_length = game["round_length"]
                record.status = game["status"]
                record.summary_json = summary
                record.state_json = game
                record.action_log_json = game["action_log"]
                record.snapshots_json = game["snapshots"]
                record.result_json = result_summary or None
                record.updated_at = datetime.utcnow()
            session.commit()

    def load_game(self, game_id: str) -> dict[str, Any] | None:
        with SessionLocal() as session:
            record = session.get(GameRecord, game_id)
            if record is None:
                return None
            return record.state_json

    def delete_game(self, game_id: str) -> bool:
        with SessionLocal() as session:
            record = session.get(GameRecord, game_id)
            if record is None:
                return False
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
            snapshots = deepcopy(record.snapshots_json or [])
            for snapshot in snapshots:
                state = snapshot.get("state") if isinstance(snapshot, dict) else None
                if isinstance(state, dict):
                    state["hint"] = None
            return {
                "game_id": record.id,
                "snapshots": snapshots,
                "actions": record.action_log_json,
                "result": record.result_json,
            }

    def get_player_stats(self, player_name: str) -> dict[str, Any]:
        aliases = player_name_aliases(player_name)
        with SessionLocal() as session:
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
