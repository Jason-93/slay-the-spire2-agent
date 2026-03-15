## Why

当前 `snapshot.player.relics` 仍然只是字符串数组，例如 `"燃烧之血"`、`"小型扭蛋"`。这对大模型决策不够用：agent 知道玩家持有什么 relic，却不知道这些 relic 当前会提供什么效果，也无法把 relic 与长期知识锚点稳定关联。

## What Changes

- **BREAKING** 将 `snapshot.player.relics` 从纯字符串列表升级为结构化 relic 对象列表，至少包含 `name`，并在可用时补充 `description`、`canonical_relic_id`、`glossary` 或等效稳定字段。
- 调整 live runtime relic 提取链路：优先从游戏 runtime 的 relic 模型、hover tip、description 或 localization 入口读取用户向说明文本，而不是只导出名称。
- 让 fixture、Python models、bridge decode 与相关验证脚本同步接受结构化 relic schema。
- 对于暂时无法稳定解析 description 的 relic，保持 fail-safe：仍返回结构化对象，不让整个 `snapshot` 因单个 relic 文本失败而失效。
- 复用现有 glossary / text diagnostics 约定，确保 relic 说明也能输出稳定的 markdown 化文本和可诊断来源。

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `game-bridge`: 扩展玩家 relic 观测语义，要求对外导出结构化 relic 对象与可读 description，而不再只是名称列表。
- `in-game-runtime-bridge`: 扩展 live runtime 的 relic 文本提取与降级约束，要求优先从游戏运行时导出 relic 的 canonical description。

## Impact

- 主要影响 `mod/Sts2Mod.StateBridge` 的 contracts、runtime extractor、fixture provider 与 Python 侧 snapshot decode。
- 会影响 `snapshot.player.relics` 的公共 schema，因此属于客户端可见的 breaking change。
- 需要更新单测、fixture / live validation，以及可能依赖 relic 字符串数组的策略摘要逻辑。
