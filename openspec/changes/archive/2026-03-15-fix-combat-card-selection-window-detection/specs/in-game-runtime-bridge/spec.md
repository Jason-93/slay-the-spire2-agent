## MODIFIED Requirements

### Requirement: 战斗窗口必须区分稳定玩家回合、敌方回合与额外选择窗口
当 `snapshot.phase="combat"` 时，bridge MUST 区分至少三类对外语义：稳定可决策的 `player_turn`、不可提交普通玩家动作的 `enemy_turn` / `combat_transition`，以及战斗内额外选牌窗口。对于非稳定玩家回合窗口，bridge MUST 不导出普通 `play_card` 与 `end_turn` 作为 legal actions。若 runtime 观察到 card selection overlay、player hand selection state 或等效选择界面信号，bridge MUST 优先导出额外选择窗口语义，而不是默认回退成普通 `player_turn`。

#### Scenario: 敌方回合只导出 enemy_turn 且无普通玩家动作
- **WHEN** 当前战斗轮到敌方行动，玩家无法继续提交出牌或结束回合
- **THEN** `metadata.window_kind` MUST 标记为 `enemy_turn` 或等效稳定值
- **THEN** `actions` MUST 不包含普通 `play_card` 或 `end_turn`

#### Scenario: 回合切换过渡中不得暴露过期玩家动作
- **WHEN** 玩家刚提交 `end_turn`，但新一轮玩家决策窗口尚未真正稳定
- **THEN** bridge MUST 将该阶段导出为 `combat_transition`、`enemy_turn` 或等效过渡窗口
- **THEN** bridge MUST NOT 继续暴露上一拍的普通玩家动作集合

#### Scenario: 额外选牌窗口优先于普通 player_turn 导出
- **WHEN** 当前战斗实际处于额外选牌窗口而不是常规出牌窗口
- **THEN** `metadata.window_kind` MUST 优先标记该额外选择窗口
- **THEN** bridge MUST 不再把该窗口默认导出为普通 `player_turn`
- **THEN** `actions` MUST 仅导出与该选择窗口匹配的 legal actions

### Requirement: 回合切换与选择窗口必须提供可诊断 metadata
bridge MUST 为战斗中的回合切换与额外选择窗口导出可诊断 metadata，以便 runner 能区分“等待敌方结算”“等待新回合稳定”“进入二级选牌窗口”。相关 metadata MUST 至少覆盖当前 `window_kind`，并 SHOULD 包含 `current_side`、`selection_kind`、`selection_source_card_id`、`transition_kind`、`overlay_top_type` 或等效字段。

#### Scenario: end_turn 后可诊断等待敌方结算
- **WHEN** 玩家已成功提交 `end_turn`，且接下来处于等待敌方行动的阶段
- **THEN** `snapshot.metadata` MUST 包含可区分当前等待阶段的稳定诊断字段
- **THEN** runner MUST 能仅依据这些字段判断当前不应继续提交普通玩家动作

#### Scenario: combat overlay 选牌窗口导出 overlay diagnostics
- **WHEN** bridge 通过 overlay top screen 或等效覆盖层节点识别到战斗额外选牌窗口
- **THEN** `snapshot.metadata` MUST 导出 `overlay_top_type` 或等效覆盖层类型诊断
- **THEN** diagnostics MUST 能区分“overlay 识别命中”“player hand 识别命中”或等效识别来源
