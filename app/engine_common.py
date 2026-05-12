"""规则引擎通用工具。

这里放跨模块共享但不依赖具体规则状态的轻量对象和函数，例如动作数据结构、
稳定随机种子、AI 难度配置读取。把这些基础工具独立出来，可以降低动作、AI、
结算模块之间的循环依赖。
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.engine_constants import AI_LEVEL_POLICIES

@dataclass(slots=True)
class ActionChoice:
    """后端内部统一使用的动作对象。

    无论是出牌、吃碰杠、立直、自摸、荣和、拔北还是九种九牌，最终都会被整理成
    `ActionChoice`。前端收到的是 `to_dict()` 的安全序列化结果。
    """

    action_id: str
    type: str
    seat: int
    label: str
    tile_id: int | None = None
    consumed_ids: list[int] = field(default_factory=list)
    meld_index: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.action_id,
            "type": self.type,
            "seat": self.seat,
            "label": self.label,
            "tile_id": self.tile_id,
            "consumed_ids": list(self.consumed_ids),
            "meld_index": self.meld_index,
            "meta": deepcopy(self.meta),
        }

def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")

def stable_seed(*parts: Any) -> int:
    """生成可复现随机数种子，让 AI L1 的随机性也能跟随牌局状态稳定复现。"""

    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:16], 16)

def ai_level_policy(level: int) -> dict[str, Any]:
    return AI_LEVEL_POLICIES.get(level, AI_LEVEL_POLICIES[2])

def ai_roll(game: dict[str, Any], seat: int, salt: str) -> float:
    seed = stable_seed(game.get("seed", ""), game.get("round_cursor", 0), len(game.get("action_log", [])), seat, salt)
    return seed / float(0xFFFFFFFFFFFFFFFF)

__all__ = [
    "ActionChoice",
    "now_iso",
    "stable_seed",
    "ai_level_policy",
    "ai_roll",
]
