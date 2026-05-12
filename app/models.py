"""SQLAlchemy ORM 数据模型。

当前系统只有一张核心业务表 `games`：它用关系型字段保存索引信息，用 JSON
字段保存完整对局状态、动作日志、回放快照和结算结果。这种设计在单机/本地
阶段开发效率高，也便于后续逐步拆成玩家、牌谱、动作明细等更细的表。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
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
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
