## ADDED Requirements

### Requirement: live validation 必须审计 enemy richer fields 的文本质量
系统 MUST 在 `live-apply-validation` 或等效验证流程中审计 `snapshot.enemies[]` 的 richer fields 质量，至少覆盖 enemy `intent` / `move_name` / `move_description` 中的富文本残留、重复意图展示，`keywords` 中的内部 id 泄漏，以及 `powers[].glossary` 中重复本体说明或低质量 glossary 条目。若发现上述低质量 enemy 字段，验证结果 MUST 标记为失败、`inconclusive` 或等效非成功结论，而不得静默通过。

#### Scenario: 验证发现 enemy 富文本 intent 残留
- **WHEN** live snapshot 中某个 enemy 的 `intent` 或 `move_name` 仍包含 `[font_size]`、`[/font_size]` 或等效 UI markup
- **THEN** 验证流程 MUST 将该结果标记为非成功
- **THEN** artifacts MUST 记录对应 enemy 路径、字段名与失败原因

#### Scenario: 验证发现 enemy keywords 泄漏内部 id
- **WHEN** live snapshot 中某个 enemy 的 `keywords` 仍包含 `POWER.*`、类型名或等效内部 token
- **THEN** 验证流程 MUST 将其识别为低质量 enemy 字段
- **THEN** 结果 MUST 明确区分这是 keyword 泄漏问题，而不是普通文本缺失

#### Scenario: 验证发现 enemy power glossary 重复本体说明
- **WHEN** live snapshot 中某个 enemy power 的 `glossary` 仍包含重复 power 名称、重复 power description、空 hint、`missing_hint` 或模板化条目
- **THEN** 验证流程 MUST 将该结果标记为非成功
- **THEN** artifacts MUST 记录对应 enemy 路径、power 路径、glossary_id 与失败原因
