## Why

当前 relic 的 `glossary` 在 live runtime 中仍会出现 hint 质量问题：一类是与 relic 自身说明重复，造成 agent 读到冗余信息；另一类是像 `格挡` 这类二级 glossary 锚点会退化为 `missing_hint` 或保留未渲染变量模板，降低大模型对 relic 语义的可用性。既然 relic description 已经结构化导出，现在需要继续把 relic glossary 收敛成更干净、更稳定的决策语义。

## What Changes

- 清理 relic glossary 的生成规则，避免把 relic 自身 title/hint 作为重复 glossary 项暴露给客户端。
- 改进 relic description 中二级 glossary（如 `格挡`、`升级`、`遗物`）的 hint 解析与降级策略，优先返回稳定、已渲染的用户向说明。
- 对无法可靠解析的 glossary hint 做更严格的过滤与日志记录，避免继续向客户端暴露 `hint=null`、`missing_hint` 或模板化重复项。
- 保持 relic 主体 `description` 不变，本次只收敛 `glossary` 的质量与去重逻辑，不引入新的客户端字段。

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `game-bridge`: 调整 relic glossary 的对外质量约束，要求避免重复、空 hint 与低价值 glossary 项泄漏到 `snapshot.player.relics`。
- `in-game-runtime-bridge`: 调整 live runtime 的 relic glossary hint 提取与降级规则，要求优先输出已渲染、非模板、非重复的 glossary hint。

## Impact

- 主要影响 `mod/Sts2Mod.StateBridge/Providers/Sts2RuntimeReflectionReader.cs` 中 relic glossary 的候选筛选、hint sourcing、去重与 diagnostics。
- 会影响 live snapshot 中 `player.relics[].glossary` 的内容质量，但不改变 relic 主体 schema。
- 需要补充 fixture / live validation，覆盖重复 glossary、`missing_hint` 与模板 hint 的回归场景。
