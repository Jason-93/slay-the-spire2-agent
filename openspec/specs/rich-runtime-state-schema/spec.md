# rich-runtime-state-schema Specification

## Purpose
定义面向 STS2 agent 的 richer runtime state schema，明确 combat facts、run facts 与 metadata 的分层边界，为后续长期规划与知识层扩展预留稳定结构。
## Requirements
### Requirement: rich runtime state schema 必须区分战斗事实与整局事实
系统 MUST 为 agent 暴露一个可扩展的 runtime state schema，并至少区分 `combat_state`、`run_state` 与诊断性 `metadata` 三类信息。`combat_state` MUST 聚焦当前决策窗口直接相关的战斗事实；`run_state` MUST 承载 act、floor、room、map 等整局规划上下文；`metadata` MUST 继续承载兼容性与诊断信息，而不是承担主要业务语义。

#### Scenario: 读取 combat 决策快照
- **WHEN** 外部 agent 在战斗窗口读取当前 snapshot
- **THEN** 响应 MUST 同时包含当前战斗事实与最小整局上下文
- **THEN** 战斗相关字段 MUST 不再只能散落在 `metadata` 中表达

### Requirement: rich runtime state schema 必须为卡牌与敌人提供可扩展语义字段
系统 MUST 允许在卡牌、敌人与玩家对象上追加 richer 字段，包括但不限于卡牌描述、升级态、目标类型、traits、结构化 intent 与 powers。新增字段 MUST 采用追加式、可选字段策略，缺失时 MUST 退化为 `null`、空数组或等效空值，而不是破坏现有基础字段。

#### Scenario: 某些 richer 字段暂时无法从 runtime 读取
- **WHEN** bridge 当前只能导出基础字段，但某个 richer 字段尚未稳定提取
- **THEN** snapshot MUST 仍保留现有基础字段并正常返回
- **THEN** 缺失的 richer 字段 MUST 以兼容方式留空，而不是导致整个 snapshot 无效

### Requirement: rich runtime state schema 必须预留稳定知识锚点
系统 MUST 为卡牌、敌人、遗物等对象预留稳定知识锚点，例如 `canonical_*_id` 或等效标识，以支持未来外挂怪物机制百科、卡牌百科与长期规划逻辑。该锚点 MUST 与运行时实例标识分离，避免将 live action 所需实例 id 与静态知识 id 混用。

#### Scenario: 同名卡牌在同一手牌中同时存在
- **WHEN** 当前手牌中存在多张同名牌，且未来系统需要把这些牌映射到统一百科条目
- **THEN** snapshot MUST 仍能用实例标识区分每一张牌
- **THEN** schema MUST 允许这些实例共享同一个稳定知识锚点

### Requirement: rich runtime state schema 必须为药水保留独立对象语义
系统 MUST 在 `player` 下为药水定义独立的结构化 schema，而不是把药水长期限制为标签字符串。该 schema MUST 允许导出 `name`、`description`、`canonical_potion_id`、`glossary` 或等效 richer fields，并保持缺失字段时的兼容退化能力。

#### Scenario: 玩家对象携带可扩展的 potion view
- **WHEN** 外部 agent 读取包含玩家资源的快照
- **THEN** `player.potions` MUST 支持结构化 potion view，而不是只能是字符串列表
- **THEN** potion view MUST 允许后续继续追加 richer 字段，而不破坏现有基础语义

### Requirement: rich runtime state schema 必须暴露药水栏容量上下文
系统 MUST 在 `player` 对象中为药水资源补充稳定的容量上下文字段，例如 `potion_capacity` 或等效命名，以便策略层同时理解“当前有哪些药水”和“还能再持有多少药水”。

#### Scenario: 策略层可同时读取当前药水与药水上限
- **WHEN** 外部 agent 在战斗或奖励后阶段读取玩家状态
- **THEN** `player` MUST 同时表达当前药水列表与药水栏上限
- **THEN** 调用方 MUST 不需要依赖角色默认值或硬编码规则推断药水上限

