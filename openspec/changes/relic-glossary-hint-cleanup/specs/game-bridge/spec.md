## MODIFIED Requirements

### Requirement: Bridge 必须导出结构化 relic 状态
系统 MUST 在 `snapshot.player` 中导出面向决策的结构化 relic 状态，而不是仅提供 relic 名称字符串列表。`player.relics` MUST 表示当前持有 relic 的结构化对象列表；每个条目至少 MUST 包含 `name`，并在可用时补充 `description`、`canonical_relic_id`、`glossary` 或等效稳定字段。若某个 relic 的说明暂不可读，bridge MUST 仍返回稳定对象结构，而不是回退为纯字符串或让整个 `snapshot` 失效。若导出 `glossary`，bridge MUST 仅返回对 relic 主 description 有补充价值的 glossary 项，并 MUST NOT 泄漏与 relic 自身说明重复、`hint` 为空、或明显属于低质量 fallback 的 glossary 条目。

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
