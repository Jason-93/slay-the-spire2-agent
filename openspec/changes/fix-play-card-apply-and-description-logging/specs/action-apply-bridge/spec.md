## ADDED Requirements

### Requirement: play_card 的 accepted 语义必须对应真实状态推进
当 bridge 处理 `type="play_card"` 的动作请求时，MUST 以真实游戏逻辑执行与可观察的 live 状态推进作为 accepted 的成立条件，而不是仅以 UI 拖拽入口或中间对象创建成功作为依据。bridge MUST 优先使用可直接进入游戏逻辑的运行时出牌入口；只有在该入口不可用时，才可退回兼容性 fallback。若动作请求已被消费但在可接受的执行窗口内没有触发新的决策上下文、资源变化、目标窗口变化或等效 live 推进信号，bridge MUST 返回 `failed`、`rejected` 或等效可诊断结论，而不是继续回报 accepted。

#### Scenario: 直接运行时出牌入口成功触发状态推进
- **WHEN** 当前 `combat` 窗口存在某个合法 `play_card`，且 bridge 能解析到该卡牌实例的直接运行时出牌入口
- **THEN** bridge MUST 优先使用该直接入口执行出牌
- **THEN** 只有当 `decision_id`、`state_version`、手牌实例集合、能量、敌我状态或后续选择窗口至少一项发生推进时，返回结果才可以标记为 accepted

#### Scenario: UI 拖拽入口未导致实际出牌时不得回报 accepted
- **WHEN** bridge 通过兼容性 UI 路径启动了某个 `play_card`，但 live snapshot 在执行窗口后仍与执行前等效一致
- **THEN** bridge MUST NOT 将该请求标记为 accepted
- **THEN** 返回结果 MUST 标记为 `failed`、`runtime_not_applied` 或等效可诊断错误原因

#### Scenario: 动作已消费但未生效时返回阶段化诊断
- **WHEN** 某个 `play_card` 请求已经通过校验、入队并进入执行阶段，但最终没有触发任何可观察的 live 推进
- **THEN** 返回结果 MUST 能区分“未被消费”和“已消费但未实际生效”
- **THEN** 返回 metadata MUST 包含 `queue_stage`、`runtime_handler`、`state_progress_detected` 或等效诊断字段
