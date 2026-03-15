## Why

当前 bridge 在卡牌说明导出上，仍然经常落回模板文本或半渲染文本。像 `CARD.TRUE_GRIT` 这类卡牌会把 `{IfUpgraded:show:| 随机}` 直接暴露给外部 agent，导致大模型读到的不是游戏真实 UI 所展示的最终描述，也会误解升级前后语义。既然 runtime 内部已经存在按当前上下文生成说明的方法，就应该优先复用游戏自己的最终渲染结果，而不是长期靠 bridge 侧补模板解析。

## What Changes

- 调整 live card description 提取策略：优先调用游戏 runtime 自带的最终描述生成入口，获取与当前 pile / 上下文一致的完整用户向文本。
- 当游戏最终描述生成成功时，`snapshot.player.hand[]`、牌堆 cards 与 `actions[].metadata.card_preview` 必须复用该 canonical description。
- 保留现有模板解析路径作为 fallback，但只有在游戏最终描述不可用或调用失败时才使用。
- 强化 diagnostics 与日志，明确区分“来自游戏最终渲染”“来自现有 runtime 文本字段”“来自模板 fallback”的不同来源。
- 重点修复升级条件、上下文条件与选择器类描述残留问题，例如 `IfUpgraded`、pile / preview 相关语义，避免把内部模板 DSL 暴露给 agent。

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `game-bridge`: 调整对外卡牌 description 的 canonical 语义，优先输出游戏最终渲染结果，而不是模板残留文本。
- `in-game-runtime-bridge`: 调整 live runtime 的卡牌说明提取要求，优先走游戏内最终描述 API，并在失败时再回退到现有字段与模板渲染。

## Impact

- 主要影响 `mod/Sts2Mod.StateBridge/Providers/Sts2RuntimeReflectionReader.cs` 的卡牌说明提取路径，以及相关 card preview / fixture / tests。
- 会影响 `/snapshot.player.hand[]`、`draw_pile_cards`、`discard_pile_cards`、`exhaust_pile_cards` 与 `play_card` metadata 中的 description 文本质量。
- 对外 schema 字段名预计不变，但 description 内容与 `description_source` 等 diagnostics 语义会调整。
