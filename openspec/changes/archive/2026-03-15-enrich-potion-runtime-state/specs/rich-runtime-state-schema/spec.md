## ADDED Requirements

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
