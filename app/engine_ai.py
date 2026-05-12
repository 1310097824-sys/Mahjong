"""AI 子模块聚合入口。

为了保持旧 import 兼容，AI 相关函数在这里重新导出。具体实现已经拆到弃牌评估、
鸣牌评估、行动提示和最终决策四个文件，方便继续向 AlphaJong/深度学习方向演进。
"""

from __future__ import annotations

from app.engine_ai_discard import *
from app.engine_ai_call import *
from app.engine_ai_hint import *
from app.engine_ai_decision import *
