# 单人立直麻将

基于 `FastAPI + React + MySQL` 的浏览器版单人立直麻将系统。项目目标是做一套本地可运行的雀魂风格立直麻将练习桌，支持三麻、四麻、牌谱回看、历史对局、规则审计和 L1/L2/L3 电脑对手。

当前版本已推送为 `v1.0`，远程仓库：

https://github.com/1310097824-sys/Mahjong

## 功能特性

- 浏览器前端牌桌，使用 React + Vite 构建。
- FastAPI 后端，提供开局、操作、回放、历史对局和统计接口。
- 默认使用 MySQL 保存历史对局、回放快照和统计数据。
- 支持四麻、三麻、东风场、半庄战。
- 支持雀魂规则档位：段位默认、友人场、古役房。
- 支持三麻 `自摸损` 与 `北家点数折半分摊` 两种结算方式。
- 支持 L1/L2/L3 电脑强度。
- 支持牌谱回看、动作记录、结算面板、支付明细和符数来源展示。
- 支持行动提示，结合向听、真实可见牌进张、风险、副露威胁和手役路线做推荐。
- 内置雀魂规则自动化审计脚本。

## 技术栈

- 后端：Python、FastAPI、SQLAlchemy、PyMySQL
- 前端：React、TypeScript、Vite、Tailwind CSS
- 数据库：MySQL 8
- 规则与算番：Python 立直麻将相关库 + 项目内规则状态机

## 快速启动

推荐直接使用一键脚本：

```powershell
D:\py\Mahjong\start_mahjong_system.cmd
```

停止系统：

```powershell
D:\py\Mahjong\stop_mahjong_system.cmd
```

启动后打开：

```text
http://127.0.0.1:8000
```

## 手动启动

1. 安装后端依赖：

```powershell
cd D:\py\Mahjong
D:\py\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

2. 安装并构建前端：

```powershell
cd D:\py\Mahjong\riichi-mahjong-ui
npm.cmd install
npm.cmd run build
```

3. 启动后端：

```powershell
cd D:\py\Mahjong
D:\py\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir D:\py\Mahjong
```

## 数据库配置

项目默认读取根目录 `.env` 或环境变量：

```powershell
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的密码
MYSQL_DATABASE=mahjong
```

也可以直接设置：

```powershell
DATABASE_URL=mysql+pymysql://root:password@127.0.0.1:3306/mahjong?charset=utf8mb4
```

首次启动时，后端会自动创建数据库和表结构。

如果需要从旧的 SQLite 数据迁移：

```powershell
cd D:\py\Mahjong
D:\py\.venv\Scripts\python.exe migrate_sqlite_to_mysql.py
```

## 前端开发

如果只调试 React 前端：

```powershell
cd D:\py\Mahjong\riichi-mahjong-ui
npm.cmd run dev
```

Vite 会把 `/api` 请求代理到本地 FastAPI 服务。

## 规则审计

项目提供雀魂规则自动化审计脚本：

```powershell
cd D:\py\Mahjong
D:\py\.venv\Scripts\python.exe tests\mahjong_soul_rule_audit.py
```

审计报告输出到：

```text
output\mahjong_soul_rule_audit.json
```

## 版本

- `v1.0`：当前完整可运行版本，包含浏览器牌桌、MySQL 存储、三麻/四麻、规则档位、牌谱回看、行动提示和规则审计。

## 注意事项

- `.env`、数据库文件、运行日志、缓存和 `node_modules` 已通过 `.gitignore` 排除。
- 如果 MySQL 无法启动，请优先检查 `MySQL80` 服务状态和数据目录权限。
- 当前 AI 仍是可解释的规则型 AI，并非神经网络模型。后续可以继续往 EV 分解、对手模型和多巡前瞻方向升级。
