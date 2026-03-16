# game-bridge Specification

## Purpose
TBD - created by archiving change sts2-agent. Update Purpose after archive.
## Requirements
### Requirement: Bridge 暴露当前决策快照
系统 MUST 暴露当前 Slay the Spire 2 决策窗口的结构化快照，至少包含会话元数据、阶段元数据、玩家可见状态、敌人可见状态、牌区摘要、遗物、药水以及终局标记。对于 combat 相关快照，bridge MUST 进一步稳定暴露 richer runtime state，包括可选的卡牌描述、升级态、目标类型、traits、结构化敌方 intent、玩家/敌方 powers 与最小 `run_state` 规划上下文；bridge MUST 保持现有基础字段语义不变，并允许 richer 字段缺失时兼容退化。

#### Scenario: 在玩家回合中请求 richer combat snapshot
- **WHEN** agent 在一场进行中的战斗里、玩家可行动阶段请求当前决策快照
- **THEN** bridge 返回该最新决策窗口的单个结构化快照，并包含足以选择合法动作的基础状态与已支持 richer state 字段
- **THEN** agent 即使遇到部分 richer 字段缺失，也仍能基于保底字段继续读取与决策

#### Scenario: 在玩家回合中请求战斗快照
- **WHEN** agent 在一场进行中的战斗里、玩家可行动阶段请求当前决策快照
- **THEN** bridge 返回该最新决策窗口的单个结构化快照，并包含足以选择合法动作的可见状态


### Requirement: Bridge 必须为知识层扩展保留稳定锚点
系统 MUST 在卡牌、敌人或等效对象上保留可供上层知识系统消费的稳定锚点，例如 `canonical_*_id` 或等效标识，并与 live action 所需的实例标识分离。bridge MAY 在第一阶段对暂时无法解析的锚点返回空值，但协议 MUST 允许这些字段稳定存在。

#### Scenario: 上层策略同时需要实例动作与静态知识映射
- **WHEN** 上层策略既要提交某张具体手牌的动作，又要查询该卡牌的长期知识标签
- **THEN** bridge 返回的对象 MUST 能区分运行时实例标识与稳定知识锚点
- **THEN** 上层调用方 MUST 不需要依赖卡名字符串推断二者关系

### Requirement: Bridge 枚举当前决策窗口的合法动作
系统 MUST 返回当前决策窗口的完整合法动作集合，且每个动作 MUST 包含稳定的 `action_id`、动作 `type`、所需参数以及执行该动作所需的目标约束。

#### Scenario: 请求当前战斗中的合法动作
- **WHEN** agent 在战斗中、玩家仍可行动时请求合法动作列表
- **THEN** bridge 返回该决策窗口下全部当前可用的出牌、选目标、使用药水和结束回合动作

### Requirement: Bridge 在不改变状态的前提下拒绝过期或非法动作
系统 MUST 基于最新决策窗口校验提交动作，并 MUST 在动作格式错误、动作非法或动作已过期时拒绝该提交，同时不修改游戏状态。

#### Scenario: 状态变化后提交了旧决策窗口的动作
- **WHEN** agent 提交的动作绑定于旧的决策窗口，而 bridge 已经推进到新的 `state_version`
- **THEN** bridge 以确定性的错误响应拒绝该动作，并保持当前游戏状态不变

### Requirement: Bridge 支持本地对局生命周期控制
系统 MUST 提供本地生命周期操作，用于启动或附着到会话、在支持时重置或重开一局，以及在不让游戏进入不确定状态的前提下干净地停止 agent 控制。

#### Scenario: 操作者为新的 agent 尝试重开一局
- **WHEN** 操作者对当前会话发起受支持的 reset 或 restart 命令
- **THEN** bridge 初始化一个新的可控会话，并返回新的会话标识供后续 agent 调用

### Requirement: Bridge 必须在 combat 快照中导出主要牌堆内容
系统 MUST 在 `snapshot.phase="combat"` 时，除当前手牌外，还导出当前玩家抽牌堆、弃牌堆、消耗堆的结构化卡牌内容。对外字段名可以是 `draw_pile_cards`、`discard_pile_cards`、`exhaust_pile_cards` 或等效稳定名称，但三类 pile MUST 可被调用方稳定区分。

#### Scenario: 战斗快照同时包含 hand 与 pile contents
- **WHEN** agent 在玩家可行动的战斗回合请求当前快照
- **THEN** `snapshot.player` MUST 同时包含 `hand` 与 draw/discard/exhaust 的 pile contents
- **THEN** 调用方 MUST 不必只依赖 `draw_pile`、`discard_pile`、`exhaust_pile` 计数字段猜测具体牌组成

#### Scenario: pile cards 与 hand cards 保持一致的基础语义
- **WHEN** bridge 导出 `draw_pile_cards`、`discard_pile_cards` 或 `exhaust_pile_cards`
- **THEN** 每个 pile card MUST 复用与 `hand[]` 一致的基础卡牌字段语义，例如 `name`、`canonical_card_id`、`description` 或等效字段
- **THEN** 这些 pile cards MUST 作为观察态信息导出，而不是自动被视为当前可执行动作

### Requirement: Bridge 必须在 combat 快照中导出 richer enemy runtime state
系统 MUST 在 `snapshot.phase="combat"` 时，为 `snapshot.enemies[]` 导出比基础血量与 intent 更丰富的敌人观测信息。对外字段可以是 `move_name`、`move_description`、`move_glossary`、`traits`、`keywords` 或等效稳定名称，但调用方 MUST 能稳定区分“当前招式信息”和“敌人自身 trait / keyword 信息”。

#### Scenario: 战斗快照包含敌人的招式文本与机制标签
- **WHEN** agent 在玩家可行动的战斗回合请求当前快照
- **THEN** `snapshot.enemies[]` MUST 在基础 `intent`、`intent_damage`、`powers` 之外，额外导出当前敌人的行动文本或等效 richer fields
- **THEN** 调用方 MUST 不必只依赖 `intent_damage` 与敌人名称猜测当前怪物机制

#### Scenario: richer enemy fields 与现有基础字段保持兼容
- **WHEN** bridge 导出 richer enemy state
- **THEN** 现有 `enemy_id`、`name`、`hp`、`block`、`intent`、`powers` 等基础字段 MUST 继续保留
- **THEN** 新增字段 MUST 作为向后兼容增强，而不是要求旧调用方迁移到全新 enemy 嵌套对象

### Requirement: Bridge 面向 Agent 的说明对象必须保持精简
系统 MUST 将 cards、powers、card preview 与其他说明类对象的公共响应收敛为面向决策的精简 schema。对外协议中的说明文本 MUST 以 canonical `description` 为主；`description_quality`、`description_source`、`description_vars` 等仅用于解析排障的内部字段 MUST NOT 继续暴露给客户端或策略层。

#### Scenario: 战斗快照中的手牌与 powers 只导出精简说明字段
- **WHEN** agent 读取 `snapshot.player.hand[]`、`snapshot.player.powers[]` 或 `snapshot.enemies[].powers[]`
- **THEN** 若对象存在说明文本，bridge MUST 返回可直接消费的 `description`
- **THEN** 公共响应 MUST NOT 再包含 `description_quality`、`description_source` 或 `description_vars`

#### Scenario: legal action preview 不再泄漏内部说明诊断
- **WHEN** bridge 为 `play_card`、`choose_reward` 或等效动作导出 `card_preview`、`reward_preview` 等说明对象
- **THEN** preview 中的说明字段 MUST 与 snapshot 一样保持精简
- **THEN** 客户端 MUST 不需要理解说明解析来源、变量表或回退等级才能正常决策

### Requirement: Bridge 快照必须暴露卡牌描述的解析质量
系统 MUST 在桥接快照中为卡牌说明维持稳定的 canonical `description` 语义，并在可用时优先使用游戏 runtime 已完成上下文渲染的最终文本，而不是模板文本、半渲染文本或 bridge 侧自行拼接的 DSL 结果。对于 `snapshot.player.hand[]`、`draw_pile_cards`、`discard_pile_cards`、`exhaust_pile_cards` 与 `actions[].metadata.card_preview` 中描述同一张 live 卡牌的对象，bridge MUST 尽可能复用同一条 canonical description 语义。若最终渲染结果暂不可得，快照 MUST 继续返回兼容的单个 `description` 文本；质量、来源与回退阶段等诊断信息 MUST 留在日志、内部 diagnostics 或等效排障通道，而 MUST NOT 再要求外部调用方理解额外公开字段。

#### Scenario: 快照中的卡牌描述优先复用游戏最终渲染结果
- **WHEN** bridge 能从 live runtime 为某张卡牌拿到与当前上下文一致的最终 description
- **THEN** `snapshot.player.hand[]`、相关 pile card 或 `actions[].metadata.card_preview` MUST 返回该最终可读文本
- **THEN** 对外 `description` MUST 不再暴露 `IfUpgraded`、`diff()` 或等效模板 DSL 残留

#### Scenario: 最终渲染不可用时仍保持精简兼容输出
- **WHEN** bridge 无法稳定获取某张卡牌的游戏最终 description，只能回退到现有 runtime 字段或模板 fallback
- **THEN** 快照 MUST 仍返回单个可序列化的 `description`
- **THEN** 公共响应 MUST NOT 因此重新暴露 `description_quality`、`description_source` 或等效调试字段

#### Scenario: 快照中的卡牌描述已完成真实数值解析
- **WHEN** bridge 已从 live runtime 拿到当前卡牌实例的真实动态数值
- **THEN** 快照中的 `description_rendered` MUST 为不含模板占位符的最终文本
- **THEN** `description_vars` MUST 能反映对应动态字段的实际值

#### Scenario: 快照中的卡牌描述仍处于模板回退
- **WHEN** bridge 只能拿到模板文本，或 `description_rendered` 仍包含模板占位符
- **THEN** 快照 MUST 继续返回兼容字段，避免中断 autoplay
- **THEN** 快照 MUST 同时暴露足以识别回退状态的质量或来源信息


### Requirement: Bridge 不得把模板文本伪装成高质量策略输入
系统 MUST 确保上层通过 snapshot 或 action metadata 读取到的卡牌说明不会在一个位置使用游戏最终描述、另一个位置却继续暴露未解释 DSL 或过时模板。对于同一张 live 卡牌实例，`snapshot.player.hand[]` 与 `actions[].metadata.card_preview` MUST 共享一致的 canonical description 语义；对于 pile cards，bridge MUST 使用与其 pile 语义相匹配的 description，而不是简单复用无上下文模板。若某张卡牌只能回退到较低质量文本，bridge MUST 在所有对外位置保持一致降级，并通过日志或内部 diagnostics 明确指出 fallback，而不是让某处看似“已完成渲染”、某处仍是模板残留。

#### Scenario: hand 与 card_preview 对同一卡牌保持一致 description
- **WHEN** 同一张 live 手牌同时出现在 `snapshot.player.hand[]` 与 `actions[].metadata.card_preview`
- **THEN** 两处的 `description` MUST 共享一致的 canonical 语义
- **THEN** bridge MUST NOT 在一个位置返回游戏最终文本、另一个位置却保留未解释模板

#### Scenario: pile cards 使用与所在 pile 对应的 description 语义
- **WHEN** bridge 导出 `draw_pile_cards`、`discard_pile_cards` 或 `exhaust_pile_cards`
- **THEN** 每张 pile card 的 `description` MUST 反映其所在 pile 的 runtime description context 或等效语义
- **THEN** bridge MUST NOT 把仅适用于 hand 或 preview 的 description 机械复制到所有 pile cards

#### Scenario: action metadata 中的 card_preview 与 snapshot 质量保持一致
- **WHEN** 同一张 live 手牌同时出现在 `snapshot.player.hand` 与 `actions[].metadata.card_preview`
- **THEN** 两处关于 `description_rendered`、`description_vars` 和回退状态的语义 MUST 保持一致
- **THEN** bridge MUST NOT 在一个位置标记为已解析、另一个位置却仍是模板回退且无解释


### Requirement: Bridge 必须导出结构化药水状态与药水栏容量
系统 MUST 在 `snapshot.player` 中导出面向决策的结构化药水状态，而不是仅提供药水名称列表。`player.potions` MUST 表示当前持有药水的结构化列表；每个条目至少 MUST 包含 `name`，并在可用时补充 `description`、`canonical_potion_id`、`glossary` 或等效稳定字段。`player` 同时 MUST 导出 `potion_capacity` 或等效稳定容量字段，用于表示当前药水栏上限。

#### Scenario: 战斗快照包含结构化药水与容量
- **WHEN** agent 在战斗中请求当前快照，且玩家持有至少一瓶药水
- **THEN** `snapshot.player.potions` MUST 返回结构化药水对象列表，而不是纯字符串数组
- **THEN** 每个药水对象 MUST 至少包含 `name`
- **THEN** `snapshot.player` MUST 同时返回 `potion_capacity` 或等效稳定字段

#### Scenario: 药水描述暂不可读时仍保持稳定结构
- **WHEN** bridge 当前只能识别药水名称，但暂时无法稳定解析某瓶药水的说明文本
- **THEN** 对应 `player.potions[]` 条目 MUST 仍然作为结构化对象返回
- **THEN** 该条目的 `description` 在缺失时 MUST 显式返回空值、缺省值或等效稳定空语义
- **THEN** bridge MUST NOT 因单瓶药水说明缺失而让整个 `snapshot` 失效

### Requirement: 药水动作必须能与结构化药水观察稳定关联
当 `actions` 中存在 `use_potion` 时，bridge MUST 让调用方能够把该动作与 `snapshot.player.potions[]` 中的具体药水稳定关联。bridge 即使继续沿用当前动作主参数，仍 MUST 在参数或 metadata 中提供足以定位对应药水对象的稳定信息。

#### Scenario: use_potion legal action 可关联到当前药水对象
- **WHEN** 当前 `actions` 中存在某个 `type="use_potion"` 的 legal action
- **THEN** 该 action MUST 能通过参数或 metadata 指向 `snapshot.player.potions[]` 中的一瓶当前药水
- **THEN** 调用方 MUST 不需要仅靠字符串模糊匹配来判断动作对应哪瓶药水

### Requirement: Bridge 必须导出结构化 relic 状态
系统 MUST 在 `snapshot.player` 中导出面向决策的结构化 relic 状态，而不是仅提供 relic 名称字符串列表。`player.relics` MUST 表示当前持有 relic 的结构化对象列表；每个条目至少 MUST 包含 `name`，并在可用时补充 `description`、`canonical_relic_id`、`glossary` 或等效稳定字段。若某个 relic 的说明暂不可读，bridge MUST 仍返回稳定对象结构，而不是回退为纯字符串或让整个 `snapshot` 失效。

#### Scenario: 战斗快照包含结构化 relic 对象
- **WHEN** agent 在任意可读取玩家状态的窗口请求当前快照，且玩家持有至少一个 relic
- **THEN** `snapshot.player.relics` MUST 返回结构化对象列表，而不是字符串数组
- **THEN** 每个 relic 对象 MUST 至少包含 `name`

#### Scenario: relic 说明缺失时保持稳定结构
- **WHEN** bridge 当前只能稳定识别某个 relic 的名称，尚无法解析其 description
- **THEN** 对应 `player.relics[]` 条目 MUST 仍以结构化对象返回
- **THEN** 该条目的 `description` MUST 使用空值、缺省值或等效稳定空语义

#### Scenario: relic glossary 不得重复主说明语义
- **WHEN** bridge 为某个 relic 成功导出 `glossary`
- **THEN** `player.relics[].glossary` MUST 只包含对主 `description` 有额外补充价值的 glossary 项
- **THEN** bridge MUST NOT 再把 relic 自身 title/hint 以重复 glossary 项暴露给客户端
- **THEN** bridge MUST NOT 导出 `hint=null`、`source=missing_hint` 或等效低价值 glossary 条目


### Requirement: relic 说明对象必须遵守精简 canonical schema
系统 MUST 将 relic 说明对象与 cards、powers、potions 一样收敛为面向决策的精简 schema。若 relic 存在说明文本，对外协议 MUST 以 canonical `description` 为主；`description_quality`、`description_source`、`description_vars` 或其他仅用于排障的内部字段 MUST NOT 暴露给客户端。

#### Scenario: relic 对外只暴露 canonical description
- **WHEN** bridge 成功为某个 relic 解析出可读说明文本
- **THEN** `snapshot.player.relics[]` MUST 返回 `description`
- **THEN** 公共响应 MUST NOT 额外暴露仅用于排障的 description diagnostics 字段

### Requirement: Bridge 导出的 enemy richer fields 必须保持去噪后的 canonical 语义
系统 MUST 将 `snapshot.enemies[]` 中的 `intent`、`move_name`、`move_description`、`keywords` 与 `move_glossary` 收敛为面向决策的 canonical 语义，而不是直接泄漏 UI 展示标签、富文本残留或内部 runtime 标识。对于只重复数值意图、仅表达 UI 排版，或与已有字段语义完全重复的 enemy 字段，bridge MUST 抑制或过滤这些低价值内容。

#### Scenario: enemy move name 不得只重复数值意图
- **WHEN** 某个敌人的 runtime `move_name` 只是 `2×3`、`攻势` 或等效数值/展示标签，且未提供独立机制语义
- **THEN** `snapshot.enemies[]` 的 `move_name` MUST 允许为空或被抑制
- **THEN** `move_description` MUST 继续作为当前行动的主要可读解释

#### Scenario: enemy keywords 不得泄漏内部标识
- **WHEN** enemy `keywords` 提取结果中出现 `POWER.SLIPPERY_POWER`、类型名、canonical id 或等效内部 token
- **THEN** 这些内部标识 MUST NOT 继续暴露给 `snapshot.enemies[]`
- **THEN** `keywords` MUST 优先保留能帮助策略理解怪物机制的稳定术语

### Requirement: enemy power glossary 不得重复 power 本体说明
系统 MUST 将 `snapshot.enemies[].powers[]` 的 `description` 视为 power 本体说明的 canonical 入口；其 `glossary` MUST 仅保留能补充术语理解的高质量条目。对于与 power 名称或 power description 重复的 identity glossary、空 hint、`missing_hint`、模板占位残留或等效低价值条目，bridge MUST NOT 继续对外暴露。

#### Scenario: enemy power 的 identity glossary 不得重复本体说明
- **WHEN** 某个 enemy power 已具备 canonical `description`
- **THEN** 该 power 的 `glossary` MUST NOT 再暴露仅重复 power 名称或整段 power 说明的 identity 条目
- **THEN** 调用方 MUST 能把 `description` 视为 power 本体说明的唯一主入口

#### Scenario: 低质量 enemy power glossary 条目不得进入对外快照
- **WHEN** bridge 为某个 enemy power 解析 glossary 时遇到空 `hint`、`source="missing_hint"`、模板占位残留或等效未完成渲染文本
- **THEN** 对应 glossary 条目 MUST NOT 出现在最终 `snapshot.enemies[].powers[].glossary` 中
- **THEN** bridge MUST 继续返回可用的 enemy power 对象，而不是因 glossary 清理让整个 enemy 对象失效

### Requirement: Bridge 导出的药水 glossary 必须避免重复本体说明与模板残留
系统 MUST 将药水对象中的 `description` 作为药水本体的 canonical 说明文本；`glossary` MUST 仅保留对术语理解有补充价值的高质量条目。对于与药水自身名称或自身说明重复的 identity glossary、空 hint、`missing_hint`、模板占位残留或等效低价值条目，bridge MUST NOT 继续对外暴露。

#### Scenario: 药水自身说明不得以 glossary identity 条目重复出现
- **WHEN** `snapshot.player.potions[]` 中某瓶药水已经具备 canonical `description`
- **THEN** 该药水的 `glossary` MUST NOT 再暴露仅重复药水名称或整段药水说明的 identity 条目
- **THEN** 调用方 MUST 能把 `description` 视为药水本体说明的唯一主入口

#### Scenario: 低质量 potion glossary 条目不得进入对外快照
- **WHEN** bridge 为某瓶药水解析 glossary 时遇到空 `hint`、`source="missing_hint"`、`{StrengthPower}` 一类模板占位，或等效未完成渲染文本
- **THEN** 对应 glossary 条目 MUST NOT 出现在最终 `snapshot.player.potions[].glossary` 中
- **THEN** bridge MUST 继续返回可用的药水对象，而不是因 glossary 清理而使整个快照失败
