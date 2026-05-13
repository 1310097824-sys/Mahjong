# 浏览器版立直麻将系统 v2.3

这是一个本地运行的浏览器版立直麻将单人对战系统。项目目标是逐步做成接近雀魂体验的本地麻将游戏：中文界面、网麻牌桌、三麻/四麻规则、AI 对战、行动提示、牌谱回放、历史对局、玩家统计，以及后续可继续扩展到训练型麻将 AI。

当前 v2.3 使用 `FastAPI + React + TypeScript + MySQL + Rust core` 的混合架构。React 前端负责牌桌表现和交互，FastAPI 后端负责规则推进、AI 决策、结算和持久化，Rust core 负责向听、进张、风险、计分和 EV 等性能敏感计算。

## v2.3 版本重点

- 后端规则继续向雀魂/标准立直麻将对齐，规则审计脚本当前为 `PASS 37 / MISSING 0 / FAIL 0`。
- Rust core 继续扩展，已覆盖更多规则、计分、形状、风险和 EV 相关的热路径计算。
- MySQL 持久化从单表大 JSON 拆成多表结构，降低历史列表、回放、统计和晚巡保存压力。
- 启动脚本会自动检查 MySQL、前端构建、Rust core 构建和数据库拆表迁移。
- 前端牌桌继续采用网麻风格，包含 macOS Dock 式底部面板、行动提示小窗、传统麻将牌面、象牙白牌底和 Canvas 水波背景。
- 牌谱回放新增自动播放、暂停、速度控制、手动 seek 自动暂停。
- API 错误处理更稳，后端返回纯文本错误时不再显示误导性的 JSON 解析报错。

## 当前能力

- 支持四麻和三麻。
- 支持东风战和半庄战。
- 支持段位默认、友人场、古役房规则档位。
- 支持是否开启古役。
- 支持最低和牌番数、赤宝牌数量、三麻自摸损、三麻北家折半等规则选项。
- 支持吃、碰、明杠、暗杠、加杠、立直、自摸、荣和、拔北、九种九牌。
- 支持立直后自动摸切、抢杠、岭上、海底、河底、荒牌流局、途中流局、流局听牌结算。
- 支持历史对局保存、删除、载入、牌谱回放和玩家统计。
- 支持 AI L1/L2/L3，L3 包含更强的风险评估、押退判断和浅层前瞻。
- 支持行动提示面板和“前三推荐”可拖动小窗，提示逻辑复用 AI 的实际评估链路。
- 支持 React 牌桌、中心电子桌芯、四家牌河、各家副露展示、传统麻将牌面和象牙白牌底。

## 技术栈

### 后端

- `FastAPI`：提供 HTTP API，并托管 React 构建后的静态资源。
- `SQLAlchemy 2.x`：管理 MySQL engine、Session 和 ORM 模型。
- `PyMySQL`：作为 SQLAlchemy 连接 MySQL 的驱动。
- `mahjong`：提供部分立直麻将基础计算能力。
- `Rust cdylib`：通过 `ctypes` 接入 Python，承担性能敏感的纯计算。

### 前端

- `React 19`：实现牌桌、Dock 面板、结算面板、历史列表、回放和行动提示 UI。
- `TypeScript`：约束前后端数据结构。
- `Vite`：本地开发和生产构建。
- `Tailwind CSS`：主要样式系统。
- `Framer Motion`：Dock、弹窗、拖拽小窗和过渡动画。
- `react-riichi-mahjong-tiles`：传统麻将牌面渲染基础。
- `Canvas`：实时水波背景。

### 数据库

当前主数据库为 MySQL，默认数据库名为 `mahjong`。连接优先读取 `.env` 中的 `DATABASE_URL`，如果没有提供完整连接串，则按 MySQL 分项配置生成连接。

示例 `.env`：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的本地密码
MYSQL_DATABASE=mahjong
MYSQL_CHARSET=utf8mb4
```

也可以直接使用完整连接串：

```env
DATABASE_URL=mysql+pymysql://root:你的本地密码@127.0.0.1:3306/mahjong?charset=utf8mb4
```

当前业务表：

- `games`：轻量对局主表，保存历史摘要、状态、模式和兼容字段。
- `game_states`：可恢复对局状态，不再重复保存动作日志和回放快照。
- `game_players`：每局每个玩家的座位、分数、AI 等级和名次。
- `game_actions`：逐行动作日志。
- `game_replay_snapshots`：逐步回放快照。
- `game_results`：终局结算摘要。

更详细的数据库说明见 [database.md](database.md)。

## 项目结构

```text
Mahjong/
├── app/
│   ├── main.py                 # FastAPI 入口、API 路由、React 静态资源托管
│   ├── config.py               # 环境变量、MySQL 连接串和默认设置
│   ├── db.py                   # SQLAlchemy engine、Session、建库建表和运行期索引
│   ├── models.py               # ORM 模型，包含 games 与拆分后的多张业务表
│   ├── store.py                # 对局保存、读取、删除、回放和玩家统计
│   ├── rust_core.py            # Python 到 Rust DLL 的 ctypes 桥接
│   ├── engine.py               # 兼容聚合入口，重新导出 engine_* 模块
│   ├── engine_common.py        # ActionChoice、稳定随机种子、AI 难度策略
│   ├── engine_constants.py     # 规则常量、AI 权重、动作优先级
│   ├── engine_tiles.py         # 牌 ID、牌种、赤宝牌、宝牌、向听入口
│   ├── engine_shape.py         # 牌型结构、听牌等待、完整形判断
│   ├── engine_rules.py         # 规则配置、默认状态、座风和宝牌信息
│   ├── engine_round.py         # 天和、地和、海底、河底、九种九牌等时机判断
│   ├── engine_scoring.py       # 和牌计分、古役、三麻计分、责任支付
│   ├── engine_actions.py       # 合法动作生成和反应动作判断
│   ├── engine_mutations.py     # 摸牌、弃牌、鸣牌、揭宝牌等状态变更
│   ├── engine_execute.py       # 根据 action_id 执行玩家动作
│   ├── engine_flow.py          # AI 自动推进、反应窗口和防死循环调度
│   ├── engine_game.py          # 新建对局、开新局、发牌和初始化
│   ├── engine_settlement.py    # 和牌、流局、连庄、终局和排名结算
│   ├── engine_state.py         # 内部状态转前端公开状态
│   ├── engine_risk.py          # 对手模型、危险度、安全度和防守评估
│   ├── engine_ai_discard.py    # 弃牌 EV、顺位 EV、Alpha 风格前瞻
│   ├── engine_ai_call.py       # 吃碰杠、拔北、立直相关 AI 评估
│   ├── engine_ai_hint.py       # 行动提示面板和前三推荐小窗数据
│   └── engine_ai_decision.py   # AI 最终行动选择器
├── rust_core/
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs              # Rust core 模块入口
│       ├── ffi.rs              # C ABI 暴露给 Python ctypes
│       ├── tiles.rs            # 牌 ID、牌种、三麻合法牌、赤宝牌
│       ├── shanten.rs          # 标准形、七对子、国士向听
│       ├── analysis.rs         # 批量进张、候选摸牌、路线分析
│       ├── risk.rs             # 批量危险度、安全度、安全牌储备
│       ├── ev.rs               # 弃牌、押退、防守、顺位和前瞻 EV
│       ├── rules.rs            # 轻量规则辅助函数
│       ├── scoring.rs          # 计分相关纯函数
│       └── shape.rs            # 牌型形状判断
├── riichi-mahjong-ui/
│   ├── src/App.tsx
│   ├── src/components/Mahjong/
│   │   ├── Table.tsx           # 主牌桌、Dock 面板、回放和行动提示
│   │   ├── MahjongTile.tsx     # 麻将牌显示
│   │   ├── Hand.tsx            # 手牌
│   │   ├── River.tsx           # 牌河
│   │   └── WaterBackground.tsx # Canvas 水波背景
│   └── package.json
├── tests/
│   └── mahjong_soul_rule_audit.py
├── migrate_games_to_split_tables.py
├── migrate_sqlite_to_mysql.py
├── start_mahjong_system.ps1
├── stop_mahjong_system.ps1
├── logic.md
├── programingsign.md
├── tech.md
├── database.md
├── references.md
└── development_roadmap.md
```

## 后端运行链路

1. 前端调用 `POST /api/games` 创建新对局。
2. `app.main` 调用 `new_game()` 创建内部 game 状态。
3. `engine_game` 初始化玩家、发牌、宝牌、座位和 `round_state`。
4. 前端提交动作到 `POST /api/games/{game_id}/actions`。
5. `engine_execute` 校验 `action_id` 并执行动作。
6. `engine_mutations` 修改底层状态。
7. `engine_flow` 自动推进 AI、反应窗口、流局或结算。
8. `engine_state` 生成前端公开状态。
9. `store.py` 把摘要、轻状态、动作日志、回放快照和结果写入 MySQL。

## AI 逻辑概览

当前 AI 是可解释的规则型/EV 型 AI，不是深度学习模型。弃牌和特殊操作都会转换成可比较的结构化评估。

主要评估项：

- 向听数和有效进张。
- 牌型质量，例如两面、坎张、边张、单骑和复合等待。
- 役种路线，例如立直、断幺、役牌、染手、七对子、对对等。
- 打点估算，包括宝牌、赤宝牌、拔北、门清价值和立直价值。
- 对手威胁，包括立直、副露、染手、役牌、对对、宝牌外露和巡目压力。
- 安全度，包括现物、筋、壁、字牌、对手弃牌河和多家综合风险。
- 押退判断，包括手牌价值、听牌距离、失点风险、点差和局况。
- 顺位收益，包括末局守位、追分、避末位、亲家和供托本场。
- L3 前瞻搜索，包括有限 beam search 和晚巡快速评估。

更详细的打牌逻辑见 [logic.md](logic.md)。

## Rust core 加速

Rust core 是渐进式迁移，不取代 Python 规则主流程。Python 端通过 [app/rust_core.py](app/rust_core.py) 调用 DLL。若 Rust DLL 不存在或版本不匹配，后端会尽量回退到 Python 逻辑，但 AI 性能会下降。

手动构建：

```powershell
cd rust_core
cargo build --release
cd ..
```

运行测试：

```powershell
cd rust_core
cargo test
cd ..
```

## 快速启动

### 1. 安装 Python 依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

如果你已经在项目父目录有可用 `.venv`，启动脚本也会尝试复用父目录虚拟环境。

### 2. 准备 MySQL

确认本机存在 `MySQL80` 服务，并且 `.env` 中账号密码正确。后端启动时会自动创建数据库和表结构。

### 3. 安装前端依赖并构建

```powershell
cd riichi-mahjong-ui
npm install
npm run build
cd ..
```

### 4. 一键启动

推荐直接运行：

```powershell
.\start_mahjong_system.ps1
```

如果系统策略禁止直接执行 `.ps1`，可以双击：

```text
start_mahjong_system.cmd
```

启动脚本会自动执行：

- 检查并启动 `MySQL80` 服务。
- 执行 `migrate_games_to_split_tables.py`，保证拆表迁移为最新。
- 检查前端构建是否过期，必要时自动 `npm run build`。
- 检查 Rust core 是否过期，必要时自动 `cargo build --release`。
- 启动 FastAPI 后端。
- 打开浏览器访问 `http://127.0.0.1:8000`。

关闭系统：

```powershell
.\stop_mahjong_system.ps1
```

或双击：

```text
stop_mahjong_system.cmd
```

手动启动后端：

```powershell
uvicorn app.main:app --reload
```

## API 概览

- `GET /`：打开 React 前端。
- `GET /api/health`：健康检查。
- `GET /api/games`：历史对局列表。
- `GET /api/games/{game_id}`：读取指定对局。
- `DELETE /api/games/{game_id}`：删除历史对局。
- `POST /api/games`：创建新对局。
- `POST /api/games/{game_id}/actions`：提交动作。
- `GET /api/games/{game_id}/replay`：读取牌谱回放。
- `GET /api/stats/{player_name}`：读取玩家统计。

## 测试与验证

Python 语法检查：

```powershell
$files = Get-ChildItem -Path app -Filter *.py -File | ForEach-Object { $_.FullName }
python -m py_compile @files migrate_games_to_split_tables.py
```

Rust 测试：

```powershell
cd rust_core
cargo test
cd ..
```

雀魂规则审计：

```powershell
python tests\mahjong_soul_rule_audit.py
```

前端类型检查：

```powershell
cd riichi-mahjong-ui
npm run lint
cd ..
```

前端生产构建：

```powershell
cd riichi-mahjong-ui
npm run build
cd ..
```

数据库拆表迁移：

```powershell
python migrate_games_to_split_tables.py
```

## 文档索引

- [logic.md](logic.md)：打牌逻辑、AI 评估和最优解计算过程。
- [programingsign.md](programingsign.md)：项目结构和各文件职责。
- [tech.md](tech.md)：技术栈和使用位置。
- [database.md](database.md)：MySQL、SQLAlchemy、表结构和持久化流程。
- [references.md](references.md)：论文、规则资料、开源项目和 AI 参考来源。
- [development_roadmap.md](development_roadmap.md)：后续从网麻系统到深度学习 AI 的路线。

## 注意事项

- `.env`、日志、pid、MySQL 数据文件、Python 缓存、Rust `target` 和前端 `node_modules` 不应提交。
- 如果页面仍显示旧前端，先重新执行 `npm run build`，再重启 FastAPI。
- 如果 MySQL 启动失败，优先检查 `MySQL80` 服务、`3306` 端口占用、游离 `mysqld.exe` 和数据目录锁。
- 当前 AI 已接近“可解释网麻 AI”的方向，但还不是训练型深度学习 AI。深度学习路线已在 [development_roadmap.md](development_roadmap.md) 中拆解。
