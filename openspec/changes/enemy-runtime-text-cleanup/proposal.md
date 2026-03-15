## Why

当前 `snapshot.enemies[]` 已经有 richer enemy fields，但真实 runtime 里仍会暴露一些低质量文本：例如 `intent` / `move_name` 直接带 UI 富文本标签，`move_name` 只是重复数值意图，`keywords` 混入 `POWER.SLIPPERY_POWER` 这类内部标识。这样的输出会污染大模型输入，也让敌方机制理解仍然偏脆弱。

## What Changes

- 清理 enemy 对外文本语义，规范 `intent`、`intent_raw`、`move_name`、`move_description` 的分工，避免把 UI 富文本、重复数值标签或内部 token 直接暴露给客户端。
- 调整 enemy `keywords` / `traits` / `move_glossary` / `powers[].glossary` 的提取与过滤逻辑，去掉内部 id、低价值重复项，以及与 power 本体说明重复的 glossary 项，并优先保留能帮助理解怪物机制的稳定术语。
- 扩展 live validation 与测试，覆盖 enemy intent 富文本清洗、重复 `move_name` 抑制、内部 keyword 过滤和 move 文本质量回归。
- 为被过滤或降级的 enemy 字段补充日志诊断，便于定位具体怪物、路径、来源与 fallback 阶段。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `game-bridge`: 调整 combat 快照中 enemy richer fields 的对外质量要求，保证面向 agent 的字段是可读、去噪后的 canonical 语义。
- `in-game-runtime-bridge`: 修改 live runtime 的 enemy 文本解析、keyword/trait 提取与去噪规则，避免导出 UI 标签和内部 id。
- `live-apply-validation`: 补充 enemy 文本质量校验，拦截富文本残留、重复 `move_name` 与内部 keyword 泄漏。

## Impact

- 受影响代码主要在 `mod/Sts2Mod.StateBridge/Providers/Sts2RuntimeReflectionReader.cs`、enemy 相关 C# tests、Python validation 脚本与断言。
- `/snapshot.enemies[]` 结构本身基本不变，但 `intent`、`move_name`、`move_description`、`move_glossary`、`keywords` 的输出质量会更稳定。
- 该变更会直接提升大模型对敌方出招、攻击次数、特殊能力与机制标签的理解质量，减少 prompt 中的噪音字段。
