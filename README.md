# 浏览器版雀魂风格立直麻将系统 v1.4

这是一个基于 **Python FastAPI + React + MySQL** 的浏览器版立直麻将单人对战系统。项目目标是做出接近雀魂/标准立直麻将体验的本地可运行麻将系统：前端是浏览器牌桌，后端负责规则、AI、结算、历史对局和回放保存。

当前版本重点推进了两条主线：

- 规则侧继续向雀魂在线规则靠齐，覆盖四麻/三麻、东风/半庄、段位默认/友人场/古役房、赤宝牌数量、起和番数、三麻自摸损/北家折半等规则配置。
- AI 侧从简单权重打牌推进到结构化 EV、对手威胁建模、押退判断、特殊行动分析和浅层前瞻，让行动提示与电脑出牌更接近“网麻式思考”。

## 功能概览

- 浏览器牌桌：React + TypeScript 实现，支持牌桌、手牌、牌河、副露、宝牌、桌芯、结算、回放、历史对局、统计面板。
- 中文界面：主要界面文案、结算役种、符项、支付说明、行动提示均以中文展示。
- 传统牌面：使用 `react-riichi-mahjong-tiles` 展示传统麻将牌面，并在 UI 层加入象牙白底座与立体边框。
- 雀魂风格桌面：包含实时 Canvas 水波背景、机械感桌芯、四家/三家方位灯、中心十字牌河、底部 macOS Dock 风格功能栏。
- 规则模式：支持四麻/三麻、东风/半庄、段位默认、友人场、古役房。
- 规则选项：支持起和番数 1/2/4、赤宝牌 0/2/3/4、三麻自摸损/北家折半。
- 特殊操作：支持吃、碰、明杠、暗杠、加杠、立直、自摸、荣和、拔北、九种九牌等常见操作。
- AI 难度：支持 L1/L2/L3，难度差异体现在随机性、局面评估深度、防守意识、前瞻和押退判断。
- AI 行动提示：对弃牌和特殊操作输出结构化分析，包括进张、风险、打点、押退、路线、最终 EV 等信息。
- 对局保存：使用 MySQL 保存对局状态、摘要、操作日志、回放快照和结算结果。
- 历史与回放：支持查看历史对局、删除历史对局、回放关键快照。
- 自动化审计：提供雀魂规则对齐审计脚本，当前审计覆盖多响、供托、三麻、拔北、古役、赤宝牌等规则点。

## 项目结构

```text
Mahjong/
├─ app/                         # FastAPI 后端与麻将规则引擎
│  ├─ config.py                  # 环境变量、数据库连接、默认配置
│  ├─ db.py                      # SQLAlchemy 引擎、会话、MySQL 数据库初始化
│  ├─ engine.py                  # 核心麻将规则、AI、结算、动作推进
│  ├─ main.py                    # FastAPI API、静态资源托管、前端入口
│  ├─ models.py                  # SQLAlchemy 对局记录模型
│  ├─ store.py                   # 对局持久化、历史、回放、统计
│  ├─ static/                    # 旧版静态前端兜底资源
│  └─ templates/                 # 旧版模板兜底入口
├─ riichi-mahjong-ui/            # React + TypeScript 前端
│  ├─ src/App.tsx                # 前端应用入口
│  ├─ src/components/Mahjong/    # 牌桌、手牌、牌河、麻将牌、水波背景
│  ├─ src/types/mahjong.ts       # 前后端数据类型定义
│  └─ package.json               # 前端依赖和脚本
├─ tests/
│  └─ mahjong_soul_rule_audit.py # 雀魂规则对齐审计脚本
├─ logic.md                      # 打牌逻辑与 AI 最优解计算说明
├─ programingsign.md             # 项目结构与文件职责说明
├─ tech.md                       # 技术栈与使用位置说明
├─ requirements.txt              # Python 后端依赖
├─ start_mahjong_system.ps1      # Windows 一键启动脚本
├─ stop_mahjong_system.ps1       # Windows 一键关闭脚本
└─ migrate_sqlite_to_mysql.py    # 历史 SQLite 数据迁移到 MySQL
```

更详细的文件职责请看 [programingsign.md](programingsign.md)，技术栈说明请看 [tech.md](tech.md)，规则和 AI 逻辑请看 [logic.md](logic.md)。

## 快速启动

### 1. 后端环境

建议在项目外层或当前项目中使用虚拟环境。示例：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

如果你的虚拟环境在 `D:\py\.venv`，也可以直接复用现有环境。

### 2. MySQL 配置

项目默认使用 MySQL，不再以 SQLite 作为主数据库。根目录 `.env` 可配置：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=mahjong
MYSQL_CHARSET=utf8mb4
```

也可以直接设置完整连接串：

```env
DATABASE_URL=mysql+pymysql://root:123456@127.0.0.1:3306/mahjong?charset=utf8mb4
```

后端启动时会尝试创建数据库和数据表。

### 3. 前端依赖与构建

```powershell
cd riichi-mahjong-ui
npm install
npm run build
cd ..
```

构建产物会输出到 `riichi-mahjong-ui/dist`，FastAPI 会优先托管该 React 构建结果。

### 4. 一键启动

```powershell
.\start_mahjong_system.ps1
```

启动后访问：

```text
http://127.0.0.1:8000
```

关闭系统：

```powershell
.\stop_mahjong_system.ps1
```

如果只想手动启动后端：

```powershell
uvicorn app.main:app --reload
```

## 主要 API

- `GET /`：返回 React 前端页面。
- `GET /api/health`：健康检查。
- `GET /api/games`：读取历史对局列表。
- `GET /api/games/{game_id}`：读取指定对局当前公开状态。
- `DELETE /api/games/{game_id}`：删除历史对局。
- `POST /api/games`：创建新对局。
- `POST /api/games/{game_id}/actions`：提交出牌或特殊操作。
- `GET /api/games/{game_id}/replay`：读取回放快照。
- `GET /api/stats/{player_name}`：读取玩家统计。

## 规则与 AI

核心逻辑集中在 `app/engine.py`：

- 牌山、摸牌、弃牌、吃碰杠、立直、拔北、流局、连庄、供托、本场、结算都在后端推进。
- 和牌判断与役种识别结合 `mahjong` 库和项目内补充逻辑。
- 雀魂规则对齐通过 `tests/mahjong_soul_rule_audit.py` 持续审计。
- AI 当前采用可解释规则型思路，不是神经网络模型。
- AI 决策会综合速度 EV、打点 EV、防守 EV、局况 EV、押退 EV、对手威胁和浅层前瞻。
- 行动提示面板复用 AI 评估结果，展示弃牌和特殊操作的推荐原因。

如果要继续向 AlphaJong/强网麻 AI 方向推进，优先方向是：更强的局面价值网络、更真实的对手手牌分布估计、更深的蒙特卡洛/搜索、更完整的牌谱训练数据管线。

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

## v1.4 版本重点

- 补充项目结构文档 `programingsign.md`。
- 补充技术栈解析文档 `tech.md`。
- 重写 README，让安装、启动、规则、AI、测试和维护路径更清晰。
- 当前系统继续保留 MySQL 持久化、React 牌桌、Dock 面板、规则审计和结构化 AI 提示。
- 当前版本作为 `v1.4` 提交并推送到远程仓库。

## 注意事项

- `.env`、日志、数据库文件、构建缓存、`node_modules` 不应提交到 Git。
- `mahjong.db` 是历史 SQLite 数据文件，当前主流程使用 MySQL。
- 如果 MySQL 重启后无法启动，优先检查是否存在游离 `mysqld.exe`、端口占用、数据目录锁文件或权限问题。
- 如果页面出现旧资源，先重新执行 `npm run build`，再重启 FastAPI。
