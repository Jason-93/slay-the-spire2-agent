## MODIFIED Requirements

### Requirement: 核心窗口必须具备首批真实动作执行映射
系统 MUST 为 `combat`、`reward`、`map` 三类核心窗口提供首批真实执行映射，至少覆盖 `play_card`、`end_turn`、`choose_reward`、`skip_reward`、`choose_map_node`、`choose_combat_card`，并在规则允许时支持 `cancel_combat_selection`。bridge MUST 只执行当前 legal actions 中存在的动作，不得猜测未枚举动作。对于 `reward` phase，bridge MUST 同时覆盖奖励列表（例如 `NRewardsScreen`）与奖励链路中的“卡牌奖励选择界面”（选牌二级界面）的动作执行映射。对于 `combat` phase 中的额外选牌窗口，bridge MUST 将“选择一张牌继续结算”建模为独立动作执行流程，而不是继续复用 `play_card`。

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

## ADDED Requirements

### Requirement: 回合切换与选择窗口漂移必须返回明确拒绝语义
当外部 agent 在回合切换边界或额外选牌窗口切换边界提交动作时，bridge MUST 返回结构化、可恢复的拒绝语义，以便 runner 刷新快照后重试，而不是退化为无上下文的泛化 `rejected`。对于“当前已不再是玩家回合”“当前窗口已不再是该选牌窗口”这两类情况，返回结果 MUST 能被调用方稳定区分。

#### Scenario: 玩家回合已结束时拒绝普通 combat 动作
- **WHEN** 外部 agent 提交一个来自旧 `player_turn` 窗口的 `play_card` 或 `end_turn`，但 runtime 已进入敌方回合或过渡态
- **THEN** bridge MUST 拒绝执行该动作
- **THEN** 返回结果 MUST 标记为 `stale_action`、`not_player_turn` 或等效可恢复错误原因

#### Scenario: 额外选牌窗口已关闭时拒绝 choose_combat_card
- **WHEN** 外部 agent 提交一个旧的 `choose_combat_card`，但当前效果已经结算完毕或当前窗口已经变为其他窗口
- **THEN** bridge MUST 拒绝执行该动作
- **THEN** 返回结果 MUST 标记为 `selection_window_changed`、`stale_action` 或等效错误原因
