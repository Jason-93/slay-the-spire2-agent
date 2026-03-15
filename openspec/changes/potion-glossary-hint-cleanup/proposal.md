## Why

当前 `snapshot.player.potions[]` 虽然已经是结构化对象，但药水的 `glossary` 仍会暴露低质量条目：一类是药水自身的 hover tip 被重复塞进 glossary，另一类是 `hint` 里仍残留 `{StrengthPower}` 这类未渲染模板。这样会让大模型误把 glossary 当成第二份 description，甚至读到未完成渲染的占位文本，削弱药水使用决策质量。

## What Changes

- 清理药水 glossary 的后处理逻辑，过滤与药水自身说明重复的 identity 条目、空 hint、`missing_hint`、模板残留和等效低价值条目。
- 调整药水 description / glossary hint 的 sourcing 优先级，优先保留游戏 runtime 已渲染的可读说明，而不是把模板 hover tip 直接透出给客户端。
- 扩展 live validation 与 fixture 断言，确保 `snapshot.player.potions[].glossary` 不再暴露模板化、重复或低质量 hint。
- 为被过滤或回退的药水 glossary 项补充日志诊断，便于定位具体药水、字段路径与 fallback 原因。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `game-bridge`: 调整对外药水说明对象语义，保证 potion glossary 只暴露对决策有价值的条目。
- `in-game-runtime-bridge`: 修改 live runtime 的药水 description / glossary 解析与过滤逻辑，优先输出真实已渲染文本。
- `live-apply-validation`: 补充 potion glossary 质量校验，拦截模板化、空 hint 和重复说明条目。

## Impact

- 受影响代码主要在 `mod/Sts2Mod.StateBridge/Providers/Sts2RuntimeReflectionReader.cs`、live validation 脚本、Python 测试与相关 fixtures。
- `/snapshot` 中药水对象的字段结构不新增，但 `description` 与 `glossary` 的质量会更稳定，减少模板文本和重复说明噪音。
- 该变更会直接提升大模型对“是否立刻喝药 / 是否保留药水”的理解质量，并降低客户端额外清洗文本的成本。
