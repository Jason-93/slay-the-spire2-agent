## MODIFIED Requirements

### Requirement: Bridge 快照必须暴露卡牌描述的解析质量
系统 MUST 在桥接快照中为卡牌说明维持稳定的 canonical `description` 语义，并在可用时优先使用游戏 runtime 已完成上下文渲染的最终文本，而不是模板文本、半渲染文本或 bridge 侧自行拼接的 DSL 结果。对于 `snapshot.player.hand[]`、`draw_pile_cards`、`discard_pile_cards`、`exhaust_pile_cards` 与 `actions[].metadata.card_preview` 中描述同一张 live 卡牌的对象，bridge MUST 尽可能复用同一条 canonical description 语义。若最终渲染结果暂不可得，快照 MUST 继续返回兼容的单个 `description` 文本；质量、来源与回退阶段等诊断信息 MUST 留在日志、内部 diagnostics 或等效排障通道，而 MUST NOT 再要求外部调用方理解额外公开字段。

#### Scenario: 快照中的卡牌描述优先复用游戏最终渲染结果
- **WHEN** bridge 能从 live runtime 为某张卡牌拿到与当前上下文一致的最终 description
- **THEN** `snapshot.player.hand[]`、相关 pile card 或 `actions[].metadata.card_preview` MUST 返回该最终可读文本
- **THEN** 对外 `description` MUST 不再暴露 `IfUpgraded`、`diff()` 或等效模板 DSL 残留

#### Scenario: 最终渲染不可用时仍保持精简兼容输出
- **WHEN** bridge 无法稳定获取某张卡牌的游戏最终 description，只能回退到现有 runtime 字段或模板 fallback
- **THEN** 快照 MUST 仍返回单个可序列化的 `description`
- **THEN** 公共响应 MUST NOT 因此重新暴露 `description_quality`、`description_source` 或等效调试字段

### Requirement: Bridge 不得把模板文本伪装成高质量策略输入
系统 MUST 确保上层通过 snapshot 或 action metadata 读取到的卡牌说明不会在一个位置使用游戏最终描述、另一个位置却继续暴露未解释 DSL 或过时模板。对于同一张 live 卡牌实例，`snapshot.player.hand[]` 与 `actions[].metadata.card_preview` MUST 共享一致的 canonical description 语义；对于 pile cards，bridge MUST 使用与其 pile 语义相匹配的 description，而不是简单复用无上下文模板。若某张卡牌只能回退到较低质量文本，bridge MUST 在所有对外位置保持一致降级，并通过日志或内部 diagnostics 明确指出 fallback，而不是让某处看似“已完成渲染”、某处仍是模板残留。

#### Scenario: hand 与 card_preview 对同一卡牌保持一致 description
- **WHEN** 同一张 live 手牌同时出现在 `snapshot.player.hand[]` 与 `actions[].metadata.card_preview`
- **THEN** 两处的 `description` MUST 共享一致的 canonical 语义
- **THEN** bridge MUST NOT 在一个位置返回游戏最终文本、另一个位置却保留未解释模板

#### Scenario: pile cards 使用与所在 pile 对应的 description 语义
- **WHEN** bridge 导出 `draw_pile_cards`、`discard_pile_cards` 或 `exhaust_pile_cards`
- **THEN** 每张 pile card 的 `description` MUST 反映其所在 pile 的 runtime description context 或等效语义
- **THEN** bridge MUST NOT 把仅适用于 hand 或 preview 的 description 机械复制到所有 pile cards
