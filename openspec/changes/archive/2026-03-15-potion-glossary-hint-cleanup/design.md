## Context

当前 bridge 已经能导出结构化 `player.potions[]`，但药水文本链路仍存在和 relic 类似的问题：runtime 某些 hover tip 会返回模板化文本，例如 `获得{StrengthPower}点**力量**`，而这些内容会被直接写进 potion glossary；同时，药水自身名称与完整说明也会被当成一条 glossary anchor 透出，形成“description 已经有一份，glossary 里再重复一份”的噪音。由于 LLM prompt 会直接消费这些字段，这类低质量文本会污染决策输入。

这个变更同时影响 C# runtime 文本解析、bridge 对外 schema 质量语义，以及 Python live validation。它不打算新增字段，而是收紧现有 `description` / `glossary` 的 canonical 语义：`description` 负责给出药水本体说明，`glossary` 只保留真正需要补充术语解释的高质量条目。

## Goals / Non-Goals

**Goals:**
- 让 `snapshot.player.potions[].description` 优先代表游戏已渲染的 canonical 药水说明，而不是模板 hover tip。
- 过滤 potion glossary 中与药水自身 description 重复、`hint` 为空、`missing_hint`、模板占位残留或等效低价值条目。
- 为仍然保留的药水 glossary 条目优先补齐真实 hint sourcing，并在无法获取时记录日志而不是静默伪装成高质量文本。
- 在 live validation 中加入 potion glossary 质量断言，避免后续回归把模板化 hint 再暴露给客户端。

**Non-Goals:**
- 本次不新增药水目标选择、实例级 potion id 或药水使用策略逻辑。
- 本次不扩展独立 glossary 百科库，也不维护完整药水说明硬编码表。
- 本次不改动客户端 prompt 协议结构，只清理现有文本质量。

## Decisions

### 决策 1：沿用“canonical description + 精简 glossary”模型，而不是向客户端暴露更多诊断字段
- 方案：继续只对外导出 `description` 与 `glossary`，把模板检测、fallback 来源、过滤原因留在 mod 日志与 validation diagnostics。
- 原因：用户已经明确不希望客户端再看到 `description_quality` 一类解析细节；药水文本也应保持与卡牌、relic 一致的精简消费方式。
- 备选方案：新增 `description_source`、`glossary_quality` 等字段。放弃原因是会把内部排障协议重新泄漏到客户端。

### 决策 2：药水 identity glossary 走 post-process 过滤，而不是完全禁止 runtime anchor 生成
- 方案：保留现有 glossary 解析主路径，但在 potion 结果落盘前做一次 post-process，过滤药水自身名称 + 自身说明重复项、模板化 hint、空 hint 和重复 anchor。
- 原因：runtime 不同来源仍可能给出有价值的二级术语（如 `力量`、`虚弱`）；完全关闭 potion glossary 会丢掉这部分信息。
- 备选方案：对药水只保留 description，不再导出 glossary。放弃原因是会损失术语解释能力，不利于 LLM 处理陌生药水。

### 决策 3：模板检测优先依赖通用占位符识别，而不是为每瓶药水单独写规则
- 方案：复用现有 description placeholder 检测能力，把 `{StrengthPower}`、`{Block}`、`LocString` 残留等模板模式统一视为低质量 hint。
- 原因：问题并不只发生在“肌肉药水”这一瓶药水；使用通用规则更容易扩展到其他 potions、relics 或敌人文本。
- 备选方案：只为已知问题药水做定向替换。放弃原因是维护成本高，且新药水仍会继续漏出模板。

### 决策 4：真实 hint sourcing 失败时优先告警和过滤，而不是保留“看起来像说明”的模板文本
- 方案：如果 glossary anchor 只能拿到模板 hover tip 或 `missing_hint`，则过滤该条目，并在日志记录药水标识、path、来源与过滤原因。
- 原因：对大模型而言，错误或半渲染说明通常比缺失说明更糟；保守删掉低质量 anchor 更安全。
- 备选方案：继续暴露模板 hint，并依赖客户端自行清洗。放弃原因是会重复把文本修复复杂度推回 Python/LLM 侧。

### 决策 5：live validation 直接把 potion glossary 纳入失败条件
- 方案：扩展现有 description audit，对 `snapshot.player.potions[].glossary` 检查空 hint、`missing_hint`、模板占位与 identity duplication。
- 原因：这类问题最容易在真实 runtime 中回归，仅靠单元测试无法覆盖所有药水文本来源。
- 备选方案：只打印 warning，不让验证失败。放弃原因是容易再次把低质量文本带进线上 prompt。

## Risks / Trade-offs

- [Risk] 某些药水的 runtime 只能拿到模板 hover tip，过滤后 glossary 可能变少 -> Mitigation：保留 canonical `description` 作为主说明，并对缺失 glossary 记录日志，后续按需要补真实来源。
- [Risk] identity 去重规则过严，可能误删与药水名同名但确有补充信息的 anchor -> Mitigation：去重时同时比较 `display_text`、`glossary_id` 与 `hint` 是否等价，并保留日志便于回看。
- [Risk] validation 新增失败条件后，live 测试更容易因为单瓶药水文本问题失败 -> Mitigation：先在 fixture 中补充覆盖，再针对真实 runtime 做一轮定向联调，确保失败信息包含药水路径与原因。
- [Risk] potion 文本清理逻辑与 relic / card 逻辑分叉过多 -> Mitigation：尽量复用现有 placeholder 检测、glossary filtering 与 logging helper，只在 potion 特有 identity 判断上加薄层包装。
