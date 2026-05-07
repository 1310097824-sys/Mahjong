# 系统论文与文献来源整理

更新时间：2026-05-07

本文档用于说明当前麻将系统开发过程中实际参考、间接参考或未来可继续对齐的论文、规则资料、开源项目和项目内部文档。需要特别说明的是：当前系统并不是直接复现某篇论文或某个现成 AI，而是在规则引擎、自动化审计、启发式 EV、对手建模和浅层搜索的基础上，逐步向雀魂/标准立直麻将和 AlphaJong/Suphx 类思路靠拢。

## 1. 总览结论

- 当前规则口径主要参考雀魂段位/友人/古役房相关资料、Riichi Wiki 的规则对比表、雀魂古役表，以及海底/河底、岭上开花等具体役种条目。
- 当前后端计分与向听计算使用 `mahjong==2.0.0`，也就是 MahjongRepository 的 Python 立直麻将计分/向听库。
- 当前 AI 不是深度学习模型，也没有接入 Suphx、AlphaJong、NAGA、Mortal 或其他训练权重；它是本项目自研的规则型/EV 型 AI。
- Suphx 论文和 AlphaJong 项目主要作为 AI 发展方向参考：局面评估、未来搜索、对手建模、押退判断、全局收益等思想被吸收进本项目设计，但没有复制其训练流程或代码实现。
- 本项目内部的 `logic.md`、`tech.md`、`programingsign.md`、`README.md`、`tests/mahjong_soul_rule_audit.py` 是当前系统最直接的工程说明和规则审计资料。

## 2. 规则与玩法资料

| 来源 | 类型 | 当前用途 | 相关位置 |
| --- | --- | --- | --- |
| [Mahjong Soul - Japanese Mahjong Wiki](https://riichi.wiki/index.php?mobileaction=toggle_view_desktop&title=Mahjong_Soul) | 雀魂规则资料 | 作为雀魂平台、段位规则、三麻规则差异等整体口径参考 | `tests/mahjong_soul_rule_audit.py`、`app/engine.py` |
| [Comparison of popular rulesets](https://riichi.wiki/Comparison_of_popular_rulesets) | 多规则集对比表 | 校验四麻/三麻起点、目标点、赤宝牌、三麻拔北、自摸损、多响、供托归属、立直后杠等规则差异 | `tests/mahjong_soul_rule_audit.py`、`app/engine.py` |
| [Template:Majsoul/Local yaku table](https://riichi.wiki/Template%3AMajsoul/Local_yaku_table) | 雀魂古役表 | 对齐古役房可选古役，如人和、大车轮、大竹林、大数邻、大七星、三连刻、一色三顺等 | `app/engine.py`、`tests/mahjong_soul_rule_audit.py` |
| [Haitei raoyue and houtei raoyui](https://riichi.wiki/Haitei_raoyue_and_houtei_raoyui) | 役种说明 | 参考海底捞月、河底捞鱼、最后摸牌/最后弃牌、最后弃牌不可被吃碰杠等处理 | `app/engine.py` |
| [Rinshan kaihou](https://riichi.wiki/Rinshan_kaihou) | 役种说明 | 参考岭上开花、杠后补牌、三麻拔北后补牌可形成岭上等规则 | `app/engine.py` |
| [Yaku - Japanese Mahjong Wiki](https://riichi.wiki/Yaku) | 役种总览 | 辅助核对标准立直麻将役种分类、闭门限定、可副露、役种兼容等 | `app/engine.py`、`logic.md` |

当前自动化规则审计入口是 `tests/mahjong_soul_rule_audit.py`。该脚本会围绕雀魂口径检查起点、目标点、三麻、赤宝牌、古役、多响、供托、本场、立直后暗杠、抢杠、海底/河底、拔北、九种九牌、流局满贯等规则点。

## 3. AI 论文与 AI 项目参考

### Suphx: Mastering Mahjong with Deep Reinforcement Learning

- 链接：[arXiv:2003.13590](https://arxiv.org/abs/2003.13590)
- 本地文件：`2003.13590v2.pdf`
- 作者：Junjie Li、Sotetsu Koyamada、Qiwei Ye、Guoqing Liu、Chao Wang、Ruihan Yang、Li Zhao、Tao Qin、Tie-Yan Liu、Hsiao-Wuen Hon
- 参考价值：Suphx 是深度强化学习麻将 AI，论文重点包括全局奖励预测、oracle guiding、运行时策略适配等。
- 本项目使用方式：作为“更强 AI 的方向参考”，不是代码依赖，也没有复现神经网络训练、牌谱训练、模型推理或官方权重。
- 对应落点：`logic.md` 中的 AI 发展说明、`app/engine.py` 中的结构化 EV、对手建模、押退判断、浅层前瞻搜索和全局顺位收益。

### AlphaJong

- 链接：[Jimboom7/AlphaJong](https://github.com/Jimboom7/AlphaJong)
- 类型：开源雀魂浏览器 AI 项目。
- 参考价值：AlphaJong README 说明其不是机器学习模型，而是使用传统算法，通过模拟若干回合并寻找较优动作。
- 本项目使用方式：作为“传统算法 + 模拟搜索 + 最优动作选择”的设计参考；当前没有直接复制 AlphaJong 代码，也没有把它作为依赖安装。
- 对应落点：`app/engine.py` 中的 `alpha_style_lookahead_profile()`、`discard_profile()`、`open_call_profile()`、`riichi_decision_profile()` 等命名和方向体现了这类思想，但实现仍是本项目自研。

### 其他 AI 资料

| 来源 | 当前状态 | 说明 |
| --- | --- | --- |
| NAGA | 未接入 | 仅在讨论 AI 水平时作为外部高强度 AI 参照，没有使用其服务、模型或接口。 |
| Mortal / mjai-reviewer | 未接入 | 未导入模型、牌谱审阅器或协议。 |
| Kanachan | 未接入 | 可作为以后研究“雀魂规则 + 训练数据 + 模型推理”的参考方向，但当前系统没有使用。 |

## 4. 开源库与工程资料

| 来源 | 类型 | 当前用途 | 相关位置 |
| --- | --- | --- | --- |
| [MahjongRepository/mahjong](https://github.com/MahjongRepository/mahjong) | Python 立直麻将库 | 计算向听、和牌、符番、役种和点数，是后端规则判断的重要基础库 | `requirements.txt`、`app/engine.py` |
| [mahjong - PyPI](https://pypi.org/project/mahjong/) | Python 包发布页 | 当前项目锁定 `mahjong==2.0.0` | `requirements.txt` |
| [react-riichi-mahjong-tiles](https://security.snyk.io/package/npm/react-riichi-mahjong-tiles) | React 牌面组件包索引 | 前端用于渲染传统立直麻将牌面，再由本项目包上象牙白底座和立体边框 | `riichi-mahjong-ui/package.json`、`riichi-mahjong-ui/src/components/Mahjong/MahjongTile.tsx` |

工程框架、数据库和前端动画资料主要属于技术栈文档，不算麻将论文或玩法文献，但它们支撑了系统实现：

- FastAPI：后端 API 服务。
- SQLAlchemy + PyMySQL + MySQL：历史对局、回放、统计和结算持久化。
- React + TypeScript + Vite：浏览器前端。
- Tailwind CSS：页面样式。
- Framer Motion：Dock、弹窗和交互动效。
- Canvas：水波背景与牌桌动态背景。

这些内容已经在 `tech.md` 中按使用位置详细说明。

## 5. 项目内部文档

| 文件 | 当前用途 |
| --- | --- |
| `README.md` | 项目总览、启动方式、功能说明、规则/AI 能力摘要。 |
| `logic.md` | 打牌逻辑、规则推进、AI 决策过程、EV 计算和最优解选择说明。 |
| `tech.md` | 技术栈、依赖、前后端使用位置说明。 |
| `programingsign.md` | 项目结构、文件职责、模块关系说明。 |
| `tests/mahjong_soul_rule_audit.py` | 雀魂规则对齐的自动化审计脚本。 |
| `spec.pdf` / `spec.txt` | 早期《基于 Python 的雀魂式立直麻将单人对战小游戏实施方案》，属于需求和实施方案，不是外部论文。 |

## 6. 当前没有直接使用的内容

为了避免把“参考过”和“已经实现”混在一起，这里单独列出当前没有直接接入的内容：

- 没有使用 Suphx 的训练数据、模型权重、神经网络结构或强化学习训练流水线。
- 没有直接接入 AlphaJong 源码，只参考了“传统算法模拟若干回合并选择最优动作”的思想。
- 没有使用 NAGA、Mortal、Akochan、Kanachan 等外部 AI 服务或模型。
- 没有爬取雀魂真实牌谱作为训练集。
- 没有实现完整监督学习、强化学习、自对弈训练或 GPU 推理。

## 7. 后续如果继续往强 AI 推进

如果后面继续把 AI 往 AlphaJong/Suphx 类方向发展，建议把资料体系补成三层：

- 规则层：继续以雀魂当前在线规则和 Riichi Wiki 的规则对比为准，所有新规则必须落到自动化审计脚本。
- 算法层：在现有 EV、对手建模、押退、浅层前瞻基础上，继续补充更稳定的搜索剪枝、局面价值估计和牌谱回放评测。
- 学习层：如果要真正接近 Suphx/现代强 AI，需要额外准备牌谱数据、特征编码、训练框架、模型评测和在线推理接口，这会是一个新的子项目级工作量。
