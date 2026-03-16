## MODIFIED Requirements

### Requirement: Orchestrator 逐步执行策略驱动的自动打牌
系统 MUST 运行一个 autoplay 循环：读取 bridge 提供的最新快照和合法动作，调用已配置 policy，提交一个被选择的动作，并持续重复直到会话结束或满足人工停止条件。在 live runtime 中，orchestrator MUST 先确认当前 observation 已进入稳定决策窗口，才允许调用 policy；若窗口尚未稳定或提交前检测到窗口已漂移，orchestrator MUST 优先等待、重观测或重新决策，而不是继续沿用旧动作直接调用 `/apply`。

#### Scenario: policy 只在稳定窗口内被调用
- **WHEN** autoplay 已为一个可控会话启动，且 bridge 报告当前存在合法决策窗口
- **THEN** orchestrator MUST 先验证 `phase`、`window_kind`、`current_side`、`round_number`、`selection_kind` 与 legal actions 已达到稳定条件
- **THEN** 只有稳定后，orchestrator 才能为该窗口调用 policy 并选择一个合法动作

#### Scenario: 决策前发现窗口仍在漂移
- **WHEN** orchestrator 在 live runtime 中发现 `phase`、`window_kind`、`current_side`、`round_number`、`selection_kind` 或 legal actions 仍处于变化中
- **THEN** orchestrator MUST 继续等待、重观测或进入恢复路径
- **THEN** orchestrator MUST NOT 在该时刻调用 policy 生成动作

#### Scenario: 提交前发现旧决策已不属于当前稳定窗口
- **WHEN** orchestrator 在模型已返回动作后再次观测到当前稳定窗口已变化
- **THEN** orchestrator MUST 作废旧决策并重新进入稳定窗口判定 / 重新决策流程
- **THEN** orchestrator MUST NOT 直接把旧动作提交到新的 live 窗口

### Requirement: Orchestrator 必须对可恢复竞争态执行有界恢复
当 battle autoplay 遇到 `stale_action`、短暂空 legal actions、刚从等待态切回玩家态、额外选牌窗口切换，或等效可恢复竞争态时，orchestrator MUST 执行“重观测 -> 约束化重试”的恢复流程。对于 live 提交前的动作漂移，rebase MUST 仅作为同稳定窗口内的窄兜底：`play_card`、`choose_combat_card` 等具备强实例锚点的动作 MAY 在同一稳定窗口内受限 rebase；`end_turn`、`use_potion` 等低信息动作 MUST NOT 跨稳定窗口、跨回合或跨子窗口 rebase。若恢复连续超过配置预算，系统 MUST 中断 battle autoplay 并记录明确停止原因。

#### Scenario: stale_action 触发同窗口恢复
- **WHEN** bridge 返回 `stale_action`，但当前 battle 仍处于可继续的 `combat`，且最新 observation 仍属于同一稳定窗口
- **THEN** orchestrator MUST 重新抓取最新 `snapshot/actions`
- **THEN** orchestrator MAY 对具备强锚点的动作执行受限 rebase，或重新决策后继续尝试

#### Scenario: `end_turn` 不得跨回合 rebase
- **WHEN** 某次旧决策选择了 `end_turn`，但提交前发现 `round_number`、`window_kind`、`current_side`、`selection_kind` 或 legal actions 已切到新的稳定玩家窗口
- **THEN** orchestrator MUST 将该旧 `end_turn` 视为失效动作
- **THEN** orchestrator MUST 重新决策，而不是把它 rebase 到新窗口

#### Scenario: 恢复预算耗尽后中断
- **WHEN** 同一场 battle 中可恢复竞争态连续超过允许预算
- **THEN** orchestrator MUST 停止继续请求模型或提交动作
- **THEN** 结果 MUST 记录 `recovery_budget_exhausted`、`stable_window_timeout` 或等效 stop reason
