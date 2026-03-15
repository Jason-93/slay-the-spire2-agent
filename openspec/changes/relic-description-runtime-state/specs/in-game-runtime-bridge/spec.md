## MODIFIED Requirements

### Requirement: live snapshot 与 actions 必须导出可读的用户向文本
系统 MUST 对 in-game runtime bridge 中的主要文本字段执行统一解析，至少覆盖 relics、potions、rewards、map nodes、cards、powers、enemies 与 action labels。当字段背后存在 `LocString`、动态变量或类似本地化容器时，bridge MUST 在 mod 端直接输出面向玩家的最终可读文本，而不得把模板替换职责下放给 Python client、policy 或其他外部调用方。对于 cards，当 runtime 暴露 `GetDescriptionForPile(...)`、`GetDescriptionForUpgradePreview()` 或等效最终描述 API 时，bridge MUST 优先使用这些 API 生成 canonical `description`，并根据 hand / draw / discard / exhaust / preview 的上下文选择对应的 pile 或 preview 语义；只有在这些最终描述入口不可用时，bridge 才能退回 `RenderedDescription`、`RenderedText` 或模板 fallback。对于 relics，bridge MUST 不再只导出名称，而是输出结构化 relic 对象，并优先从 relic 模型、hover tip、`Description`、`SmartDescription`、localization 或等效 runtime 文本来源解析 canonical `description`。对于带说明的实体，对外协议中的 `description` MUST 作为唯一 canonical 文本字段；bridge MUST NOT 再要求调用方在 `description`、`description_rendered`、`description_raw` 之间自行挑选真实语义。若原始文本包含 `[gold]格挡[/gold]` 这类 glossary 富文本高亮，bridge MUST 在对外 `description` 中将其规范化为 `**格挡**` 这类稳定标记。

#### Scenario: relic 说明由 mod 端直接导出为 canonical description
- **WHEN** 玩家持有的某个 relic 在 runtime 中存在可读 description、hover tip 或等效文本来源
- **THEN** `snapshot.player.relics[]` MUST 直接导出该 relic 的 canonical `description`
- **THEN** 外部 client MUST NOT 需要再根据 relic 名称查表或自行渲染说明文本

#### Scenario: relic 暂时无说明时仍返回结构化对象
- **WHEN** 某个 relic 当前只能从 runtime 中读取到名称，拿不到稳定的 description
- **THEN** bridge MUST 仍返回该 relic 的结构化对象
- **THEN** bridge MUST 保持整个 `snapshot` 成功，而不是因单个 relic 文本失败中断响应

### Requirement: 文本解析失败时必须提供可诊断的降级信息
系统 MUST 在文本解析失败、只能拿到模板、或仅能部分解析时保持 fail-safe，并在日志、内部 metadata 或等效 diagnostics 结构中暴露足够的调试信息。对于 cards，diagnostics MUST 至少能够定位对象路径、`card_id` 或 `canonical_card_id`、description context、选择的 source 与失败阶段。对于 relics，diagnostics MUST 至少能够定位 relic 名称或 `canonical_relic_id`、对象路径与 description 的 fallback 阶段。bridge MUST 将“最终可读文本”的公开语义继续收敛到单个 `description` 字段，而不是让客户端通过额外公开 schema 猜测哪些文本仍含占位符。bridge MAY 在日志中保留调试原文，但 MUST NOT 因为个别文本字段解析失败而使整个 `snapshot` 或 `actions` 构建失败。

#### Scenario: relic description 读取失败时记录日志并安全降级
- **WHEN** 某个 relic 无法从 runtime 文本来源中稳定解析 description
- **THEN** bridge MUST 记录包含 relic 标识、对象路径与 fallback 阶段的 warning 或等效 diagnostics
- **THEN** 对外 `snapshot.player.relics[]` MUST 仍返回至少包含 `name` 的结构化对象
