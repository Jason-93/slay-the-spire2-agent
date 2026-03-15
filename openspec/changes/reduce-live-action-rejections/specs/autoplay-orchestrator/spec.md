## MODIFIED Requirements

### Requirement: Orchestrator 逐步执行策略驱动的自动打牌
系统 MUST 运行一个 autoplay 循环：读取 bridge 提供的最新快照和合法动作，调用已配置 policy，提交一个被选择的动作，并持续重复直到会话结束或满足人工停止条件。在 live runtime 中，orchestrator MUST 在提交前执行稳定窗口校验，避免在已知高风险窗口下盲目调用 `/apply`。

#### Scenario: policy 驱动一回合实时战斗
- **WHEN** autoplay 已为一个可控会话启动，且 bridge 报告当前存在合法决策窗口
- **THEN** orchestrator 只为该窗口选择并提交一个合法动作，然后继续处理下一个决策窗口

#### Scenario: 提交前发现窗口不稳定
- **WHEN** orchestrator 在 live runtime 中发现当前 `phase`、`window_kind`、`current_side` 或等效 metadata 表明窗口尚不稳定
- **THEN** orchestrator MUST 先等待、重观测或进入恢复路径
- **THEN** orchestrator MUST NOT 直接对该窗口盲目提交 `/apply`

### Requirement: Orchestrator 在 bridge 或 policy 失败时安全停止
系统 MUST 在 bridge 拒绝动作、决策窗口失步、或 policy 在配置限制内未返回有效结果时安全处理失败。对于可恢复的 runtime reject 或时序竞争态，orchestrator MUST 优先执行有界恢复；对于不可恢复错误或恢复预算耗尽，orchestrator MUST 停止 autoplay，并将会话标记为 interrupted。

#### Scenario: autoplay 过程中 bridge 拒绝了过期动作
- **WHEN** bridge 因提交动作已不再匹配当前活动决策窗口而返回拒绝结果
- **THEN** orchestrator MUST 先将该错误分类为可恢复或不可恢复
- **THEN** 若属于可恢复类别，orchestrator MUST 尝试重观测与有限重试，而不是立即终止整场运行

#### Scenario: 可恢复拒绝超过预算后停止
- **WHEN** 同一场 autoplay 中可恢复 reject 或等效恢复链路连续超过允许预算
- **THEN** orchestrator MUST 停止继续发出后续动作
- **THEN** trace 与 summary MUST 记录恢复预算耗尽或等效中断原因
