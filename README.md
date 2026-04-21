# 浏览器版立直麻将系统 v1.3

这是一个基于 `FastAPI + React + MySQL` 的本地浏览器版立直麻将练习系统。项目目标是做一套可单人游玩、界面接近网麻牌桌、规则持续对齐雀魂/标准立直麻将，并带有可解释 AI 行动提示的麻将系统。

## 当前能力

- 支持四麻与三麻，支持东风战与半庄战。
- 支持雀魂风格规则档位：段位默认、友人场、古役开关。
- 数据存储使用 MySQL，保留历史对局、回放、统计与删除历史对局能力。
- 前端使用 React、TypeScript、Vite、Tailwind CSS，浏览器直接访问牌桌。
- 牌桌 UI 已包含网麻牌桌比例、中心桌芯、牌河矩阵、副露展示、传统麻将牌面、象牙白牌底、底部 Dock 式功能入口。
- 支持 L1 / L2 / L3 电脑难度。
- 行动提示支持弃牌、立直、自摸、荣和、碰、吃、明杠、暗杠、加杠、拔北、九种九牌与过。
- AI 已具备结构化 EV：速度、打点、防守、局况、形状、押退、对手威胁、副露承诺、L3 浅层前瞻。
- 三麻已修正有效进张合法性，不会把 2 万到 8 万作为可摸入候选。

## 技术栈

- 后端：Python、FastAPI、SQLAlchemy、PyMySQL、mahjong。
- 前端：React 19、TypeScript、Vite、Tailwind CSS、Framer Motion、react-riichi-mahjong-tiles。
- 数据库：MySQL。
- 本地脚本：PowerShell / CMD 一键启动与关闭。

## 目录结构

```text
Mahjong/
├─ app/
│  ├─ main.py              # FastAPI 入口与 API 路由
│  ├─ engine.py            # 规则、对局状态机、AI 决策
│  ├─ db.py                # 数据库初始化
│  ├─ models.py            # SQLAlchemy 模型
│  └─ store.py             # 对局存取、统计、回放
├─ riichi-mahjong-ui/      # React 前端
├─ tests/                  # 规则审计与自动化测试脚本
├─ start_mahjong_system.ps1
├─ stop_mahjong_system.ps1
├─ requirements.txt
└─ README.md
```

## 环境准备

建议环境：

- Windows 10/11。
- Python 3.11 或更新版本。
- Node.js 18 或更新版本。
- MySQL 8，Windows 服务名默认按 `MySQL80` 处理。

安装后端依赖：

```powershell
cd D:\py\Mahjong
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

安装并构建前端：

```powershell
cd D:\py\Mahjong\riichi-mahjong-ui
npm.cmd install
npm.cmd run build
```

## MySQL 配置

创建数据库：

```sql
CREATE DATABASE IF NOT EXISTS mahjong
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

在项目根目录创建 `.env`。不要把 `.env` 提交到 Git。

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的本地密码
MYSQL_DATABASE=mahjong
MYSQL_CHARSET=utf8mb4
SECRET_KEY=mahjong-dev-secret
```

也可以直接使用完整连接串：

```env
DATABASE_URL=mysql+pymysql://root:你的本地密码@127.0.0.1:3306/mahjong?charset=utf8mb4
```

## 启动系统

推荐使用一键脚本：

```powershell
cd D:\py\Mahjong
.\start_mahjong_system.ps1
```

脚本会检查并尝试启动 `MySQL80`，然后启动 FastAPI 服务并打开浏览器。

关闭系统：

```powershell
cd D:\py\Mahjong
.\stop_mahjong_system.ps1
```

手动启动后端：

```powershell
cd D:\py\Mahjong
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir D:\py\Mahjong
```

浏览器访问：

```text
http://127.0.0.1:8000
```

前端开发模式：

```powershell
cd D:\py\Mahjong\riichi-mahjong-ui
npm.cmd run dev
```

## 规则与 AI

当前规则目标优先对齐雀魂在线规则，其次对齐标准立直麻将。已覆盖的重点包括：

- 四麻、三麻、东风、半庄。
- 立直、两立直、一发、门清自摸、荣和、自摸。
- 碰、吃、明杠、暗杠、加杠、抢杠、岭上、宝牌、里宝牌。
- 三麻拔北、三麻万子牌过滤、三麻自摸损/北家折半计分选项。
- 九种九牌、四风连打、四家立直、四杠散了、三家和等流局处理。
- 古役通过模式开关启用，默认以雀魂段位规则为准。

AI 当前是可解释规则型 AI，不是神经网络模型。v1.3 的 L3 重点增强如下：

- 弃牌使用结构化 EV：速度、打点、防守、局况、形状、押退、前瞻。
- 防守会结合对手立直、副露、现物、筋、壁、字牌安全度、预估失点。
- 鸣牌会检查是否有稳定和牌役，避免副露后无役。
- 碰、吃、明杠增加“副露承诺度”，会惩罚远手乱鸣、鸣后首打危险、鸣后进张少。
- 行动提示会显示特殊操作分析，包括为什么建议执行或建议跳过。
- L3 已有浅层前瞻，但还不是 AlphaJong 那种多巡模拟搜索。

大致强度预估：

- L1：入门级，保留明显失误和较弱防守。
- L2：普通练习级，能看向听、进张和部分风险。
- L3：规则型高阶练习 AI，约等于雀魂雀士高段到雀杰 1 附近，仍弱于成熟模拟搜索 AI。

## 常用 API

- `GET /api/health`：健康检查。
- `GET /api/games`：历史对局列表。
- `POST /api/games`：创建对局。
- `GET /api/games/{game_id}`：读取对局。
- `POST /api/games/{game_id}/actions`：执行行动。
- `DELETE /api/games/{game_id}`：删除历史对局。
- `GET /api/games/{game_id}/replay`：读取回放。
- `GET /api/stats/{player_name}`：读取玩家统计。

## 校验命令

后端语法检查：

```powershell
cd D:\py\Mahjong
.\.venv\Scripts\python.exe -m py_compile app\engine.py
```

雀魂规则审计：

```powershell
cd D:\py\Mahjong
.\.venv\Scripts\python.exe tests\mahjong_soul_rule_audit.py
```

前端类型检查：

```powershell
cd D:\py\Mahjong\riichi-mahjong-ui
npm.cmd run lint
```

前端生产构建：

```powershell
cd D:\py\Mahjong\riichi-mahjong-ui
npm.cmd run build
```

## v1.3 版本说明

- 保存当前系统为 v1.3。
- 重写 README，统一中文文档与运行说明。
- 继续强化 AI：加入副露承诺度、特殊操作“过”的分析、强制防守修正、特殊操作提示扩展。
- 前端行动提示显示特殊操作 EV、和牌路线稳定度、副露承诺与强防信息。
- 保留 v1.2 之前的浏览器牌桌、MySQL 存储、历史对局删除、回放、Dock 底部导航、传统牌面和雀魂风格桌芯。

## 后续路线

- 引入 AlphaJong 风格的多巡模拟搜索，但在 Python 后端中重写实现，避免直接复制 GPL 代码。
- 把 L3 从浅层前瞻升级为 2 巡 beam search。
- 继续增强对手模型：染手、役牌快攻、对对和、满贯级副露、追立/弃和判断。
- 用自动化对局统计和牌率、放铳率、平均打点、平均順位，按数据调参。

## 注意事项

- `.env`、数据库文件、日志、PID 文件、缓存、`node_modules` 不应提交。
- 公共仓库中不要提交真实数据库密码、本地私有数据或聊天下载文件。
- 如果 MySQL 无法启动，优先检查 Windows 服务 `MySQL80`、端口 `3306`、数据库目录权限和 `.env` 配置。
- 如果前端页面未更新，先执行 `npm.cmd run build`，再重新启动后端。
