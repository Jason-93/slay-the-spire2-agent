## ADDED Requirements

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
