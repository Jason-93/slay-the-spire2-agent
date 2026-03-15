## ADDED Requirements

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

### Requirement: relic 说明对象必须遵守精简 canonical schema
系统 MUST 将 relic 说明对象与 cards、powers、potions 一样收敛为面向决策的精简 schema。若 relic 存在说明文本，对外协议 MUST 以 canonical `description` 为主；`description_quality`、`description_source`、`description_vars` 或其他仅用于排障的内部字段 MUST NOT 暴露给客户端。

#### Scenario: relic 对外只暴露 canonical description
- **WHEN** bridge 成功为某个 relic 解析出可读说明文本
- **THEN** `snapshot.player.relics[]` MUST 返回 `description`
- **THEN** 公共响应 MUST NOT 额外暴露仅用于排障的 description diagnostics 字段
