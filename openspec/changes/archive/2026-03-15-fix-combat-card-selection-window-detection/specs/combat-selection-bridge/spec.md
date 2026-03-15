## MODIFIED Requirements

### Requirement: 战斗内额外选牌窗口必须导出为可区分的 combat 子窗口
当战斗中的某个效果要求玩家在当前可见卡牌集合中继续选择一张牌，例如“消耗 1 张牌”“弃 1 张牌”“从若干候选牌中选择 1 张继续结算”时，bridge MUST 保持 `snapshot.phase="combat"`，并将当前窗口导出为可区分的战斗子窗口，而不是继续伪装成普通 `player_turn`。bridge MUST 优先识别真实运行时中的战斗选牌覆盖层，包括独立 overlay screen、`NPlayerHand` 内部选择态或等效 live 节点；MUST NOT 仅依赖 prompt 文本是否存在才进入该语义。bridge MUST 在 `metadata` 中提供至少 `window_kind`、`selection_kind`、`selection_prompt`、`overlay_top_type` 或等效稳定诊断字段，便于外部 runner 判断当前处于哪一类额外选择。

#### Scenario: 打出需要额外选牌的卡后进入战斗选牌窗口
- **WHEN** 玩家打出一张会要求“再选择一张牌继续结算”的卡牌，且游戏已进入该二级选择窗口
- **THEN** `snapshot.phase` MUST 保持为 `combat`
- **THEN** `metadata.window_kind` MUST 标记为独立于 `player_turn` 的战斗选牌窗口，例如 `combat_card_selection`
- **THEN** bridge MUST 在 `metadata` 中标记触发该窗口的来源卡牌、覆盖层类型或等效诊断信息

#### Scenario: 独立 overlay 选牌屏幕出现时仍识别为 combat_card_selection
- **WHEN** 当前 live 窗口表现为独立的 card selection overlay，例如 `NChooseACardSelectionScreen` 或等效类型，且存在可选卡牌与选择 hook
- **THEN** bridge MUST 将该窗口识别为 `combat_card_selection`
- **THEN** bridge MUST NOT 因 `NPlayerHand` 未显式进入选择态或 prompt 缺失而回落成普通 `player_turn`

#### Scenario: 战斗选牌窗口出现时不得继续伪装普通玩家回合
- **WHEN** 当前窗口实际处于战斗内额外选牌状态
- **THEN** bridge MUST NOT 继续把该窗口导出为仅包含普通 `play_card` / `end_turn` 的标准玩家回合
- **THEN** bridge MUST 优先导出与当前选择窗口匹配的 legal actions
