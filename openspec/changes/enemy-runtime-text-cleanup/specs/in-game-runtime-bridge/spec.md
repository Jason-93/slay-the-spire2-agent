## ADDED Requirements

### Requirement: live runtime enemy 文本必须清理富文本与低价值重复标签
当 bridge 从 live runtime 导出 enemy 当前行动信息时，`intent`、`intent_raw`、`move_name` 与 `move_description` MUST 经过统一的文本规范化，去除 `[font_size]`、纯展示性乘号格式、富文本残留或等效 UI markup。若 `move_name` 只是当前意图的重复展示而非独立招式名，bridge MUST 抑制该字段，而不是把 UI 标签原样暴露给客户端。

#### Scenario: 数值多段攻击的富文本 intent 被规范化
- **WHEN** runtime 对某个敌人的当前意图返回 `2[font_size=18]×3[/font_size]` 或等效富文本标签
- **THEN** 对外导出的 enemy 文本字段 MUST NOT 保留该富文本 markup
- **THEN** bridge MUST 继续导出结构化 `intent_type`、`intent_damage`、`intent_hits` 与可读 `move_description`

#### Scenario: move_name 只是意图展示标签时被抑制
- **WHEN** runtime 的 `move_name` 与 `intent` 仅在排版、数字格式或展示标签上不同，而没有额外机制语义
- **THEN** bridge MUST 将 `move_name` 置空或等效抑制
- **THEN** bridge MUST NOT 把该重复标签继续作为独立 enemy richer field 暴露

### Requirement: live runtime enemy keywords 必须过滤内部 id 与重复 token
当 bridge 为 enemy 导出 `keywords`、`traits` 与 `move_glossary` 时，MUST 过滤 power id、canonical id、类型名或等效内部 token，并去掉与 powers、intent 或 move 文本完全重复的低价值项。若过滤后没有稳定的高价值关键字，bridge MAY 返回空数组，但 MUST 保持整个 enemy 对象成功导出。

#### Scenario: keyword 提取结果包含 power id 时被过滤
- **WHEN** 某个敌人的 keyword 候选中包含 `POWER.SLIPPERY_POWER` 或等效内部对象标识
- **THEN** 最终 `snapshot.enemies[].keywords` MUST NOT 包含该内部 id
- **THEN** bridge MUST 优先保留真正描述机制的术语或 glossary 锚点

#### Scenario: enemy keyword 过滤后仍保持 fail-safe
- **WHEN** 某个敌人的 keyword 候选大多属于内部 token、重复 move 术语或低价值噪音
- **THEN** bridge MUST 仍返回可序列化的 enemy 对象
- **THEN** `keywords` MAY 降级为空数组，但 MUST NOT 因过滤逻辑使整个 combat snapshot 失败

### Requirement: live runtime enemy power glossary 必须过滤重复本体说明与低质量条目
当 bridge 为 `snapshot.enemies[].powers[]` 导出 `glossary` 时，MUST 在 runtime 解析后执行质量过滤，只保留真正补充术语语义的 glossary anchors。若某条 glossary 与 power 本体名称或 canonical `description` 重复，或者只能得到空 hint、`missing_hint`、模板化 hint，bridge MUST 记录 diagnostics 并过滤该条目。

#### Scenario: enemy power glossary 与 power description 重复时被过滤
- **WHEN** 某个 enemy power 的 glossary anchor 仅重复该 power 的名称或整段 power 说明
- **THEN** bridge MUST 将该 glossary 条目从最终 `snapshot.enemies[].powers[].glossary` 中过滤掉
- **THEN** `description` MUST 继续作为该 power 的 canonical 本体说明

#### Scenario: enemy power glossary 低质量时过滤并记录日志
- **WHEN** 某个 enemy power 的 glossary anchor 为空 hint、`missing_hint` 或模板残留
- **THEN** bridge MUST 过滤该条目
- **THEN** bridge MUST 在日志或等效 diagnostics 中记录 enemy 标识、power 标识、路径、来源与过滤原因
