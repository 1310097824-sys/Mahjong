# 数据库使用说明

更新时间：2026-05-07

本文档说明当前系统中 `SQLAlchemy + PyMySQL + MySQL` 的使用方式，以及当前 MySQL 数据库、表结构和各字段作用。

## 1. 总体结论

当前系统使用 MySQL 作为主数据库，后端通过 SQLAlchemy 操作数据库，底层连接驱动使用 PyMySQL。

当前实际连接信息：

| 项目 | 当前值 |
| --- | --- |
| 数据库类型 | MySQL |
| Python 驱动 | PyMySQL |
| ORM / 连接管理 | SQLAlchemy |
| 主数据库名 | `mahjong` |
| 地址 | `127.0.0.1:3306` |
| 默认用户 | `root` |
| 字符集 | `utf8mb4` |
| 当前业务表数量 | 1 |
| 当前业务表 | `games` |

当前系统采用“关系型表 + JSON 文档”的方式保存牌局。也就是说，MySQL 里目前没有把每张牌、每次动作、每个玩家都拆成独立关系表，而是把完整对局状态、操作日志、回放快照和结算结果放进 `games` 表的 JSON 字段中。

## 2. SQLAlchemy、PyMySQL、MySQL 分别负责什么

### MySQL

MySQL 是真正保存数据的数据库服务。

当前系统用它保存：

- 历史对局。
- 当前进行中的对局状态。
- 已完成对局的结算结果。
- 操作日志。
- 回放快照。
- 玩家统计所需的历史数据。

### PyMySQL

PyMySQL 是 Python 连接 MySQL 的驱动。

项目里不会直接大量调用 PyMySQL API，而是通过 SQLAlchemy 的连接串间接使用：

```text
mysql+pymysql://root:123456@127.0.0.1:3306/mahjong?charset=utf8mb4
```

其中 `mysql+pymysql` 表示：

- 数据库方言是 MySQL。
- 连接驱动使用 PyMySQL。

### SQLAlchemy

SQLAlchemy 是上层 ORM 和数据库连接管理层。

项目通过 SQLAlchemy 完成：

- 创建数据库连接引擎。
- 管理连接池。
- 创建 Session。
- 定义 ORM 表模型。
- 自动创建表。
- 查询、插入、更新、删除对局记录。

## 3. 数据库配置入口

配置入口位于：

```text
app/config.py
```

系统会优先读取根目录 `.env`，再读取系统环境变量。

常用配置项：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=mahjong
MYSQL_CHARSET=utf8mb4
```

如果设置了 `DATABASE_URL`，系统会优先使用完整连接串：

```env
DATABASE_URL=mysql+pymysql://root:123456@127.0.0.1:3306/mahjong?charset=utf8mb4
```

如果没有设置 `DATABASE_URL`，系统会根据 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE` 和 `MYSQL_CHARSET` 自动拼出连接串。

## 4. 数据库初始化流程

初始化入口位于：

```text
app/db.py
```

核心流程：

1. 读取 `settings.database_url`。
2. 判断当前连接是否为 MySQL。
3. 如果是 MySQL，则先连接到 MySQL 服务本身。
4. 执行 `CREATE DATABASE IF NOT EXISTS mahjong`。
5. 使用 `utf8mb4` 字符集和 `utf8mb4_unicode_ci` 排序规则。
6. 创建 SQLAlchemy engine。
7. 创建 `SessionLocal`。
8. FastAPI 启动时调用 `init_db()`。
9. `Base.metadata.create_all(bind=engine)` 根据 ORM 模型创建表。

MySQL 专用连接池配置：

| 配置 | 作用 |
| --- | --- |
| `pool_pre_ping=True` | 每次取连接前先检测连接是否有效，减少 MySQL 断开空闲连接导致的报错 |
| `pool_recycle=3600` | 连接超过 3600 秒后回收重建，降低长时间运行后的连接失效概率 |

## 5. 当前 MySQL 数据库

当前系统实际使用的数据库名是：

```text
mahjong
```

当前数据库中实际业务表数量：

```text
1
```

当前业务表：

```text
games
```

当前记录数检查时为：

```text
26
```

记录数会随着你创建、完成、删除历史对局而变化。

## 6. `games` 表作用

`games` 是当前系统唯一的业务表。

ORM 定义位置：

```text
app/models.py
```

它负责保存一整局麻将对局的全部持久化数据，包括：

- 历史列表摘要。
- 完整游戏状态。
- 操作日志。
- 回放快照。
- 终局结算。
- 玩家统计所需数据。

## 7. `games` 表字段说明

| 字段 | 类型 | 是否可空 | 作用 |
| --- | --- | --- | --- |
| `id` | `varchar(36)` | 否 | 对局 ID，主键，对应后端 `game_id` |
| `player_name` | `varchar(32)` | 否 | 玩家名，用于历史显示和玩家统计 |
| `mode` | `varchar(2)` | 否 | 对局模式，通常是 `3P` 或 `4P` |
| `round_length` | `varchar(8)` | 否 | 场次长度，通常是 `EAST` 或 `HANCHAN` |
| `status` | `varchar(16)` | 否 | 对局状态，如 `RUNNING` 或 `FINISHED` |
| `summary_json` | `json` | 否 | 历史列表用的轻量摘要 |
| `state_json` | `json` | 否 | 完整对局状态，用于恢复牌局 |
| `action_log_json` | `json` | 否 | 操作日志，用于记录整局动作 |
| `snapshots_json` | `json` | 否 | 回放快照，用于牌谱回看 |
| `result_json` | `json` | 是 | 终局结算结果 |
| `notes` | `text` | 否 | 预留备注字段 |
| `created_at` | `datetime` | 否 | 记录创建时间 |
| `updated_at` | `datetime` | 否 | 记录更新时间 |

## 8. `games` 表索引

| 索引 | 字段 | 作用 |
| --- | --- | --- |
| `PRIMARY` | `id` | 按对局 ID 精确读取、更新、删除 |
| `ix_games_player_name` | `player_name` | 玩家统计和按玩家筛选时使用 |
| `ix_games_mode` | `mode` | 按三麻/四麻筛选时使用 |
| `ix_games_status` | `status` | 区分进行中和已完成对局，统计已完成对局时使用 |

## 9. `games` 表的实际建表结构

当前 MySQL 中 `games` 表结构等价于：

```sql
CREATE TABLE `games` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `player_name` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `mode` varchar(2) COLLATE utf8mb4_unicode_ci NOT NULL,
  `round_length` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `summary_json` json NOT NULL,
  `state_json` json NOT NULL,
  `action_log_json` json NOT NULL,
  `snapshots_json` json NOT NULL,
  `result_json` json DEFAULT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_games_player_name` (`player_name`),
  KEY `ix_games_mode` (`mode`),
  KEY `ix_games_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

## 10. 主要 JSON 字段存什么

### `summary_json`

用于历史对局列表和轻量展示。

通常包含：

- `game_id`
- `player_name`
- `mode`
- `round_length`
- `rule_profile`
- `minimum_han`
- `aka_dora_count`
- `sanma_scoring_mode`
- `status`
- `round_label`
- `updated_at`
- `points`
- `placements`

读取历史列表时只查这个字段，避免把完整游戏状态一起加载出来。

### `state_json`

保存完整对局状态，是恢复牌局的核心字段。

通常包含：

- 对局基础信息。
- 当前局状态。
- 各家点数。
- 手牌。
- 副露。
- 牌河。
- 宝牌指示牌。
- 当前回合。
- 合法动作。
- AI 提示。
- 结算状态。

读取某个对局继续游玩时，后端会主要依赖这个字段。

### `action_log_json`

保存整局动作日志。

通常记录：

- 摸牌。
- 弃牌。
- 吃。
- 碰。
- 明杠。
- 暗杠。
- 加杠。
- 立直。
- 自摸。
- 荣和。
- 拔北。
- 流局。
- 结算。

### `snapshots_json`

保存回放快照。

回放不是每次重新推导整局，而是读取这些快照来展示关键时刻的牌桌状态。

### `result_json`

保存终局结算结果。

通常包含：

- 排名。
- 最终点数。
- 和牌者。
- 放铳者。
- 支付构成。
- 役种。
- 符番。
- 本场、供托等结算信息。

如果对局还没有结束，该字段可能为 `null`。

## 11. 代码里如何读写数据库

数据库读写集中在：

```text
app/store.py
```

### `save_game()`

保存对局。

如果 `games.id` 对应记录不存在，则插入新记录；如果已存在，则更新记录。

写入内容包括：

- `summary_json`
- `state_json`
- `action_log_json`
- `snapshots_json`
- `result_json`
- `updated_at`

### `load_game()`

按 `game_id` 读取 `state_json`。

用于：

- 继续当前对局。
- 前端刷新后恢复牌局。
- 提交动作前读取最新状态。

### `delete_game()`

按 `game_id` 删除对局记录。

对应前端的删除历史对局功能。

### `list_games()`

读取最近历史对局列表。

它只查询 `summary_json`，并按 `updated_at` 倒序排列。

这样历史列表加载更轻，不需要一次性读取完整牌局 JSON。

### `get_replay()`

读取回放数据。

返回：

- `snapshots_json`
- `action_log_json`
- `result_json`

读取回放时会把快照中的 `hint` 清掉，避免回放里重复显示实时 AI 提示。

### `get_player_stats()`

读取玩家统计。

它查询：

- `player_name`
- `status = FINISHED`
- `summary_json`
- `result_json`

然后从结算排名中统计：

- 对局数。
- 一位次数。
- 平均顺位。
- 最高分。
- 被忽略的异常旧记录数。

当前还兼容旧版本默认玩家名 `Guest` 和新版本 `访客`。

## 12. API 如何触发数据库操作

API 入口位于：

```text
app/main.py
```

| API | 调用的数据库方法 | 作用 |
| --- | --- | --- |
| `GET /api/games` | `store.list_games()` | 读取历史对局 |
| `GET /api/games/{game_id}` | `store.load_game()` + `store.save_game()` | 读取并自动推进对局 |
| `DELETE /api/games/{game_id}` | `store.delete_game()` | 删除历史对局 |
| `POST /api/games` | `store.save_game()` | 创建新对局 |
| `POST /api/games/{game_id}/actions` | `store.load_game()` + `store.save_game()` | 提交动作并保存状态 |
| `GET /api/games/{game_id}/replay` | `store.get_replay()` | 读取回放 |
| `GET /api/stats/{player_name}` | `store.get_player_stats()` | 读取玩家统计 |

## 13. 为什么当前只用一张表

当前项目选择一张 `games` 表加多个 JSON 字段，主要是为了适配麻将状态复杂、字段经常变化的特点。

优点：

- 保存和恢复整局非常方便。
- 规则字段新增时不需要频繁改表。
- 对回放快照、动作日志、结算结果这类嵌套结构很友好。
- 适合当前单机、本地浏览器对战系统。

缺点：

- 不适合做特别复杂的 SQL 统计。
- 如果要统计每个役种胜率、每巡弃牌倾向、AI 决策质量，JSON 查询会比较重。
- 回放和日志数据长期变多后，单行 JSON 可能越来越大。
- 难以对每个动作、每个玩家、每个结算项做独立索引。

## 14. 后续数据库拆分建议

如果系统继续发展到更长期的牌谱分析、AI 训练数据收集或大量历史统计，建议逐步拆表。

可以考虑拆成：

| 表名 | 作用 |
| --- | --- |
| `games` | 保存对局基础信息和当前状态摘要 |
| `game_players` | 保存每局每个玩家的座位、名称、AI 等级、最终点数和顺位 |
| `game_actions` | 保存每一步动作，便于检索牌谱和分析出牌 |
| `game_snapshots` | 保存回放快照，避免全部塞进单行 JSON |
| `game_results` | 保存结算总览 |
| `game_result_yaku` | 保存每次和牌的役种、番数、符数 |
| `player_stats` | 保存预聚合玩家统计，避免每次都扫描历史对局 |
| `ai_decision_logs` | 保存 AI 每次评估的候选动作、EV、风险和最终选择 |

这样做会让系统更适合：

- 大量历史对局。
- 玩家长期战绩统计。
- AI 行动质量回放。
- 牌谱数据导出。
- 规则回归测试。
- 后续机器学习或强化学习数据积累。
