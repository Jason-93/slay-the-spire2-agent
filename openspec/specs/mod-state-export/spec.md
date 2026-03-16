# mod-state-export Specification

## Purpose
定义 STS2 mod 导出的统一决策窗口状态与 richer runtime schema，覆盖 combat、reward、map 等关键 phase，确保外部 agent 能稳定读取实时游戏事实与规划上下文。
## Requirements
### Requirement: Mod 必须导出统一且可扩展的决策窗口状态快照
系统 MUST 在 Slay the Spire 2 运行过程中识别当前决策窗口，并导出统一结构的状态快照，至少覆盖 `combat`、`reward`、`map`、`terminal` 四类窗口，并包含 `session_id`、`decision_id`、`state_version`、`phase` 等元数据。对于 `combat` 快照，mod MUST 在保持现有玩家、敌人、牌区与窗口元数据的同时，支持追加 richer state 字段，例如卡牌描述、升级态、目标类型、traits、结构化敌方 intent、玩家/敌方 powers，以及最小 `run_state` 上下文；新增字段 MUST 以追加式、可选字段方式导出，避免破坏现有消费方。

#### Scenario: 玩家处于战斗回合时请求 richer combat snapshot
- **WHEN** 外部调用方在玩家可行动的战斗回合请求当前快照
- **THEN** mod 返回一份 `combat` 类型的结构化状态快照，包含现有基础状态与已支持的 richer card/enemy/player fields
- **THEN** 若部分 richer 字段当前无法稳定读取，响应 MUST 仍保持 snapshot 有效，并以空值或缺省值兼容返回

### Requirement: Mod 必须导出最小整局规划上下文
系统 MUST 在不影响当前决策窗口导出的前提下，为 snapshot 提供最小 `run_state` 上下文，至少覆盖 `act`、`floor`、`current_room_type` 与可用的地图位置信息，以支撑后续牌库与路线规划能力。

#### Scenario: agent 在战斗中读取当前整局上下文
- **WHEN** 外部 agent 在进行中的战斗里请求 snapshot
- **THEN** 响应 MUST 包含当前所处 act、floor 与房间类型
- **THEN** 若当前 runtime 已能识别地图坐标或可达节点，mod MUST 一并导出这些最小规划上下文

### Requirement: Mod 必须导出与窗口对应的合法动作集合
系统 MUST 针对当前决策窗口导出完整合法动作集合，并为每个动作提供稳定的 `action_id`、动作 `type`、参数信息与目标约束。

#### Scenario: 奖励选牌窗口导出合法动作
- **WHEN** 外部调用方在奖励选牌界面请求合法动作
- **THEN** mod 返回该窗口下所有可选卡牌动作以及 `skip` 等合法选择动作

### Requirement: Mod 必须在状态变化时推进快照版本
系统 MUST 在决策窗口变化、回合推进或界面切换后推进 `state_version`，并生成新的 `decision_id`，以便外部系统识别状态是否已经失效。

#### Scenario: 战斗结束进入奖励界面
- **WHEN** 游戏从战斗窗口切换到奖励窗口
- **THEN** mod 返回新的 `state_version` 和新的 `decision_id`，并将 `phase` 更新为 `reward`

### Requirement: Mod 必须暴露兼容性元数据
系统 MUST 在状态快照中包含协议版本、mod 版本以及可用于诊断的兼容性元数据，以帮助外部 agent 检查当前 bridge 是否可用。

#### Scenario: 外部系统检查 bridge 兼容性
- **WHEN** 外部调用方读取当前状态快照
- **THEN** 响应中包含当前协议版本、mod 版本以及必要的环境兼容信息

### Requirement: Mod 必须同时导出牌堆计数与 pile contents
系统 MUST 在 combat `snapshot.player` 中继续保留现有 `draw_pile`、`discard_pile`、`exhaust_pile` 等计数字段，同时新增对应的 pile contents 列表，用于描述这些牌堆中当前有哪些牌。计数与列表 MUST 指向同一时刻的窗口状态，不得彼此明显矛盾。

#### Scenario: 抽牌堆存在卡牌时导出列表与计数
- **WHEN** 玩家当前战斗中的抽牌堆非空
- **THEN** `snapshot.player.draw_pile` MUST 返回数量摘要
- **THEN** `snapshot.player.draw_pile_cards` MUST 返回与该 pile 对应的结构化卡牌列表

#### Scenario: pile 为空时仍返回稳定结构
- **WHEN** 弃牌堆或消耗堆当前为空
- **THEN** 对应计数字段 MUST 为 `0`
- **THEN** 对应 pile contents 字段 MUST 返回空数组，而不是缺失或返回非列表值

### Requirement: Mod 必须同时导出基础 enemy state 与 richer enemy fields
系统 MUST 在 combat `snapshot.enemies[]` 中继续保留现有基础敌人字段，同时新增可供 agent 直接消费的 richer enemy fields，用于表达当前招式说明、trait/tag 与机制关键词。基础字段与 enrich 字段 MUST 指向同一时刻的窗口状态，不得彼此明显矛盾。

#### Scenario: 敌人存在当前招式文本时导出 enrich fields
- **WHEN** 某个敌人的当前招式在 runtime 中可读取到显示文本或说明文本
- **THEN** 对应 `snapshot.enemies[]` 条目 MUST 返回基础敌人状态
- **THEN** 对应条目 MUST 额外返回 `move_name`、`move_description` 或等效 enrich fields

#### Scenario: enrich 字段暂时为空时仍返回稳定结构
- **WHEN** 某个敌人的 trait、keyword 或 move description 当前不可读
- **THEN** 该敌人的基础字段 MUST 仍然导出
- **THEN** enrich 字段 MUST 返回空数组、空值或缺失 optional 字段中的稳定形式，而不是返回不可序列化值

### Requirement: Mod 导出的 glossary hint 必须反映真实来源语义
系统在导出 glossary anchors 时，`display_text` 与 `hint` SHOULD 尽量来自游戏 runtime / localization 的真实文本；若使用 fallback，导出结构 MUST 准确表达其来源语义，不得把手写说明伪装成游戏原始词条说明。

#### Scenario: Power glossary 说明来自真实 power 文本
- **WHEN** 某个 power 或等效模型存在可解析的标题与说明文本
- **THEN** 对应 glossary anchor MUST 优先复用该模型或其 hover tip 的真实文本
- **THEN** `hint` 内容 MUST 与当前语言环境下的游戏词条说明保持一致或等效

#### Scenario: fallback glossary 不再冒充游戏原文
- **WHEN** 某个 glossary term 当前只能依赖 bridge 内置 fallback
- **THEN** 该 glossary anchor MAY 返回空 `hint` 或最小 fallback `hint`
- **THEN** 其 `source` MUST 明确标识 fallback 语义，且 metadata 或日志 MUST 可用于定位缺口

### Requirement: Mod 必须以精简协议导出说明类对象
系统 MUST 在统一状态快照与合法动作元数据中把说明类对象导出为精简公共协议。对于 cards、powers、card preview 与后续复用同类说明结构的对象，mod MUST 以 `description` 作为唯一必需的用户向说明文本字段；仅用于 description 解析排障的 `description_quality`、`description_source`、`description_vars` 等内部结构 MUST NOT 进入公共导出 schema。

#### Scenario: snapshot 中的卡牌说明只保留 canonical description
- **WHEN** 外部调用方读取 `snapshot.player.hand[]` 中的卡牌对象
- **THEN** 若该卡牌存在说明文本，快照 MUST 返回最终可读的 `description`
- **THEN** 快照 MUST NOT 要求调用方继续读取内部 diagnostics 才能理解该卡牌描述

#### Scenario: action metadata 与 snapshot 共享同一精简说明协议
- **WHEN** bridge 为动作 metadata 导出 `card_preview` 或其他说明对象
- **THEN** metadata 中的说明结构 MUST 与 snapshot 保持一致的精简字段语义
- **THEN** 不同导出位置 MUST NOT 出现一处只给 `description`、另一处继续暴露内部解析 diagnostics 的分叉协议

### Requirement: Mod 必须导出单一 canonical description 协议
系统 MUST 在统一状态快照与合法动作元数据中以 `description` 作为唯一 canonical 说明文本字段，并稳定导出 `description_quality`、`description_source` 与 `description_vars` 作为辅助 diagnostics。mod MUST NOT 在公共 schema 中继续保留仅用于历史兼容的重复字段，例如要求调用方在 `description_rendered`、`description_raw` 与 `description` 之间自行判断哪一个可用。若说明中包含 glossary 高亮，`description` MUST 输出为稳定的 markdown 风格强调文本，例如 `**格挡**`。

#### Scenario: snapshot 中的卡牌说明字段可直接消费
- **WHEN** 外部调用方读取 `snapshot.player.hand[]` 中的卡牌对象
- **THEN** 若该卡牌存在说明文本，快照 MUST 直接返回最终可读的 `description`
- **THEN** 若存在可提取的动态变量，快照 MUST 返回 `description_vars`
- **THEN** 调用方 MUST 能仅基于 `description` 与 diagnostics 判断当前说明是已解析、部分解析还是模板回退

#### Scenario: legal action preview 与 snapshot 保持同一说明语义
- **WHEN** bridge 生成 `play_card`、`choose_reward` 或其他带 `card_preview` / `reward_preview` 的合法动作
- **THEN** metadata 中的说明字段 MUST 与当前 `snapshot` 对应对象保持一致语义
- **THEN** 不同导出位置之间 MUST NOT 出现一个已解析、一个仍要求客户端兜底的冲突状态

#### Scenario: glossary 高亮在不同导出位置保持一致
- **WHEN** 某个对象说明中包含 glossary 词条，例如 `格挡`
- **THEN** `snapshot` 与 action preview 中的 `description` MUST 一致使用 `**格挡**` 形式
- **THEN** 调用方 MUST 不需要额外理解游戏富文本标签或再次格式化

### Requirement: Mod 必须为说明解析结果提供稳定扩展点
系统 MUST 允许在不改变基础字段契约的前提下，把相同的说明解析语义扩展到 cards 之外的其他实体，例如 powers、relics、potions 或后续百科对象。新增实体时 MUST 复用相同的质量语义与来源标记，避免每类对象单独定义一套说明字段协议。

#### Scenario: 新实体接入时沿用统一质量语义
- **WHEN** 后续将 relics、potions 或其他可解释对象接入说明导出
- **THEN** 新对象 MUST 继续使用与 cards / powers 一致的 `description`、`description_quality` 与 `description_source` 语义
- **THEN** 外部调用方 MUST 无需为每种实体重新实现一套说明可信度判定逻辑

### Requirement: Mod 必须为 live 手牌描述优先导出真实动态数值
系统 MUST 在真实 STS2 runtime 的 `combat` 手牌导出中，优先返回与当前卡牌实例一致的动态数值描述。对于 `damage`、`block`、`draw`、`strength` 或等效高价值字段，mod MUST 尽量从 live card instance 或等效运行时状态中提取真实值，而不是长期停留在模板占位符文本。

#### Scenario: 基础攻击牌在 live combat 中导出真实伤害
- **WHEN** 玩家处于真实战斗回合，手牌中存在一张可打出的基础攻击牌，且运行时能计算当前伤害
- **THEN** 该卡牌的导出结果 MUST 反映当前实例级的真实伤害值，或在 `description_vars` 中给出对应数值
- **THEN** mod MUST NOT 只返回没有任何数值信息的 `{Damage:diff()}` 模板作为唯一有效信息

#### Scenario: 基础防御牌在 live combat 中导出真实格挡
- **WHEN** 玩家处于真实战斗回合，手牌中存在一张可打出的基础防御牌，且运行时能计算当前格挡
- **THEN** 该卡牌的导出结果 MUST 反映当前实例级的真实格挡值，或在 `description_vars` 中给出对应数值
- **THEN** 若真实值暂不可得，响应 MUST 明确处于模板回退，而不是伪装为高质量 rendered

### Requirement: Mod 必须区分高质量 rendered 描述与模板回退
系统 MUST 区分“已经解析出真实数值的 `description_rendered`”与“仅做了样式去除但仍包含模板占位符的兼容文本”。当最终文本仍包含模板占位符、且也无法提供对应变量值时，mod MUST 将该对象标记为回退状态，并为排障提供来源或质量信息。

#### Scenario: 文本仍含模板占位符时不得视为高质量 rendered
- **WHEN** 导出的卡牌描述文本中仍包含 `{Damage:diff()}`、`{Block:diff()}` 或等效模板占位符
- **THEN** mod MUST 将该结果视为模板回退或未完全渲染状态
- **THEN** 对应 diagnostics MUST 能指出这是回退路径，而不是成功渲染

#### Scenario: 已完成变量替换时可视为高质量 rendered
- **WHEN** mod 已成功解析真实动态数值，并能生成不含模板占位符的用户向描述
- **THEN** `description_rendered` MUST 返回该最终文本
- **THEN** diagnostics 或等效字段 MUST 能表明该描述来自 live value resolution，而不是模板回退

### Requirement: Mod 必须导出统一的决策窗口状态快照
系统 MUST 在 Slay the Spire 2 运行过程中识别当前决策窗口，并导出统一结构的状态快照，至少覆盖 `combat`、`reward`、`map`、`terminal` 四类窗口，并包含 `session_id`、`decision_id`、`state_version`、`phase` 等元数据。

#### Scenario: 玩家处于战斗回合时请求状态
- **WHEN** 外部调用方在玩家可行动的战斗回合请求当前快照
- **THEN** mod 返回一份 `combat` 类型的结构化状态快照，包含玩家、敌人、牌区和窗口元数据
