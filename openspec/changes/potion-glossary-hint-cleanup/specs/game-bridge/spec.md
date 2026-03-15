## ADDED Requirements

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
