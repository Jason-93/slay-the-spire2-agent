## ADDED Requirements

### Requirement: runner 必须持续处理 reward 到 map 的跨 phase 自动化
系统 MUST 在 battle autoplay 中把 `reward`、`map` 与房间过渡视为可继续推进的合法阶段，而不是一旦 `phase != combat` 就立即停止。runner MUST 基于最新 `snapshot` 与 `legal actions`，持续推进直到重新进入 `combat`、命中安全停止条件或遇到无法识别的窗口。

#### Scenario: reward 阶段继续推进
- **WHEN** runner 在 battle autoplay 中观察到 `snapshot.phase = reward`，且存在 `choose_reward` 或 `skip_reward`
- **THEN** runner MUST 继续读取最新 `snapshot` 与 `actions`
- **THEN** 在奖励链路完成并进入 `map` 前，runner MUST 不得仅因 phase 变化而提前停止

#### Scenario: reward_choice 与 card_reward_selection 都属于可处理奖励窗口
- **WHEN** bridge 导出 `reward_choice` 或 `card_reward_selection`
- **THEN** runner MUST 将其视为当前 autoplay 链路中的合法窗口
- **THEN** runner MUST 根据配置选择 `choose_reward`、`skip_reward` 或等效 reward 动作继续推进

#### Scenario: map 阶段继续推进到下一房间
- **WHEN** runner 进入 `map` phase 且存在可执行的 `choose_map_node`
- **THEN** runner MUST 继续自动执行地图选路
- **THEN** 在 bridge 重新导出 `combat` 前，runner MUST 继续保持 autoplay 而不是把 map 当作终点

#### Scenario: 房间过渡后恢复到下一场 combat
- **WHEN** reward/map 动作提交后，runner 观察到房间过渡窗口并最终重新进入 `combat`
- **THEN** runner MUST 恢复到战斗 autoplay
- **THEN** 运行结果 MUST 能明确区分这是 `reward/map/next-room` 成功推进后的恢复

### Requirement: runner 必须为 reward、map 与过渡阶段提供安全策略和停止条件
系统 MUST 为 `reward`、`map` 与等待过渡的阶段提供可配置的安全策略与预算。reward 选择、地图选路和等待房间切换既可以由 LLM 驱动，也可以由本地保守策略接管；runner MUST 始终只从当前 legal actions 中选动作，并在异常空窗或长时间不推进时安全停止。

#### Scenario: 使用保守默认策略推进
- **WHEN** 调用方为 reward 或 map 选择 `safe-default` 等保守策略
- **THEN** runner MUST 能在不依赖 LLM 的情况下继续推进
- **THEN** 本地策略来源 MUST 在 trace 或 summary 中可诊断

#### Scenario: 当前窗口没有 legal actions 时按过渡逻辑处理
- **WHEN** reward 或 map 阶段暂时没有 `/actions`，但 `snapshot` 与 metadata 仍表明处于正常过渡
- **THEN** runner MUST 进入有限等待，而不是立刻判定失败
- **THEN** 若状态长时间不推进，runner MUST 以明确原因停止

#### Scenario: 过渡超时会被结构化记录
- **WHEN** runner 在等待房间切换时超过 `transition_timeout` 或等效预算
- **THEN** runner MUST 中断当前 autoplay
- **THEN** 结果 MUST 记录超时原因，并带上当时的 snapshot/metadata 诊断

### Requirement: runner 必须为 reward -> map -> next combat 链路记录完整 trace
系统 MUST 为 `reward -> map -> next combat` 的跨窗口自动化链路记录完整 trace，明确每一步属于 reward、map、过渡等待还是恢复到新战斗。trace MUST 支持在 live 调试时快速定位卡在奖励、卡在地图还是已经成功进入下一战。

#### Scenario: trace 标记跨 phase 步骤类型
- **WHEN** runner 执行 battle autoplay 并跨越 reward、map 与过渡窗口
- **THEN** trace MUST 记录每一步的 `phase`、legal actions、policy 输出与 bridge 回执
- **THEN** trace MUST 能区分 `reward`、`map`、`transition_wait` 与 `combat_resume`

#### Scenario: 运行摘要记录已进入下一场战斗
- **WHEN** runner 从 reward 或 map 链路重新进入 `combat`
- **THEN** 运行摘要 MUST 标记 `next_combat_entered=true` 或等效结果
- **THEN** 摘要 MUST 能反映本次运行跨越了 reward/map 后成功恢复战斗
