## ADDED Requirements

### Requirement: live runtime 药水说明必须优先使用已渲染文本并清理低质量 glossary
当 bridge 从 live runtime 导出 `snapshot.player.potions[]` 时，药水本体 `description` MUST 优先使用游戏已经渲染完成的可读文本，而不是直接透传仍含占位符的 hover tip 模板。对于药水 glossary，bridge MUST 在 runtime 解析后执行质量过滤，只保留真实术语说明；若某条 glossary 只能得到模板化或缺失的 hint，bridge MUST 记录 diagnostics 并过滤该条目。

#### Scenario: hover tip 仍是模板时回退到可读 canonical description
- **WHEN** 某瓶药水的 runtime hover tip 或等效文本来源仍包含 `{StrengthPower}`、`{Block}` 或其他未完成渲染的模板占位
- **THEN** `snapshot.player.potions[]` 的 canonical `description` MUST NOT 直接使用该模板文本
- **THEN** bridge MUST 继续尝试已渲染 description、localization 或等效真实文本来源

#### Scenario: 低质量 potion glossary 条目被过滤并留下日志
- **WHEN** 某瓶药水的 glossary anchor 为空 hint、`missing_hint`、模板残留，或与药水自身 description 重复
- **THEN** bridge MUST 将该条目从最终 potion glossary 中过滤掉
- **THEN** bridge MUST 在日志或等效 diagnostics 中记录药水标识、对象路径、来源与过滤原因
