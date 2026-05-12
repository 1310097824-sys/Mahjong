"""对局自动推进流程。

麻将系统不是一次请求只动一步：AI 行动、反应窗口、流局、结算后开下一局都需要
后端自动推进。这个模块负责循环调度这些阶段，并设置防死循环保护，避免某个特殊
状态让系统卡住。
"""

from __future__ import annotations

from app.engine_game import *
from app.engine_mutations import *
from app.engine_execute import *
