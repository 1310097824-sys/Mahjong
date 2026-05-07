# 浏览器版雀魂风格立直麻将系统 v2.1

这是一个基于 **Python FastAPI + React + TypeScript + MySQL** 的本地浏览器版立直麻将单人对战系统。项目目标是做出接近成熟网麻体验的本地立直麻将：前端提供沉浸式牌桌、Dock 面板、行动提示和回放展示，后端负责规则推进、AI 决策、计分结算、历史对局和统计持久化。

v2.1 是一个文档和路线图增强版本：在 v2.0 的规则、AI、前端和 MySQL 基础上，补充了数据库结构说明，以及从当前系统一路发展到深度学习 AI、模型平台、联机赛事和研究平台的长期路线图。

## 当前能力

- 浏览器牌桌：React + TypeScript 构建，支持四家/三家牌桌、手牌、牌河、副露、宝牌、桌芯、结算和回放。
- 中文优先：界面文案、结算说明、行动提示、规则选项和统计面板以中文展示。
- 雀魂式信息组织：中心电子桌芯、中心十字牌河、三麻/四麻方位灯、立直横置牌、宝牌指示和副露展示。
- 原创视觉实现：Canvas 水波桌面、传统麻将牌面、象牙白牌座、立体边框、玻璃质感面板和 macOS Dock 风格底部导航。
- Dock 面板：牌桌下方固定 Dock，点击后在牌桌附近展开小窗口；行动提示支持前三推荐小窗并可拖动。
- 规则模式：支持四麻/三麻、东风/半庄、段位默认、友人场、古役房。
- 规则选项：支持最低和牌番数、赤宝牌数量、三麻自摸损、三麻北家折半、古役开关。
- 特殊操作：支持吃、碰、明杠、暗杠、加杠、立直、自摸、荣和、拔北、九种九牌。
- AI 难度：支持 L1/L2/L3，差异体现在随机性、进攻深度、防守意识、押退判断和浅层前瞻。
- AI 行动提示：弃牌和特殊操作都会接入行动分析，输出推荐、风险、进张、役种路线、押退和 EV 信息。
- MySQL 持久化：保存对局摘要、完整状态、操作日志、回放快照和结算结果。
- 历史与统计：支持历史对局、删除历史对局、回放、玩家统计，并兼容旧版 `Guest` / `访客` 默认玩家名。
- 文档体系：提供结构、技术、规则 AI、数据库、文献和长期路线图说明。

## 项目结构

```text
Mahjong/
├─ app/                         # FastAPI 后端与麻将规则引擎
│  ├─ config.py                  # 环境变量、MySQL 连接和默认配置
│  ├─ db.py                      # SQLAlchemy 引擎、会话和数据库初始化
│  ├─ engine.py                  # 核心规则、AI、动作推进、结算和审计辅助逻辑
│  ├─ main.py                    # FastAPI API、React 静态资源托管
│  ├─ models.py                  # SQLAlchemy ORM 模型
│  ├─ store.py                   # 对局保存、历史、回放和玩家统计
│  ├─ static/                    # 未构建 React 时的旧静态资源兜底
│  └─ templates/                 # 旧模板兜底
├─ riichi-mahjong-ui/            # React + TypeScript 前端
│  ├─ src/App.tsx                # 前端入口
│  ├─ src/components/Mahjong/    # 牌桌、手牌、牌河、麻将牌、Dock、水波背景
│  ├─ src/types/mahjong.ts       # 前后端数据类型
│  └─ package.json               # 前端依赖与脚本
├─ tests/
│  └─ mahjong_soul_rule_audit.py # 雀魂规则对齐自动化审计
├─ README.md                     # 项目入口说明
├─ logic.md                      # 打牌逻辑与 AI 最优解计算说明
├─ programingsign.md             # 项目结构与文件职责说明
├─ tech.md                       # 技术栈与使用位置说明
├─ database.md                   # MySQL、SQLAlchemy、表结构和持久化说明
├─ references.md                 # 论文、文献、规则资料和开源项目来源
├─ development_roadmap.md        # 后续发展路线图，覆盖 v2.1 到 v8.0
├─ requirements.txt              # Python 后端依赖
├─ start_mahjong_system.ps1      # Windows 一键启动脚本
├─ stop_mahjong_system.ps1       # Windows 一键关闭脚本
└─ migrate_sqlite_to_mysql.py    # 旧 SQLite 数据迁移到 MySQL
```

## 快速启动

### 1. 安装后端依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

如果你已经在 `D:\py\.venv` 有可用环境，也可以继续复用现有虚拟环境。

### 2. 配置 MySQL

项目默认使用 MySQL。根目录 `.env` 示例：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=mahjong
MYSQL_CHARSET=utf8mb4
```

也可以直接写完整连接串：

```env
DATABASE_URL=mysql+pymysql://root:123456@127.0.0.1:3306/mahjong?charset=utf8mb4
```

后端启动时会自动初始化数据库和数据表。当前主数据库名是 `mahjong`，当前业务表是 `games`。详细结构见 `database.md`。

### 3. 安装并构建前端

```powershell
cd riichi-mahjong-ui
npm install
npm run build
cd ..
```

构建产物会输出到 `riichi-mahjong-ui/dist`，FastAPI 会优先托管这个 React 生产构建。

### 4. 一键启动

```powershell
.\start_mahjong_system.ps1
```

脚本会检查 `MySQL80` 服务、确认前端已经构建、启动 FastAPI，并打开浏览器。

访问地址：

```text
http://127.0.0.1:8000
```

关闭系统：

```powershell
.\stop_mahjong_system.ps1
```

只手动启动后端时可使用：

```powershell
uvicorn app.main:app --reload
```

## API 概览

- `GET /`：打开 React 前端页面。
- `GET /api/health`：健康检查。
- `GET /api/games`：读取历史对局列表。
- `GET /api/games/{game_id}`：读取指定对局当前公开状态。
- `DELETE /api/games/{game_id}`：删除历史对局。
- `POST /api/games`：创建新对局。
- `POST /api/games/{game_id}/actions`：提交出牌或特殊操作。
- `GET /api/games/{game_id}/replay`：读取回放快照。
- `GET /api/stats/{player_name}`：读取玩家统计。

## 数据库与持久化

系统当前使用 `SQLAlchemy + PyMySQL + MySQL`：

- `MySQL`：实际保存历史对局、回放、结算和统计数据。
- `PyMySQL`：Python 连接 MySQL 的底层驱动。
- `SQLAlchemy`：创建连接引擎、Session、ORM 表模型和数据库读写。

当前 MySQL 使用 `mahjong` 数据库，核心业务表为 `games`。系统采用“关系型表 + JSON 文档”的方式保存牌局：`summary_json` 用于历史列表，`state_json` 用于恢复完整对局，`action_log_json` 用于动作日志，`snapshots_json` 用于回放，`result_json` 用于终局结算。

详细字段、索引、读写流程和后续拆表建议见 `database.md`。

## 规则说明

核心规则位于 `app/engine.py`。当前系统以后端为唯一规则源，前端只提交动作，不直接裁定牌理。

已覆盖的主要规则方向：

- 四麻和三麻牌山、王牌、宝牌指示、赤宝牌。
- 东风和半庄对局流程。
- 段位默认、友人场、古役房规则档位。
- 起点和目标点：四麻默认 25000 / 30000，三麻默认 35000 / 40000。
- 吃、碰、明杠、暗杠、加杠、抢杠、岭上、海底、河底。
- 立直、一发、双立直、立直后自动摸切、立直后暗杠限制。
- 三麻拔北、三麻自摸损、三麻北家折半。
- 多响、供托、本场、连庄、荒牌流局、途中流局、九种九牌。
- 古役房可选古役，包括人和、大车轮、大竹林、大数邻、大七星、三连刻、一色三顺等。

规则对齐请运行：

```powershell
python tests\mahjong_soul_rule_audit.py
```

## AI 与行动提示

当前 AI 是可解释的规则型/EV 型 AI，不是神经网络模型，也没有直接接入 Suphx、AlphaJong、NAGA 或 Mortal 权重。

AI 决策会综合：

- 向听数和有效进张。
- 牌型质量、两面/坎张/边张/单骑等等待质量。
- 役种路线和估算打点。
- 宝牌、赤宝牌、拔北、门清立直价值。
- 对手立直、副露、染手、役牌、威胁等级和预估失点。
- 现物、筋、壁、字牌等安全度。
- 点差、亲家、南场/东场、守位/追分等局况。
- L3 的浅层前瞻搜索和全局顺位收益。

行动提示面板复用 AI 的评估结果。完整面板会展示详细分析，简洁小窗只显示前三推荐，适合打牌时快速参考。

更详细的算法解释见 `logic.md`。

## 长期发展方向

长期路线集中在 `development_roadmap.md`，已经覆盖：

- `v2.1 - v2.6`：规则审计、牌桌体验、AI 强化、回放统计、数据库拆表。
- `v3.0 - v3.5`：本地账号、原创段位、成就任务、WebSocket 联机。
- `v4.0 - v5.0`：高级 AI 教练、训练数据闭环、监督学习、价值网络、模型推理、L4/L5 深度学习 AI。
- `v5.1 - v6.0`：大规模数据集、训练基础设施、高级模型结构、自对弈、AI 平台化。
- `v6.1 - v8.0`：多模型生态、云训练、统一牌谱协议、AI 联赛、个性化教练、插件生态、隐私数据协作、研究平台和成熟麻将 AI 平台。

这份路线图是后续持续开发的主参考文档。

## 文档索引

- `logic.md`：打牌逻辑、规则推进和 AI 最优解计算过程。
- `programingsign.md`：项目结构和各文件职责。
- `tech.md`：系统使用的技术栈以及每项技术用在哪里。
- `database.md`：SQLAlchemy、PyMySQL、MySQL、表结构、字段和后续拆表方向。
- `references.md`：论文、规则资料、开源库和 AI 项目参考来源。
- `development_roadmap.md`：后续从 v2.1 到 v8.0 的详细发展路线。
- `spec.pdf` / `spec.txt`：早期实施方案文档。

## 测试与验证

后端语法检查：

```powershell
python -m py_compile app\engine.py app\main.py app\store.py tests\mahjong_soul_rule_audit.py
```

雀魂规则审计：

```powershell
python tests\mahjong_soul_rule_audit.py
```

前端类型检查：

```powershell
cd riichi-mahjong-ui
npm run lint
```

前端生产构建：

```powershell
cd riichi-mahjong-ui
npm run build
```

## v2.1 版本重点

- 重写 README，统一反映当前 v2.1 系统能力、文档体系和长期路线。
- 新增 `database.md`，详细说明 SQLAlchemy、PyMySQL、MySQL、`mahjong` 数据库、`games` 表结构和后续拆表方向。
- 新增 `development_roadmap.md`，详细规划从 v2.1 到 v8.0 的发展方向。
- 路线图补充深度学习 AI 方向，包括数据闭环、监督学习、价值网络、离线强化学习、自对弈、模型服务、AI 联赛和研究平台。
- 当前版本继续保留 v2.0 的规则、AI、Dock 面板、行动提示小窗、MySQL 持久化和规则审计能力。

## 注意事项

- `.env`、日志、数据库文件、构建缓存和 `node_modules` 不应提交到 Git。
- `mahjong.db` 是旧 SQLite 数据文件，当前主流程以 MySQL 为准。
- 如果 MySQL 重启后异常，优先检查 `mysqld.exe` 游离进程、3306 端口占用、服务状态和数据目录锁文件。
- 如果打开页面仍是旧 UI，请重新执行 `npm run build`，再重启 FastAPI。
- 当前 AI 已具备网麻式启发，但还不是深度学习强 AI；深度学习路线已在 `development_roadmap.md` 中作为长期目标拆解。
