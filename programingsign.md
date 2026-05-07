# 项目结构与文件职责说明

本文档用于说明当前麻将系统的目录结构、主要文件职责，以及各模块之间如何协作。文件名 `programingsign.md` 按当前项目要求保留。

## 总体结构

```text
Mahjong/
├─ app/                  # Python FastAPI 后端、规则引擎、数据库访问
├─ riichi-mahjong-ui/    # React + TypeScript 浏览器前端
├─ tests/                # 自动化规则审计脚本
├─ output/               # 审计输出等生成物，通常不提交
├─ sometxt/              # 过程资料或临时文本资料
├─ .agents/              # Codex/Agent 技能与项目辅助配置
├─ .playwright-cli/      # 浏览器自动化缓存目录，通常不提交
├─ README.md             # 项目入口说明
├─ logic.md              # 打牌逻辑与 AI 决策过程说明
├─ tech.md               # 技术栈与技术使用位置说明
└─ programingsign.md     # 本文件，说明项目结构和文件职责
```

系统采用前后端分离但同域部署的方式：

- 后端 `app/main.py` 提供 API，并在生产模式下托管 React 构建后的静态文件。
- 前端 `riichi-mahjong-ui` 通过 `fetch` 调用 `/api/...` 接口。
- 规则、AI、结算、对局推进都在后端 `app/engine.py` 中完成。
- 对局历史、回放快照和统计通过 `app/store.py` 写入 MySQL。

## 根目录文件

### `.env`

本地环境变量配置文件，主要保存 MySQL 连接信息，例如：

- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`
- `DATABASE_URL`

该文件包含本地敏感配置，不应提交到 Git。

### `.gitignore`

Git 忽略规则，当前主要忽略：

- `.env`
- `mahjong.db`
- 日志文件
- Python 缓存
- Playwright 缓存
- 审计输出目录
- 前端 `node_modules`

### `README.md`

项目入口文档，说明系统功能、快速启动、主要 API、规则 AI、测试验证和版本重点。

### `logic.md`

打牌逻辑与 AI 行动逻辑说明文档。它解释：

- 一局牌如何推进。
- 玩家动作如何进入后端。
- AI 如何评估弃牌。
- AI 如何评估吃碰杠、立直、自摸、荣和、拔北、九种九牌。
- 当前“最优解”不是神经网络结果，而是结构化 EV 与规则型搜索的综合判断。

### `tech.md`

技术栈解析文档。它说明项目使用了哪些技术、这些技术分别用在哪里、承担什么职责。

### `programingsign.md`

当前文件，用于说明项目目录结构和每个文件的职责。

### `requirements.txt`

Python 后端依赖列表，包含：

- FastAPI
- Uvicorn
- SQLAlchemy
- PyMySQL
- mahjong
- pypdf
- httpx

### `start_mahjong_system.ps1`

Windows PowerShell 一键启动脚本。它用于启动当前麻将系统所需的本地服务，通常包括：

- 检查或启动 MySQL。
- 启动 FastAPI/Uvicorn。
- 输出访问地址和日志位置。

### `start_mahjong_system.cmd`

CMD 包装脚本，方便双击或在传统命令行中调用 PowerShell 启动脚本。

### `stop_mahjong_system.ps1`

Windows PowerShell 一键关闭脚本。它用于停止系统启动脚本拉起的后端服务，必要时也会辅助处理残留进程。

### `stop_mahjong_system.cmd`

CMD 包装脚本，方便双击或在传统命令行中调用 PowerShell 关闭脚本。

### `migrate_sqlite_to_mysql.py`

历史迁移脚本，用于把旧版 SQLite 数据迁移到当前 MySQL 数据库。

### `mahjong.db`

旧版 SQLite 数据库文件。当前主系统已经切换到 MySQL，该文件主要用于历史数据或迁移场景，不建议继续作为主数据库使用。

### `spec.pdf` / `spec.txt`

早期需求或实施方案资料。`spec.txt` 是可直接检索的文本版本，`spec.pdf` 是原始方案文件。

### `riichi-mahjong-ui.zip`

前端项目压缩包或历史备份文件，不参与当前运行链路。

### 日志文件

根目录下的 `*.log`、`*.err.log`、`*.out.log` 主要来自本地启动、Uvicorn 或 MySQL 调试过程。它们用于排查本机运行问题，不属于源代码。

### `2003.13590v2.pdf`

当前工作区中存在的未跟踪 PDF 文件。它看起来像外部论文或参考资料，不属于本系统运行链路，默认不提交。

## `app/` 后端目录

### `app/__init__.py`

Python 包标识文件，让 `app` 可以被 `uvicorn app.main:app` 正确导入。

### `app/config.py`

项目配置模块，负责：

- 读取根目录 `.env`。
- 从环境变量构造 MySQL 连接串。
- 定义默认起点、回放快照保留数量等设置。
- 提供全局 `settings` 对象。

后端数据库、启动流程和持久化模块都会间接依赖这里的配置。

### `app/db.py`

数据库连接模块，负责：

- 创建 SQLAlchemy `engine`。
- 创建 `SessionLocal`。
- 定义 ORM 基类 `Base`。
- 在 MySQL 中自动创建目标数据库。
- 初始化数据表。

它是 `models.py` 和 `store.py` 与 MySQL 沟通的基础。

### `app/models.py`

数据库模型定义，目前核心模型是 `GameRecord`。

`GameRecord` 对应 `games` 表，保存：

- 对局 ID。
- 玩家名。
- 模式和局长。
- 当前状态。
- 对局摘要 JSON。
- 完整状态 JSON。
- 操作日志 JSON。
- 回放快照 JSON。
- 结算结果 JSON。
- 创建与更新时间。

### `app/store.py`

对局存储层，负责把规则引擎产生的状态保存到数据库，并向 API 层提供查询能力。

主要职责：

- 新建对局记录。
- 保存当前状态。
- 保存操作日志。
- 保存回放快照。
- 查询历史对局列表。
- 查询指定对局。
- 删除历史对局。
- 读取回放。
- 统计玩家战绩。

`main.py` 不直接操作数据库，而是通过 `store.py` 完成持久化。

### `app/main.py`

FastAPI 应用入口。主要职责：

- 创建 `FastAPI` 应用。
- 配置 CORS。
- 在启动时初始化数据库。
- 托管旧版静态资源和 React 构建资源。
- 暴露游戏 API。

核心 API 包括：

- `GET /`
- `GET /api/health`
- `GET /api/games`
- `GET /api/games/{game_id}`
- `DELETE /api/games/{game_id}`
- `POST /api/games`
- `POST /api/games/{game_id}/actions`
- `GET /api/games/{game_id}/replay`
- `GET /api/stats/{player_name}`

### `app/engine.py`

系统最核心文件，包含麻将规则、AI 和状态推进逻辑。

主要职责：

- 生成四麻/三麻牌山。
- 处理三麻去除 2-8 万。
- 发牌、摸牌、补岭上牌。
- 计算宝牌、里宝牌、赤宝牌、拔北宝牌。
- 构建合法动作。
- 执行弃牌、吃、碰、杠、立直、自摸、荣和、拔北、九种九牌。
- 判断振听、一发、两立直、海底、河底、抢杠、岭上等状态。
- 判断荒牌流局、途中流局、流局满贯。
- 处理本场、供托、连庄、终局、延长战。
- 计算和牌役种、符、番、点数和支付。
- 构造前端公开状态。
- 生成 AI 决策与行动提示。

AI 相关重点函数集中在：

- `discard_profile(...)`：对候选弃牌做结构化评估。
- `should_call_open(...)`：AI 对鸣牌的判断入口之一。
- `choose_ai_turn_action(...)`：AI 自家回合的行动选择。
- 特殊操作评估函数：用于碰、吃、杠、立直、自摸、荣和、拔北等提示和决策。

### `app/static/`

旧版静态前端资源目录，包含：

- `app.js`
- `styles.css`

当前主前端已经迁移到 React，但这个目录仍可作为兜底或历史版本参考。

### `app/templates/`

旧版模板目录，包含：

- `index.html`

当前 `main.py` 会优先返回 React 构建结果；如果构建产物不存在，可以回退到旧模板。

## `riichi-mahjong-ui/` 前端目录

### `riichi-mahjong-ui/package.json`

前端依赖与脚本配置。

常用脚本：

- `npm run dev`：启动 Vite 开发服务器。
- `npm run build`：构建生产静态资源。
- `npm run preview`：预览构建结果。
- `npm run lint`：运行 TypeScript 类型检查。

### `riichi-mahjong-ui/src/main.tsx`

React 入口文件，负责把 `App` 挂载到页面根节点。

### `riichi-mahjong-ui/src/App.tsx`

前端应用根组件。当前主要渲染 `Table`，也就是麻将桌主界面。

### `riichi-mahjong-ui/src/index.css`

全局样式入口。主要包含：

- Tailwind CSS 引入。
- 全局背景、字体、滚动条。
- 麻将牌、牌桌、Dock、面板、结算等全局样式。
- 深色视觉基调与特效样式。

### `riichi-mahjong-ui/src/types/mahjong.ts`

前后端数据结构 TypeScript 类型定义。它约束：

- 牌类型。
- 玩家公开状态。
- 副露。
- 牌河。
- 合法动作。
- 行动提示。
- 结算结果。
- 回放快照。
- 历史记录。
- 玩家统计。

这是前端保持类型安全的关键文件。

### `riichi-mahjong-ui/src/components/Mahjong/Table.tsx`

前端主组件，也是 UI 复杂度最高的文件。主要职责：

- 创建新对局。
- 拉取当前对局状态。
- 提交玩家操作。
- 自动推进 AI 行动。
- 控制 AI 出牌延迟。
- 渲染牌桌布局。
- 渲染四家/三家玩家区域。
- 渲染手牌、牌河、副露、宝牌、桌芯、结算。
- 渲染底部 Dock 与弹出面板。
- 渲染历史对局、回放、统计、行动提示、设置等功能。
- 将后端英文/内部字段转换成中文 UI 文案。

### `riichi-mahjong-ui/src/components/Mahjong/Hand.tsx`

手牌组件，负责按不同方位展示玩家手牌：

- 自家正向手牌。
- 对家横向暗牌。
- 左右家竖向暗牌。
- 终局或荣和后可展示其他玩家手牌。

### `riichi-mahjong-ui/src/components/Mahjong/MahjongTile.tsx`

单张麻将牌组件。负责：

- 把后端牌标签转换成传统麻将牌面。
- 使用 `react-riichi-mahjong-tiles` 渲染牌面。
- 添加象牙白底座、厚边框、阴影和立体感。
- 处理暗牌、横置立直牌、不同尺寸和不同方位。

### `riichi-mahjong-ui/src/components/Mahjong/River.tsx`

牌河组件，负责渲染各家的弃牌矩阵。

当前目标是让四家牌河靠近桌心、形成规整的中心十字布局，并支持：

- 立直宣言牌横置。
- 被鸣走弃牌标识。
- 不同方位的旋转和排布。

### `riichi-mahjong-ui/src/components/Mahjong/WaterBackground.tsx`

Canvas 实时水波背景组件。负责在牌桌底层绘制动态流水纹理，让桌面更接近网麻牌桌的流动质感。

## `tests/` 测试目录

### `tests/mahjong_soul_rule_audit.py`

雀魂规则对齐审计脚本。它不是普通单元测试集合，而是一份面向规则缺口的自动化清单。

当前覆盖方向包括：

- 四麻/三麻起点和目标点。
- 多响与供托归属。
- 荒牌、途中流局、流局满贯。
- 副露听牌计算。
- 振听。
- 立直宣言牌被鸣。
- 杠宝牌翻开时机。
- 四杠散了。
- 海底前限制。
- 三麻自摸损和本场。
- 三麻禁吃。
- 三麻 1万宝牌指示牌适配。
- 三麻有效进张排除 2-8 万。
- 拔北、一发、两立直、荣和拔北。
- 古役房役种。
- 规则档位。
- 起和番数。
- 赤宝牌数量。

脚本会输出 `PASS/MISSING/FAIL` 统计，并将审计报告写入 `output/mahjong_soul_rule_audit.json`。

## 生成物与缓存

### `output/`

审计报告和其他运行生成物目录，通常由脚本生成，不提交到 Git。

### `__pycache__/`

Python 字节码缓存目录，不属于源代码。

### `riichi-mahjong-ui/node_modules/`

前端依赖目录，由 `npm install` 生成，不提交到 Git。

### `riichi-mahjong-ui/dist/`

前端生产构建产物，由 `npm run build` 生成。FastAPI 会优先托管该目录。是否提交取决于部署策略；当前项目主要保留源码构建方式。

## 运行链路

1. 用户访问 `http://127.0.0.1:8000`。
2. `app/main.py` 返回 React 页面。
3. React `Table.tsx` 请求 `/api/games` 或创建新对局。
4. `main.py` 调用 `engine.py` 创建或推进游戏。
5. `engine.py` 返回公开状态。
6. `store.py` 将状态、日志和快照保存到 MySQL。
7. 前端根据公开状态渲染牌桌、动作按钮和行动提示。
8. 玩家点击动作按钮后，前端把动作 ID POST 到后端。
9. 后端执行动作并自动推进 AI，返回新的公开状态。

## 维护建议

- 改规则优先看 `app/engine.py`，再补 `tests/mahjong_soul_rule_audit.py`。
- 改界面优先看 `riichi-mahjong-ui/src/components/Mahjong/Table.tsx` 和 `index.css`。
- 改数据结构时同步修改 `app/engine.py` 的公开状态和 `src/types/mahjong.ts`。
- 改持久化时同步检查 `app/models.py` 与 `app/store.py`。
- 每次规则变更后运行 `python tests\mahjong_soul_rule_audit.py`。
- 每次前端变更后运行 `npm run lint` 和 `npm run build`。
