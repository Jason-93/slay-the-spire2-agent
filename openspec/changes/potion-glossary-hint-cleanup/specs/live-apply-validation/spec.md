## ADDED Requirements

### Requirement: live validation 必须审计 potion glossary 的文本质量
系统 MUST 在 `live-apply-validation` 或等效验证流程中审计 `snapshot.player.potions[].glossary` 的文本质量，至少覆盖空 hint、`missing_hint`、模板占位残留，以及与药水本体说明重复的 identity glossary。若发现上述低质量条目，验证结果 MUST 标记为失败、`inconclusive` 或等效非成功结论，而不得静默通过。

#### Scenario: 验证发现模板化 potion glossary
- **WHEN** live snapshot 中某瓶药水的 glossary `hint` 仍包含 `{StrengthPower}`、`{Block}` 或其他模板占位
- **THEN** 验证流程 MUST 将该结果标记为非成功
- **THEN** artifacts MUST 记录对应药水路径、glossary_id 与失败原因

#### Scenario: 验证发现药水 identity glossary 重复本体说明
- **WHEN** 某瓶药水的 glossary 条目仅重复药水名称或药水 canonical `description`
- **THEN** 验证流程 MUST 将其识别为低质量 glossary 条目
- **THEN** 结果 MUST 明确区分这是重复说明问题，而不是普通 description 缺失
