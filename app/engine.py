"""后端麻将引擎聚合入口。

历史版本里规则、AI、动作推进和结算都集中在这个文件。当前版本已经把逻辑拆到
多个 `engine_*` 模块中，本文件保留为兼容层：对外仍然暴露旧的 `app.engine`
接口，内部通过星号导入聚合各模块函数。这样前端、测试和旧代码不需要一次性
改 import 路径，同时后端实现已经开始走模块化结构。
"""

from __future__ import annotations

from app.engine_common import *
from app.engine_constants import *
from app.engine_rules import *
from app.engine_risk import *
from app.engine_round import *
from app.engine_scoring import *
from app.engine_shape import *
from app.engine_tiles import *
from app.engine_actions import *
from app.engine_ai import *
from app.engine_state import *
from app.engine_settlement import *
from app.engine_flow import *
