# Browser Riichi Mahjong

基于文档实现的浏览器版单人立直麻将原型，采用 `FastAPI + Python` 后端和 `React + Vite` 前端。

当前版本重点覆盖：

- React 浏览器牌桌界面
- 四麻 / 三麻开局
- 单人对战，其余座位为 L1 / L2 / L3 AI
- 出牌、立直、荣和、自摸、吃、碰、杠、三麻拔北
- 动作日志、对局存档、基础回放
- 本地统计与历史对局列表

当前实现更偏 MVP，可直接运行试玩；更细的途中流局、振听边界和雀魂差异规则还可以继续补强。

## 运行

1. 安装 Python 依赖

```bash
python -m pip install -r requirements.txt
```

2. 安装 React 依赖

```bash
cd riichi-mahjong-ui
npm.cmd install
```

3. 构建 React 前端

```bash
npm.cmd run build
cd ..
```

4. 启动服务

```bash
uvicorn app.main:app --reload --app-dir D:\py\Mahjong
```

5. 打开浏览器

```text
http://127.0.0.1:8000
```

## One-Click Scripts

项目根目录提供了两个可双击的一键脚本：

```text
start_mahjong_system.cmd
stop_mahjong_system.cmd
```

- `start_mahjong_system.cmd`：检查 `MySQL80`，必要时请求管理员权限启动 MySQL，然后拉起后端并自动打开浏览器。
- `stop_mahjong_system.cmd`：关闭 8000 端口上的麻将后端进程，默认不停止 MySQL，避免影响其他项目。

## 前端开发模式

如果你想单独调 React 页面：

```bash
cd riichi-mahjong-ui
npm.cmd run dev
```

默认会通过 `Vite proxy` 把 `/api` 请求转发到 `http://127.0.0.1:8000`，所以本地调试时只要 FastAPI 服务同时开着即可。

## 数据库

当前后端默认使用 `MySQL`，优先读取以下环境变量：

```bash
set MYSQL_HOST=127.0.0.1
set MYSQL_PORT=3306
set MYSQL_USER=root
set MYSQL_PASSWORD=你的密码
set MYSQL_DATABASE=mahjong
```

也可以在项目根目录创建 `.env`，后端启动时会自动读取。

如果你更习惯一次性传完整连接串，也可以直接设置：

```bash
set DATABASE_URL=mysql+pymysql://root:password@127.0.0.1:3306/mahjong?charset=utf8mb4
```

首次启动时，后端会自动创建 `mahjong` 数据库和表结构。

如果你想把旧的 `mahjong.db` 历史对局迁到 MySQL：

```bash
python migrate_sqlite_to_mysql.py
```

## 说明

- 牌面未使用雀魂资源，前端采用 React 组件绘制的文本牌面以避免版权风险。
- AI 难度按文档要求实现到 `L1 / L2 / L3`：
  - `L1`：优先进张，偏随机
  - `L2`：向听数 + ukeire + 基础防守
  - `L3`：更强的攻守权衡、立直压力和副露节奏
- 回放基于动作快照，可用于本地复盘。
- 启动：D:\py\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir D:\py\Mahjong
