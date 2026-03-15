## ADDED Requirements

### Requirement: Orchestrator 必须维护 battle 级短期上下文并向策略层暴露恢复态
系统 MUST 在整场战斗 autoplay 过程中维护 battle-scoped context，至少包含最近动作摘要、最近 bridge 回执、当前回合索引、总动作数、连续恢复次数，以及当前是否处于等待、transition、额外选牌或 recovery 状态。该上下文 MUST 能进入策略输入摘要，而不是每一步都只暴露孤立的当前快照。

#### Scenario: 刚结束回合后进入等待态
- **WHEN** orchestrator 成功提交 `end_turn`，且战斗仍处于 `combat`
- **THEN** battle context MUST 记录最近一次成功动作是 `end_turn`
- **THEN** 后续进入下一次模型决策前，策略输入 MUST 能看见当前处于等待下一玩家回合的状态

#### Scenario: 刚经历可恢复拒绝后再次请求模型
- **WHEN** 上一步动作因 `stale_action` 或等效可恢复原因被 bridge 拒绝
- **THEN** battle context MUST 记录最近失败原因与恢复次数
- **THEN** 下一次策略调用 MUST 能消费该恢复摘要，而不是完全丢失失败上下文

### Requirement: Orchestrator 必须对可恢复竞争态执行有界恢复
当 battle autoplay 遇到 `stale_action`、短暂空 legal actions、刚从等待态切回玩家态、额外选牌窗口切换，或等效可恢复竞争态时，orchestrator MUST 执行“重观测 -> 约束化重试”的恢复流程。若恢复连续超过配置预算，系统 MUST 中断 battle autoplay 并记录明确停止原因。

#### Scenario: stale_action 触发 battle 级恢复
- **WHEN** bridge 返回 `stale_action`，但当前 battle 仍处于可继续的 `combat`
- **THEN** orchestrator MUST 重新抓取最新 `snapshot/actions`
- **THEN** orchestrator MUST 在恢复预算内继续尝试，而不是立即终止整场 battle

#### Scenario: 恢复预算耗尽后中断
- **WHEN** 同一场 battle 中可恢复竞争态连续超过允许预算
- **THEN** orchestrator MUST 停止继续请求模型或提交动作
- **THEN** 结果 MUST 记录 `recovery_budget_exhausted` 或等效 stop reason
