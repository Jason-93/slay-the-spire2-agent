## MODIFIED Requirements

### Requirement: 核心窗口必须具备首批真实动作执行映射
系统 MUST 为 `combat`、`reward`、`map` 三类核心窗口提供首批真实执行映射，至少覆盖 `play_card`、`end_turn`、`choose_reward`、`skip_reward`、`choose_map_node`、`continue_game`。bridge MUST 只执行当前 legal actions 中存在的动作，不得猜测未枚举动作。对于 `reward` phase，bridge MUST 同时覆盖奖励列表（例如 `NRewardsScreen`）与奖励链路中的“卡牌奖励选择界面”（选牌二级界面）的动作执行映射。对于流程推进类按钮（Proceed/Continue/OK），bridge MUST 通过 `continue_game` 显式建模并执行，不得复用 `skip_reward` 等语义不一致的动作类型。

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

#### Scenario: 存在继续按钮时执行 continue_game
- **WHEN** 当前窗口存在明确的 Proceed/Continue/OK 等流程推进按钮，且 legal actions 中存在 `continue_game`
- **THEN** bridge MUST 将该动作映射到游戏内真实按钮点击/激活流程
- **THEN** 若按钮不可点击、窗口已变化或目标控件不可解析，bridge MUST 拒绝执行并返回 `stale_action`、`runtime_incompatible` 或等效错误原因

