# combat-selection-bridge Specification

## Purpose
TBD - created by archiving change fix-combat-transition-selection-bridge. Update Purpose after archive.
## Requirements
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

### Requirement: 战斗选牌窗口必须导出稳定的选择动作与卡牌实例定位
当 bridge 识别到战斗内额外选牌窗口时，系统 MUST 为每个当前可选条目生成稳定 legal action，并使用实例级 `card_id` 或等效稳定参数定位目标牌。若该窗口允许关闭、取消或跳过，bridge MAY 额外生成 `cancel_combat_selection`；若规则不允许取消，则 MUST NOT 导出该动作。

#### Scenario: 可选卡牌按展示列表生成 choose_combat_card
- **WHEN** 当前战斗选牌窗口中存在 N 张可选卡牌
- **THEN** `actions` MUST 生成 N 个 `type="choose_combat_card"` 的 legal actions
- **THEN** 每个动作 MUST 通过 `params.card_id`、`params.selection_index` 或等效稳定参数与具体可选卡牌一一对应
- **THEN** 外部 agent MUST 能仅依赖当前 `snapshot` 与 `actions` 完成选择，而不需要猜测隐藏索引

#### Scenario: 选择窗口不可取消时不生成 cancel_combat_selection
- **WHEN** 当前额外选牌窗口的游戏规则不允许取消、关闭或跳过
- **THEN** `actions` MUST NOT 包含 `cancel_combat_selection`
- **THEN** bridge MUST 在 `metadata` 中说明取消不可用或等效诊断原因

### Requirement: 战斗选牌动作必须驱动真实结算并在窗口变化时返回明确拒绝语义
bridge MUST 将 `choose_combat_card` 映射到游戏内真实的选牌确认流程，并在执行前校验当前选择窗口仍与导出动作对应。若可选牌集合、来源效果或窗口本身已变化，bridge MUST 拒绝执行并返回 `stale_action`、`selection_window_changed` 或等效明确错误原因，而不是退化为泛化的 `play_rejected`。

#### Scenario: 选择一张牌后继续完成该效果结算
- **WHEN** 外部 agent 提交一个命中当前 legal action 集的 `choose_combat_card`
- **THEN** bridge MUST 选择与该动作参数对应的那一张牌
- **THEN** 后续 `snapshot` MUST 反映该效果继续结算后的新 live 状态或新的决策窗口

#### Scenario: 选择窗口已变化时拒绝过期选择动作
- **WHEN** 额外选牌窗口已关闭、来源效果已结算，或当前可选牌集合与导出时不一致
- **THEN** bridge MUST 拒绝执行该 `choose_combat_card`
- **THEN** 返回结果 MUST 明确标记为 `stale_action`、`selection_window_changed` 或等效错误原因

