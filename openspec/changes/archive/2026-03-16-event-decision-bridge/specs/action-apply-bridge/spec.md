## MODIFIED Requirements

### Requirement: 核心窗口必须具备首批真实动作执行映射
系统 MUST 为 `combat`、`reward`、`map`、`event` 四类核心窗口提供首批真实执行映射，至少覆盖 `play_card`、`end_turn`、`choose_reward`、`skip_reward`、`choose_map_node`、`choose_combat_card`、`choose_event_option`、`continue_event`，并在规则允许时支持 `cancel_combat_selection`。bridge MUST 只执行当前 legal actions 中存在的动作，不得猜测未枚举动作。对于 `reward` phase，bridge MUST 同时覆盖奖励列表（例如 `NRewardsScreen`）与奖励链路中的“卡牌奖励选择界面”（选牌二级界面）的动作执行映射。对于 `combat` phase 中的额外选牌窗口，bridge MUST 将“选择一张牌继续结算”建模为独立动作执行流程，而不是继续复用 `play_card`。对于 `event` phase，bridge MUST 将“选择事件分支”和“继续离开事件”建模为独立动作执行流程，而不是复用 reward 或 map 动作。

#### Scenario: 战斗回合执行打牌动作
- **WHEN** 当前 phase 为 `combat` 且 legal actions 中存在某个 `play_card`
- **THEN** bridge MUST 能把该动作映射到游戏内真实出牌流程
- **THEN** 执行后新的 `snapshot` MUST 反映更新后的 live 状态或新的决策上下文

#### Scenario: 奖励窗口执行选项或跳过
- **WHEN** 当前 phase 为 `reward` 且 legal actions 中存在 `choose_reward` 或 `skip_reward`
- **THEN** bridge MUST 能触发对应奖励选择或跳过逻辑
- **THEN** 执行结果 MUST 导向新的窗口状态、地图状态或下一决策

#### Scenario: 卡牌奖励选择界面执行选卡
- **WHEN** 当前 phase 为 `reward` 且当前窗口为卡牌奖励选择界面，并且 legal actions 中存在某个 `choose_reward`
- **THEN** bridge MUST 使用该 action 的 `params.reward_index` 定位当前可选卡牌并触发真实选择流程
- **THEN** bridge MUST NOT 选择与 `reward_index` 不一致的其他卡牌
- **THEN** 若当前界面已变化或可选项数量不一致，bridge MUST 拒绝执行并返回 `stale_action` 或等效错误原因

#### Scenario: 卡牌奖励选择界面执行跳过
- **WHEN** 当前 phase 为 `reward` 且当前窗口为卡牌奖励选择界面，并且 legal actions 中存在 `skip_reward`
- **THEN** bridge MUST 触发该界面对应的跳过/关闭逻辑并退出该奖励步骤
- **THEN** 若当前奖励规则不允许跳过或跳过钩子不可用，bridge MUST 拒绝执行并返回 `runtime_incompatible` 或等效错误原因

#### Scenario: 地图窗口执行路线选择
- **WHEN** 当前 phase 为 `map` 且 legal actions 中存在某个 `choose_map_node`
- **THEN** bridge MUST 只允许选择当前可达节点
- **THEN** 执行后 MUST 进入与该节点对应的后续 run 状态

#### Scenario: 战斗额外选牌窗口执行 choose_combat_card
- **WHEN** 当前 phase 为 `combat` 且当前窗口为战斗内额外选牌窗口，并且 legal actions 中存在某个 `choose_combat_card`
- **THEN** bridge MUST 使用该 action 的实例级参数定位当前被选中的卡牌并触发真实选择流程
- **THEN** 若当前选择窗口已变化或该牌已不再可选，bridge MUST 拒绝执行并返回 `stale_action`、`selection_window_changed` 或等效错误原因

#### Scenario: event 窗口执行 choose_event_option
- **WHEN** 当前 phase 为 `event` 且当前窗口为事件选项窗口，并且 legal actions 中存在某个 `choose_event_option`
- **THEN** bridge MUST 使用该 action 的 `params.option_index` 定位当前可见选项并触发真实选择流程
- **THEN** bridge MUST NOT 选择与 `option_index` 不一致的其他事件分支
- **THEN** 若当前事件界面已变化、选项数量不一致或目标按钮不可点击，bridge MUST 拒绝执行并返回 `stale_action`、`runtime_incompatible` 或等效错误原因

#### Scenario: event 收尾窗口执行 continue_event
- **WHEN** 当前 phase 为 `event` 且当前窗口只剩继续/离开/确认动作，并且 legal actions 中存在 `continue_event`
- **THEN** bridge MUST 触发对应的继续推进逻辑
- **THEN** 执行结果 MUST 导向新的 `event`、`map`、`combat`、`reward` 或等效后续窗口

#### Scenario: event 动作不得在错误窗口复用
- **WHEN** 外部 agent 提交旧的 `choose_event_option` 或 `continue_event`，但当前已经不再处于对应的 event 子窗口
- **THEN** bridge MUST 拒绝执行该动作
- **THEN** 返回结果 MUST 标记为 `stale_action`、`selection_window_changed`、`runtime_not_ready` 或等效结构化错误原因
