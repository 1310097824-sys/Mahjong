# 技术栈与使用位置说明

本文档说明当前麻将系统使用了哪些技术、每项技术用在什么地方、为什么需要它，以及维护时应关注哪些文件。

## 技术总览

当前系统是一个本地浏览器麻将系统，采用：

- 后端：Python + FastAPI + SQLAlchemy + MySQL。
- 前端：React + TypeScript + Vite + Tailwind CSS。
- UI 动效：Framer Motion + CSS 动画 + Canvas。
- 麻将牌面：`react-riichi-mahjong-tiles`。
- 规则与 AI：Python 规则引擎 + `mahjong` 计分库 + 项目内自定义雀魂规则补全。
- 持久化：MySQL JSON 字段保存完整状态、日志、回放和结算。
- 测试：Python 自动化规则审计 + TypeScript 类型检查 + Vite 构建验证。

## 后端技术

### Python

使用位置：

- `app/config.py`
- `app/db.py`
- `app/engine.py`
- `app/main.py`
- `app/models.py`
- `app/store.py`
- `tests/mahjong_soul_rule_audit.py`
- `migrate_sqlite_to_mysql.py`

承担职责：

- 实现麻将规则。
- 实现 AI 决策。
- 实现 API 服务。
- 实现数据库持久化。
- 实现规则审计。

项目规则逻辑比较复杂，Python 的优势是可读性好、调试方便、适合快速迭代规则和 AI。

### FastAPI

依赖来源：

```text
fastapi==0.135.3
```

使用位置：

- `app/main.py`

承担职责：

- 创建 Web API。
- 接收前端创建对局、提交动作、查询历史和读取回放的请求。
- 返回 JSON 格式的公开游戏状态。
- 托管 React 构建后的静态文件。

主要接口：

- `GET /api/health`
- `GET /api/games`
- `GET /api/games/{game_id}`
- `DELETE /api/games/{game_id}`
- `POST /api/games`
- `POST /api/games/{game_id}/actions`
- `GET /api/games/{game_id}/replay`
- `GET /api/stats/{player_name}`

### Uvicorn

依赖来源：

```text
uvicorn[standard]==0.44.0
```

使用位置：

- 手动启动命令 `uvicorn app.main:app --reload`
- `start_mahjong_system.ps1`

承担职责：

- 作为 ASGI 服务器运行 FastAPI。
- 开发时通过 `--reload` 监听文件变化。

### Pydantic

使用位置：

- `app/main.py`

承担职责：

- 定义请求体模型，例如创建对局的 `CreateGameRequest`。
- 对前端传入的模式、局长、AI 难度、规则档位、起和番数、赤宝牌数量等参数做基础校验。

FastAPI 内置依赖 Pydantic，因此项目没有单独在 `requirements.txt` 中显式列出。

### SQLAlchemy

依赖来源：

```text
sqlalchemy==2.0.49
```

使用位置：

- `app/db.py`
- `app/models.py`
- `app/store.py`

承担职责：

- 创建数据库连接。
- 定义 ORM 模型。
- 读写 MySQL 对局记录。

当前系统把对局状态作为 JSON 保存，因此 SQLAlchemy 主要负责可靠持久化，而不是把每张牌拆成大量关系表。

### MySQL

使用位置：

- `.env`
- `app/config.py`
- `app/db.py`
- `app/store.py`

承担职责：

- 保存历史对局。
- 保存完整状态。
- 保存操作日志。
- 保存回放快照。
- 保存结算结果。
- 支持历史查询、删除和统计。

当前默认数据库名：

```text
mahjong
```

当前默认连接参数来自 `.env` 或环境变量。

### PyMySQL

依赖来源：

```text
pymysql==1.1.1
```

使用位置：

- SQLAlchemy 的 MySQL 驱动。
- 连接串形如 `mysql+pymysql://...`。

承担职责：

- 让 Python 后端通过 SQLAlchemy 连接 MySQL。

### `mahjong` 计分库

依赖来源：

```text
mahjong==2.0.0
```

使用位置：

- `app/engine.py`

承担职责：

- 辅助进行立直麻将和牌、役种、符番和点数计算。

项目并没有完全依赖第三方库完成所有规则，因为雀魂规则和项目需求还包含：

- 三麻拔北。
- 三麻特殊牌山。
- 古役房开关。
- 起和番数限制。
- 赤宝牌数量配置。
- 多响供托归属。
- 途中流局。
- 牌河、振听、立直宣言等状态推进。

这些由 `app/engine.py` 做了大量补充。

### dataclasses / typing / JSON

使用位置：

- `app/config.py`
- `app/engine.py`
- `app/models.py`
- `app/store.py`

承担职责：

- 用 `dataclass` 管理配置。
- 用类型标注提升复杂规则代码的可维护性。
- 用 JSON 字段保存复杂对局状态。

## 前端技术

### React 19

依赖来源：

```json
"react": "^19.0.0",
"react-dom": "^19.0.0"
```

使用位置：

- `riichi-mahjong-ui/src/main.tsx`
- `riichi-mahjong-ui/src/App.tsx`
- `riichi-mahjong-ui/src/components/Mahjong/*.tsx`

承担职责：

- 构建浏览器牌桌 UI。
- 管理对局状态、面板状态、回放状态和设置状态。
- 根据后端公开状态重新渲染手牌、牌河、副露、宝牌和动作按钮。

### TypeScript

依赖来源：

```json
"typescript": "~5.8.2"
```

使用位置：

- `riichi-mahjong-ui/src/**/*.ts`
- `riichi-mahjong-ui/src/**/*.tsx`

承担职责：

- 给前后端数据结构加类型。
- 避免动作类型、牌型、结算字段和提示字段在前端误用。
- 通过 `npm run lint` 执行 `tsc --noEmit` 类型检查。

关键类型文件：

- `riichi-mahjong-ui/src/types/mahjong.ts`

### Vite

依赖来源：

```json
"vite": "^6.2.0",
"@vitejs/plugin-react": "^5.0.4"
```

使用位置：

- `riichi-mahjong-ui/package.json`
- `riichi-mahjong-ui/vite.config.*`

承担职责：

- 前端开发服务器。
- React 构建。
- 输出生产静态资源到 `dist`。

常用命令：

```powershell
npm run dev
npm run build
npm run preview
```

### Tailwind CSS 4

依赖来源：

```json
"tailwindcss": "^4.1.14",
"@tailwindcss/vite": "^4.1.14"
```

使用位置：

- `riichi-mahjong-ui/src/index.css`
- `riichi-mahjong-ui/src/components/Mahjong/Table.tsx`
- 其他前端组件中的 `className`

承担职责：

- 快速组织玻璃拟态、渐变、圆角、阴影、布局和响应式样式。
- 让 Dock、面板、按钮、牌桌区域大多通过 class 维护。

### Framer Motion / Motion

依赖来源：

```json
"framer-motion": "^12.38.0",
"motion": "^12.23.24"
```

使用位置：

- `riichi-mahjong-ui/src/components/Mahjong/Table.tsx`

承担职责：

- 底部 macOS Dock 风格功能栏动效。
- 面板出现/关闭的平滑动画。
- 图标 hover 放大、邻近图标波浪式放大。
- 当前激活项高亮。

### react-riichi-mahjong-tiles

依赖来源：

```json
"react-riichi-mahjong-tiles": "^2.0.0"
```

使用位置：

- `riichi-mahjong-ui/src/components/Mahjong/MahjongTile.tsx`

承担职责：

- 渲染传统立直麻将牌面。
- 让 1索、9万、东南西北、中发白等显示为传统牌面，而不是纯文字。

项目在该库外层额外加了：

- 象牙白底座。
- 厚实立体边框。
- 阴影。
- 暗牌背面。
- 横置立直牌效果。

### Canvas

使用位置：

- `riichi-mahjong-ui/src/components/Mahjong/WaterBackground.tsx`

承担职责：

- 实时渲染牌桌水波背景。
- 提供流动光纹、波线和轻微动态质感。

性能注意：

- Canvas 动画如果帧率过高或绘制过重会导致网页卡顿。
- 已通过降低绘制复杂度、限制动画负担、减少 React 重渲染来优化。

### lucide-react

依赖来源：

```json
"lucide-react": "^0.546.0"
```

使用位置：

- `riichi-mahjong-ui/src/components/Mahjong/Table.tsx`

承担职责：

- Dock 图标。
- 面板和按钮中的轻量图标。

### Base UI / shadcn / class-variance-authority / clsx / tailwind-merge

依赖来源：

```json
"@base-ui/react": "^1.4.0",
"shadcn": "^4.2.0",
"class-variance-authority": "^0.7.1",
"clsx": "^2.1.1",
"tailwind-merge": "^3.5.0"
```

使用位置：

- `riichi-mahjong-ui/src/components/ui/*`
- `riichi-mahjong-ui/src/components/Mahjong/Table.tsx`

承担职责：

- 提供按钮、卡片、徽章等基础 UI 组件。
- 管理复杂 className 合并。
- 让 UI 样式更容易复用。

## 规则与 AI 技术

### 规则引擎

使用位置：

- `app/engine.py`

承担职责：

- 表示整局游戏状态。
- 生成合法动作。
- 校验动作是否合法。
- 推进回合。
- 处理结算。
- 生成公开状态给前端。

规则引擎是当前系统最重要的核心层。前端不直接判定规则，只根据后端返回的合法动作渲染按钮。

### 结构化 EV AI

使用位置：

- `app/engine.py`
- `riichi-mahjong-ui/src/types/mahjong.ts`
- `riichi-mahjong-ui/src/components/Mahjong/Table.tsx`

承担职责：

- 给每张候选弃牌计算综合价值。
- 给特殊操作计算是否推荐。
- 将 AI 的判断解释给行动提示面板。

当前 AI 主要评估维度：

- `speed_ev`：速度和向听推进。
- `value_ev`：打点潜力。
- `defense_ev`：危险度和放铳损失。
- `table_ev`：点棒、亲子、场况。
- `push_fold_ev`：押退判断。
- `lookahead_ev`：浅层前瞻。
- `alpha_search_ev`：更偏 AlphaJong 思路的局面搜索估计。
- `global_reward_ev`：终局排名收益估计。

### 对手建模

使用位置：

- `app/engine.py`

承担职责：

- 根据对手立直、副露、弃牌、可见牌、巡目推测威胁。
- 对每个对手估计危险度和可能失点。
- 在 AI 弃牌和特殊操作评估中加入风险来源。

当前对手建模仍是规则型，不是神经网络。

### 行动提示

使用位置：

- 后端：`app/engine.py`
- 类型：`riichi-mahjong-ui/src/types/mahjong.ts`
- UI：`riichi-mahjong-ui/src/components/Mahjong/Table.tsx`

承担职责：

- 把 AI 对当前巡目的分析展示给玩家。
- 不只提示弃牌，也提示碰、吃、杠、立直、自摸、荣和、拔北、九种九牌。
- 展示推荐程度、原因、路线和 EV 分解。

## 数据库与数据格式

### `games` 表

定义位置：

- `app/models.py`

主要字段：

- `id`
- `player_name`
- `mode`
- `round_length`
- `status`
- `summary_json`
- `state_json`
- `action_log_json`
- `snapshots_json`
- `result_json`
- `notes`
- `created_at`
- `updated_at`

### 为什么使用 JSON 字段

麻将对局状态非常复杂，包含：

- 多家手牌。
- 牌山。
- 副露。
- 牌河。
- 当前阶段。
- 合法动作。
- 立直、一发、振听、供托、本场等状态。
- 回放快照。
- 结算明细。

如果全部拆成关系表会显著增加维护成本。当前系统更适合用 JSON 保存完整状态，同时用少量索引字段支持历史列表和统计。

## 前后端通信

### 通信方式

前端使用浏览器 `fetch` 调用后端 JSON API。

典型流程：

1. 前端创建对局：`POST /api/games`。
2. 后端返回公开状态。
3. 前端渲染牌桌。
4. 玩家点击动作按钮。
5. 前端提交动作：`POST /api/games/{game_id}/actions`。
6. 后端推进玩家动作和 AI 动作。
7. 后端保存状态并返回新公开状态。
8. 前端更新 UI。

### 公开状态

公开状态由后端构造，前端只展示允许看到的信息。

例如：

- 自家能看到完整手牌。
- 其他玩家默认只看到暗牌数量。
- 荣和或结算时可显示其他玩家手牌。
- 合法动作由后端给出，前端不自行推断。

## 测试与质量保障

### Python 语法检查

使用命令：

```powershell
python -m py_compile app\engine.py app\main.py app\store.py tests\mahjong_soul_rule_audit.py
```

作用：

- 检查核心 Python 文件是否存在语法错误。

### 雀魂规则审计

使用命令：

```powershell
python tests\mahjong_soul_rule_audit.py
```

作用：

- 自动检查系统和雀魂/标准立直规则的对齐程度。
- 输出 `PASS/MISSING/FAIL`。
- 生成 JSON 审计报告。

### TypeScript 类型检查

使用命令：

```powershell
cd riichi-mahjong-ui
npm run lint
```

作用：

- 执行 `tsc --noEmit`。
- 检查前端类型错误。

### Vite 构建

使用命令：

```powershell
cd riichi-mahjong-ui
npm run build
```

作用：

- 检查前端是否能生产构建。
- 生成可由 FastAPI 托管的 `dist` 静态资源。

## 启动与部署技术

### PowerShell 启动脚本

使用位置：

- `start_mahjong_system.ps1`
- `stop_mahjong_system.ps1`

承担职责：

- 降低手动启动 MySQL 和 Uvicorn 的复杂度。
- 写入日志。
- 方便 Windows 本地运行。

### FastAPI 托管 React

使用位置：

- `app/main.py`

承担职责：

- 如果 `riichi-mahjong-ui/dist` 存在，直接返回 React 构建产物。
- 让用户只访问 `http://127.0.0.1:8000` 就能进入系统。

## 当前技术边界

### AI 不是机器学习模型

当前 AI 是规则型、EV 型、浅搜索型 AI，而不是 AlphaJong 那样依赖大量牌谱训练和深度模型的 AI。

它的优势：

- 可解释。
- 方便调试。
- 可以逐条按雀魂规则修正。
- 本地运行成本低。

它的限制：

- 对隐藏信息的估计不如训练模型。
- 对长期局面收益的判断仍然有限。
- 对复杂押退和读牌的精度不如强牌谱 AI。

### 前端是本地单页应用

当前前端更接近本地应用式 SPA，不是多人在线实时服务器。

如果未来要做在线多人，需要新增：

- 用户系统。
- 房间系统。
- WebSocket。
- 服务端权威同步。
- 断线重连。
- 防作弊。

## 维护路线建议

- 规则优先：任何规则修复都应补到 `tests/mahjong_soul_rule_audit.py`。
- 类型同步：后端公开状态新增字段后，要同步改 `src/types/mahjong.ts`。
- AI 可解释：新增 AI 维度时，要同步让行动提示面板显示原因。
- 性能优先：前端动画和 Canvas 改动后，要实际浏览器测试卡顿情况。
- 数据安全：不要提交 `.env`、本地数据库、日志和缓存。
