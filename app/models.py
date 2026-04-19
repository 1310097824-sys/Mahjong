from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GameRecord(Base):
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
