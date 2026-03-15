## Why

当前 combat 快照里的 `player.potions` 仍然只是字符串数组，例如 `"potions": ["迅捷药水", "肌肉药水"]`。这让大模型只能知道“有哪瓶药水”，却不知道药水具体效果，也不知道当前药水栏上限与剩余空间，导致它很难判断该不该保留药水、是否值得现在使用、以及战后是否应该为新药水腾位。

## What Changes

- **BREAKING** 将 `snapshot.player.potions` 从纯名称列表升级为结构化药水对象，至少补齐 `name`、`description`、稳定锚点与可选 glossary。
- 在 `snapshot.player` 中补充药水栏容量信息，例如当前上限、已占用槽位或等效稳定字段，避免上层只能用 `len(potions)` 猜测。
- 保持 `use_potion` 动作可用，同时让动作 metadata 能引用结构化药水信息，便于策略层把“是否使用药水”与“药水效果/背包空间”一起考虑。
- 扩展 live runtime 的药水读取路径，优先从游戏运行时提取药水说明文本，而不是只返回槽位标签。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `game-bridge`: 调整玩家快照中的药水导出，从字符串列表扩展为结构化药水观察与容量信息。
- `rich-runtime-state-schema`: 为玩家对象补充 potion view 与容量字段，确保 schema 对 consumable planning 友好。
- `in-game-runtime-bridge`: 调整 live runtime 的药水提取要求，稳定导出药水说明、知识锚点与药水栏上限。

## Impact

- 受影响代码主要在 `mod/Sts2Mod.StateBridge/Contracts/RuntimeModels.cs`、`mod/Sts2Mod.StateBridge/Providers/Sts2RuntimeReflectionReader.cs`、Python bridge/models/policy 摘要逻辑，以及相关 fixtures / tests。
- `/snapshot` 的 `player.potions` 结构会增强，LLM policy 看到的玩家资源信息会更完整。
- 该变更将直接提升大模型在“是否保留药水位”“是否立刻喝药”“是否为战后新药水留空间”上的决策质量。
