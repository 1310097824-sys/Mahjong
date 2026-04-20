# 单人立直麻将系统

这是一个基于 `FastAPI + React + MySQL` 的浏览器版单人立直麻将系统。项目目标是做一套本地可运行、界面接近网麻牌桌、规则逐步对齐雀魂/标准立直麻将的练习型麻将桌。

当前版本：`v1.1`

远程仓库：<https://github.com/1310097824-sys/Mahjong>

## v1.1 主要能力

- 浏览器牌桌前端，使用 React、TypeScript、Vite、Tailwind CSS 构建。
- FastAPI 后端，提供开局、行动、回放、历史对局、统计和规则审计相关接口。
- 默认使用 MySQL 保存历史对局、回放快照和玩家统计。
- 支持四麻、三麻、东风场、半庄战。
- 支持雀魂规则档位：段位默认、友人场、古役房。
- 支持三麻自摸损与北家点数折半分摊两种结算方式。
- 支持 L1 / L2 / L3 电脑强度。
- 支持牌谱回看、行动记录、历史对局删除、结算面板、支付明细、符数来源和役种展示。
- 前端牌桌使用传统麻将牌面，并加入象牙白底座、立体牌边、实时水波 Canvas 背景。
- 首页底部组件已改造成 macOS Dock 风格导航，点击图标会在牌桌附近展开对应操作面板。
- 行动提示已支持 EV 拆分、有效进张、危险来源、安全判断、牌型质量、预计打点和押退判断。
- AI 已从单步启发式逐步升级为结构化评估：速度 EV、打点 EV、防守 EV、局况 EV、形状质量、押退判断、对手威胁建模和 L3 前瞻。
- 三麻有效进张已过滤 2-8 万，避免出现三麻不存在牌种。

## 技术栈

后端：

- Python
- FastAPI
- SQLAlchemy
- PyMySQL
- mahjong 规则/算番库

前端：

- React 19
- TypeScript
- Vite
- Tailwind CSS
- Framer Motion
- lucide-react
- react-riichi-mahjong-tiles

数据库：

- MySQL 8 推荐
- 项目内仍保留 SQLite 迁移脚本，便于迁移旧数据

## 项目结构

```text
D:\py\Mahjong
├─ app
│  ├─ main.py              # FastAPI 入口
│  ├─ engine.py            # 麻将规则、AI、对局状态机
│  ├─ db.py                # 数据库连接
│  ├─ models.py            # 数据表模型
│  └─ store.py             # 存档、回放、统计读写
├─ riichi-mahjong-ui
│  ├─ src
│  │  └─ components/Mahjong # React 牌桌 UI
│  ├─ package.json
│  └─ vite.config.ts
├─ tests
│  └─ mahjong_soul_rule_audit.py
├─ start_mahjong_system.cmd
├─ stop_mahjong_system.cmd
├─ migrate_sqlite_to_mysql.py
└─ README.md
```

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
npm.cmd install --legacy-peer-deps
npm.cmd run build
```

说明：当前项目使用 React 19，但 `react-riichi-mahjong-tiles` 的 peer dependency 声明偏保守，所以推荐使用 `--legacy-peer-deps` 安装。

3. 启动后端：

```powershell
cd D:\py\Mahjong
D:\py\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir D:\py\Mahjong
```

## 前端开发模式

如果只调试 React 前端：

```powershell
cd D:\py\Mahjong\riichi-mahjong-ui
npm.cmd run dev
```

Vite 会把 `/api` 请求代理到本地 FastAPI 服务。

## MySQL 配置

项目读取根目录 `.env` 或环境变量。推荐配置：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的密码
MYSQL_DATABASE=mahjong
```

也可以直接设置：

```env
DATABASE_URL=mysql+pymysql://root:你的密码@127.0.0.1:3306/mahjong?charset=utf8mb4
```

首次启动时，后端会自动创建数据库和表结构。

如果需要从旧 SQLite 数据迁移：

```powershell
cd D:\py\Mahjong
D:\py\.venv\Scripts\python.exe migrate_sqlite_to_mysql.py
```

## 规则与 AI

当前规则目标是优先对齐雀魂在线规则，其次对齐标准立直麻将。系统已经覆盖的重点包括：

- 立直、两立直、一发、宝牌、里宝牌。
- 三麻拔北、三麻宝牌指示特殊处理。
- 三麻有效进张过滤 2-8 万。
- 流局、听牌、不听罚符、供托、本场。
- 荣和、自摸、多人荣和、包牌责任、役满/数え役满。
- 古役开关，默认不启用，古役房或友人场手动开启后生效。

AI 当前仍是可解释的规则型 AI，不是神经网络模型。L3 已经具备更完整的局面评估：

- 速度 EV：向听数、进张、前瞻路线。
- 打点 EV：宝牌、役牌、混一色/清一色、七对子、对对和等路线估值。
- 防守 EV：对立直/副露威胁的危险度、现物、筋、壁、字牌安全度。
- 局况 EV：点差、亲家、末局、守位/追分/避末位。
- 押退判断：胜负手全押、优势推进、边界半押、优先撤退、弃和守备。

## 规则审计

运行规则审计脚本：

```powershell
cd D:\py\Mahjong
D:\py\.venv\Scripts\python.exe tests\mahjong_soul_rule_audit.py
```

审计报告输出到：

```text
output\mahjong_soul_rule_audit.json
```

## 常用校验命令

后端语法检查：

```powershell
cd D:\py\Mahjong
D:\py\.venv\Scripts\python.exe -m py_compile app\engine.py
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

## 版本记录

- `v1.0`：完整可运行版本，包含浏览器牌桌、MySQL 存储、三麻/四麻、规则档位、牌谱回看、行动提示和规则审计。
- `v1.1`：加强规则与 AI，加入结构化 EV、押退判断、三麻合法进张修正、macOS Dock 风格底部导航、牌桌副露布局修正和前端交互优化。

## 注意事项

- `.env`、数据库文件、运行日志、缓存和 `node_modules` 不应提交到仓库。
- 如果 MySQL 无法启动，请优先检查 Windows 服务、端口 `3306`、数据目录权限和 `.env` 配置。
- 公开仓库中不要提交真实数据库密码或本地私有数据。
- 当前 AI 仍是规则型 AI，后续可以继续向牌谱学习、蒙特卡洛搜索或更深层对手建模方向升级。
