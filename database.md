# 数据库使用说明

更新时间：2026-05-13

本文说明当前麻将系统中 `SQLAlchemy + PyMySQL + MySQL` 的使用方式，以及已经落地的多表拆分结构。

## 1. 总体结论

当前系统使用 MySQL 作为主数据库，后端通过 SQLAlchemy ORM 操作数据库，底层连接驱动使用 PyMySQL。

| 项目 | 当前值 |
| --- | --- |
| 数据库类型 | MySQL |
| Python 驱动 | PyMySQL |
| ORM / 连接管理 | SQLAlchemy |
| 主数据库名 | `mahjong` |
| 地址 | `127.0.0.1:3306` |
| 默认用户 | `root` |
| 字符集 | `utf8mb4` |

系统已经从早期的“单表大 JSON”拆成“轻量主表 + 状态表 + 动作明细 + 回放快照 + 玩家结果 + 结算结果”。`games` 仍保留旧 JSON 字段以兼容老代码，但新写入会把这些旧字段压缩为空对象/空数组。

## 2. 为什么要拆表

旧结构只有一张 `games` 表，里面同时保存历史摘要、完整对局状态、全量动作日志、全量回放快照和结算结果。实际检查时，单局 JSON 已经达到 MB 级：

- 最大 `games.state_json` 约 `4.24 MB`。
- 最大 `games.snapshots_json` 约 `4.14 MB`。
- 平均 `games.state_json` 约 `2.15 MB`。
- 平均 `games.snapshots_json` 约 `2.08 MB`。

这会让历史列表、玩家统计、排序和普通查询被大 JSON 拖慢，甚至触发 MySQL：

```text
Out of sort memory, consider increasing server sort buffer size
```

拆表后的当前效果：

- `games.state_json/action_log_json/snapshots_json` 已压缩为空对象或空数组。
- `game_states.state_json` 不再重复保存 `action_log` 和 `snapshots`，最大约 `21 KB`。
- `game_actions` 与 `game_replay_snapshots` 以逐行明细保存，适合回放、统计和后续 AI 训练抽样。
- 保存对局时动作和快照采用追加式写入，不再每一步全删全插，能明显降低晚巡越打越卡的问题。

## 3. 当前表结构

| 表名 | 作用 |
| --- | --- |
| `games` | 对局主表，保存轻量摘要、状态、模式和兼容字段 |
| `game_states` | 当前可恢复对局状态，不重复保存动作日志和回放快照 |
| `game_players` | 每局每个玩家的座位、分数、AI 等级和名次 |
| `game_actions` | 逐行动作日志 |
| `game_replay_snapshots` | 逐步回放快照 |
| `game_results` | 终局结算摘要 |

当前迁移后的数据量：

| 表名 | 当前行数 |
| --- | ---: |
| `games` | 10 |
| `game_states` | 10 |
| `game_players` | 31 |
| `game_actions` | 1926 |
| `game_replay_snapshots` | 1926 |
| `game_results` | 2 |

## 4. `games`

`games` 是对局主表，适合历史列表、状态筛选和轻量统计入口。

| 字段 | 作用 |
| --- | --- |
| `id` | 对局 ID，主键 |
| `player_name` | 人类玩家名 |
| `mode` | `3P` 或 `4P` |
| `round_length` | `EAST` 或 `HANCHAN` |
| `status` | `RUNNING` / `FINISHED` |
| `summary_json` | 历史列表用摘要 |
| `state_json` | 旧版完整状态字段，新写入压缩为 `{}` |
| `action_log_json` | 旧版动作日志字段，新写入压缩为 `[]` |
| `snapshots_json` | 旧版回放字段，新写入压缩为 `[]` |
| `result_json` | 兼容结算结果 |
| `notes` | 备注 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

关键索引：

| 索引 | 字段 | 作用 |
| --- | --- | --- |
| `PRIMARY` | `id` | 精确读取、更新、删除 |
| `ix_games_updated_at` | `updated_at` | 历史列表排序 |
| `ix_games_status_updated_at` | `status, updated_at` | 按状态列出对局 |
| `ix_games_player_status_updated_at` | `player_name, status, updated_at` | 玩家历史和统计 |
| `ix_games_player_name` | `player_name` | 兼容旧查询 |
| `ix_games_mode` | `mode` | 模式筛选 |
| `ix_games_status` | `status` | 状态筛选 |

## 5. `game_states`

`game_states` 保存当前可恢复的对局状态。为了降低晚巡保存压力，里面不再保存完整 `action_log` 和 `snapshots`，这两个字段在保存前会被压缩为空数组。

| 字段 | 作用 |
| --- | --- |
| `game_id` | 对局 ID，主键，关联 `games.id` |
| `state_json` | 轻量可恢复对局状态 |
| `updated_at` | 更新时间 |

读取对局时，`GameStore.load_game()` 会先读取 `game_states.state_json`，再从 `game_actions` 和 `game_replay_snapshots` 自动拼回完整 `action_log` 与 `snapshots`。因此这个拆分对前端和规则引擎是透明的。

## 6. `game_players`

`game_players` 保存每局每个玩家的座位、身份和结果，玩家统计优先查询这张表，不再从结算 JSON 里反复解析。

| 字段 | 作用 |
| --- | --- |
| `game_id` | 对局 ID |
| `seat` | 座位号 |
| `name` | 玩家名 |
| `is_human` | 是否人类玩家 |
| `ai_level` | AI 难度，真人为 0 |
| `initial_points` | 初始点数，当前预留 |
| `final_points` | 当前/最终点数 |
| `placement` | 终局名次，未结束时为空 |
| `updated_at` | 更新时间 |

## 7. `game_actions`

`game_actions` 保存逐行动作日志，后续可以直接用于回放、规则审计和 AI 训练样本抽取。

| 字段 | 作用 |
| --- | --- |
| `game_id` | 对局 ID |
| `seq` | 动作序号 |
| `seat` | 动作座位 |
| `actor` | 动作玩家名 |
| `action_type` | 动作类型，如 `DISCARD`、`DRAW`、`KAN` |
| `tile_label` | 展示用牌名 |
| `round_label` | 当前局标签 |
| `details` | 动作说明 |
| `state_hash` | 状态哈希 |
| `action_json` | 完整原始动作 JSON |
| `created_at` | 创建时间 |

关键索引：

- `game_id, seq`
- `game_id, action_type`

## 8. `game_replay_snapshots`

`game_replay_snapshots` 保存逐步回放快照。它把原先几 MB 的快照数组拆成小 JSON 行，只有打开回放时才读取。

| 字段 | 作用 |
| --- | --- |
| `game_id` | 对局 ID |
| `seq` | 快照序号 |
| `action_type` | 对应动作类型 |
| `round_label` | 当前局标签 |
| `snapshot_json` | 前端回放需要的公开状态 |
| `created_at` | 创建时间 |

关键索引：

- `game_id, seq`

## 9. `game_results`

`game_results` 保存终局结算摘要，供结算面板、历史结果、统计和后续排行榜使用。

| 字段 | 作用 |
| --- | --- |
| `game_id` | 对局 ID，主键 |
| `result_json` | 完整结算 JSON |
| `finished_at` | 完成时间 |
| `leftover_riichi_bonus` | 终局剩余供托处理 |
| `updated_at` | 更新时间 |

## 10. 当前读写路径

保存入口：

```text
app/store.py -> GameStore.save_game()
```

保存流程：

1. 写入/更新 `games.summary_json`。
2. 把旧版大 JSON 字段压缩为 `{}` / `[]`。
3. 写入轻量 `game_states.state_json`。
4. 刷新小体量的 `game_players`。
5. 向 `game_actions` 只追加新增 `seq`。
6. 向 `game_replay_snapshots` 只追加新增 `seq`。
7. 已完成对局写入或更新 `game_results`。

读取对局：

```text
GameStore.load_game()
game_states.state_json + game_actions + game_replay_snapshots
```

读取回放：

```text
GameStore.get_replay()
game_actions + game_replay_snapshots + game_results
```

玩家统计：

```text
GameStore.get_player_stats()
game_players + games.status
```

未迁移的旧数据仍会回退读取 `games.state_json/action_log_json/snapshots_json/result_json`。

## 11. 迁移脚本

迁移脚本：

```text
migrate_games_to_split_tables.py
```

运行方式：

```powershell
python migrate_games_to_split_tables.py
```

它会：

1. 调用 `init_db()` 创建新表和运行期索引。
2. 遍历旧 `games` 记录。
3. 把旧大 JSON 写入拆分表。
4. 对已经拆分但仍重复保存历史数组的 `game_states` 做二次压缩。
5. 保留兼容字段，但压缩旧大 JSON。

最近一次迁移结果：

```text
拆表迁移完成：迁移 0 局，压缩 10 局，已拆分 0 局，跳过 0 局。
```

## 12. 后续拆分建议

下一阶段可以继续做：

- 把 `games.summary_json` 中常用字段拆成真实列，例如 `rule_profile`、`round_label`、`aka_dora_count`、`sanma_scoring_mode`。
- 给 `game_results` 增加 `winner_seat`、`top_score`、`human_placement`、`is_tobi` 等统计字段。
- 把 `game_actions.action_json` 再拆出训练友好的字段，例如 `tile_id`、`from_seat`、`action_source`、`is_called`。
- 为 AI 训练单独生成 `training_samples` 表，不直接从回放 JSON 在线解析。
- 引入 Alembic 管理数据库版本迁移，避免后续手工改表。
