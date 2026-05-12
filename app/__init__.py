"""浏览器版单人立直麻将后端包。

`app` 包包含 FastAPI 入口、MySQL 持久化、规则引擎、AI 决策和 Rust core
桥接层。外部启动时通常只需要加载 `app.main:app`，其他模块由入口和引擎按需导入。
"""
