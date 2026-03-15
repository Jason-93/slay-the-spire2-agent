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
系统 MUST 在桥接快照中稳定暴露卡牌描述的质量语义，使上层调用方能够区分“已经得到真实动态数值”的卡牌与“仍处于模板回退”的卡牌。若 bridge 暂时无法拿到真实值，快照 MUST 保持兼容可读，但 MUST 同时提供足够的质量或来源信息，避免上层误判。

#### Scenario: 快照中的卡牌描述已完成真实数值解析
- **WHEN** bridge 已从 live runtime 拿到当前卡牌实例的真实动态数值
- **THEN** 快照中的 `description_rendered` MUST 为不含模板占位符的最终文本
- **THEN** `description_vars` MUST 能反映对应动态字段的实际值

#### Scenario: 快照中的卡牌描述仍处于模板回退
- **WHEN** bridge 只能拿到模板文本，或 `description_rendered` 仍包含模板占位符
- **THEN** 快照 MUST 继续返回兼容字段，避免中断 autoplay
- **THEN** 快照 MUST 同时暴露足以识别回退状态的质量或来源信息

### Requirement: Bridge 不得把模板文本伪装成高质量策略输入
系统 MUST 确保上层通过 snapshot 或 action metadata 读取到的卡牌描述不会被错误标记为“已渲染完成”。如果某张卡牌的 `card_preview`、`snapshot.player.hand` 或等效结构仍停留在模板占位符层，bridge MUST 在对应输出上保持一致的回退语义。

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

