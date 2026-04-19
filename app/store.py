from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Select, desc, func, select

from app.db import SessionLocal
from app.models import GameRecord


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
            return {
                "game_id": record.id,
                "snapshots": record.snapshots_json,
                "actions": record.action_log_json,
                "result": record.result_json,
            }

    def get_player_stats(self, player_name: str) -> dict[str, Any]:
        with SessionLocal() as session:
            stmt = select(GameRecord).where(GameRecord.player_name == player_name, GameRecord.status == "FINISHED")
            records = session.scalars(stmt).all()
            if not records:
                return {
                    "games_played": 0,
                    "avg_placement": None,
                    "wins": 0,
                    "best_score": None,
                }
            placements = []
            best_score = None
            wins = 0
            for record in records:
                placements_data = (record.result_json or {}).get("placements", [])
                for item in placements_data:
                    if item.get("is_human"):
                        placements.append(item["placement"])
                        if item["placement"] == 1:
                            wins += 1
                        if best_score is None or item["points"] > best_score:
                            best_score = item["points"]
            avg_placement = round(sum(placements) / len(placements), 3) if placements else None
            return {
                "games_played": len(records),
                "avg_placement": avg_placement,
                "wins": wins,
                "best_score": best_score,
            }
