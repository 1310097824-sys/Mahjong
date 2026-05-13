"""SQLAlchemy ORM 数据模型。

当前系统只有一张核心业务表 `games`：它用关系型字段保存索引信息，用 JSON
字段保存完整对局状态、动作日志、回放快照和结算结果。这种设计在单机/本地
阶段开发效率高，也便于后续逐步拆成玩家、牌谱、动作明细等更细的表。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GameRecord(Base):
    """一局麻将对局的持久化记录。

    `summary_json` 用于历史列表快速展示；`state_json` 用于恢复当前对局；
    `action_log_json` 和 `snapshots_json` 用于回放；`result_json` 用于统计和结算面板。
    """

    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    player_name: Mapped[str] = mapped_column(String(32), index=True)
    mode: Mapped[str] = mapped_column(String(2), index=True)
    round_length: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), index=True)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    action_log_json: Mapped[list] = mapped_column(JSON, default=list)
    snapshots_json: Mapped[list] = mapped_column(JSON, default=list)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


class GameStateRecord(Base):
    """当前可恢复对局状态。

    `games` 表只保留轻量摘要后，完整 `game` 字典放到这里。恢复对局和提交动作时
    才需要读取这张表，历史列表、统计和回放不再被它拖慢。
    """

    __tablename__ = "game_states"

    game_id: Mapped[str] = mapped_column(String(36), ForeignKey("games.id"), primary_key=True)
    state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


class GamePlayerRecord(Base):
    """一局对局内的玩家席位结果。

    玩家统计以后优先查这张表，不再从 `result_json` / `summary_json` 里反复解析。
    """

    __tablename__ = "game_players"
    __table_args__ = (
        Index("ix_game_players_name_human", "name", "is_human"),
        Index("ix_game_players_name_placement", "name", "placement"),
    )

    game_id: Mapped[str] = mapped_column(String(36), ForeignKey("games.id"), primary_key=True)
    seat: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), index=True)
    is_human: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    ai_level: Mapped[int] = mapped_column(Integer, default=0)
    initial_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    placement: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GameActionRecord(Base):
    """逐行动作日志。

    旧版把整局 action_log 存成一个 JSON 数组；拆表后可以按 `game_id + seq`
    流式读取，也能按动作类型做统计或训练数据抽取。
    """

    __tablename__ = "game_actions"
    __table_args__ = (
        Index("ix_game_actions_game_seq", "game_id", "seq"),
        Index("ix_game_actions_game_type", "game_id", "action_type"),
    )

    game_id: Mapped[str] = mapped_column(String(36), ForeignKey("games.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    seat: Mapped[int] = mapped_column(Integer, index=True)
    actor: Mapped[str] = mapped_column(String(32), default="")
    action_type: Mapped[str] = mapped_column(String(32), index=True)
    tile_label: Mapped[str] = mapped_column(String(16), default="")
    round_label: Mapped[str] = mapped_column(String(32), default="")
    details: Mapped[str] = mapped_column(Text, default="")
    state_hash: Mapped[str] = mapped_column(String(64), default="")
    action_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GameReplaySnapshotRecord(Base):
    """逐步回放快照。

    回放是当前最大的 JSON 来源之一，单独成表后只有打开回放时才读取，历史列表和
    统计查询不会再搬运几 MB 的快照数组。
    """

    __tablename__ = "game_replay_snapshots"
    __table_args__ = (Index("ix_game_replay_snapshots_game_seq", "game_id", "seq"),)

    game_id: Mapped[str] = mapped_column(String(36), ForeignKey("games.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_type: Mapped[str] = mapped_column(String(32), default="")
    round_label: Mapped[str] = mapped_column(String(32), default="")
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GameResultRecord(Base):
    """终局结算摘要。

    结算结果独立保存后，玩家统计和历史列表不用再读取完整 `games.state_json`。
    """

    __tablename__ = "game_results"

    game_id: Mapped[str] = mapped_column(String(36), ForeignKey("games.id"), primary_key=True)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    finished_at: Mapped[str] = mapped_column(String(32), default="")
    leftover_riichi_bonus: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
