# autoplay-orchestrator Specification

## Purpose
TBD - created by archiving change sts2-agent. Update Purpose after archive.
## Requirements
### Requirement: Orchestrator 逐步执行策略驱动的自动打牌
系统 MUST 运行一个 autoplay 循环：读取 bridge 提供的最新快照和合法动作，调用已配置 policy，提交一个被选择的动作，并持续重复直到会话结束或满足人工停止条件。在 live runtime 中，orchestrator MUST 在提交前执行稳定窗口校验，避免在已知高风险窗口下盲目调用 `/apply`。

#### Scenario: policy 驱动一回合实时战斗
- **WHEN** autoplay 已为一个可控会话启动，且 bridge 报告当前存在合法决策窗口
- **THEN** orchestrator 只为该窗口选择并提交一个合法动作，然后继续处理下一个决策窗口

#### Scenario: 提交前发现窗口不稳定
- **WHEN** orchestrator 在 live runtime 中发现当前 `phase`、`window_kind`、`current_side` 或等效 metadata 表明窗口尚不稳定
- **THEN** orchestrator MUST 先等待、重观测或进入恢复路径
- **THEN** orchestrator MUST NOT 直接对该窗口盲目提交 `/apply`

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


### Requirement: Orchestrator 支持可插拔 policy 实现
系统 MUST 提供统一的 policy 接口，该接口接收当前 observation 与合法动作集合，并返回一个被选择的合法动作，或者返回显式 halt 结果。

#### Scenario: 不同 policy 复用同一套 bridge 契约
- **WHEN** 启发式 policy 与 LLM policy 都被配置到 orchestrator 中
- **THEN** 两者都可以消费同一份标准化 bridge 输入，并在无需 bridge 特定分支代码的前提下返回动作结果

### Requirement: Orchestrator 为每次尝试决策持久化 trace
系统 MUST 为每次 autoplay 决策尝试持久化一条 trace 记录，其中包含时间戳、决策标识、标准化 observation 元数据、合法动作集合、选中动作或 halt 结果，以及 bridge 返回值。

#### Scenario: 成功提交动作后写入 trace
- **WHEN** orchestrator 提交一个合法动作并被 bridge 接受
- **THEN** 系统写入一条可用于回放、调试或评估的 trace 记录

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

#### Scenario: stale_action 触发同窗口恢复
- **WHEN** bridge 返回 `stale_action`，但当前 battle 仍处于可继续的 `combat`，且最新 observation 仍属于同一稳定窗口
- **THEN** orchestrator MUST 重新抓取最新 `snapshot/actions`
- **THEN** orchestrator MAY 对具备强锚点的动作执行受限 rebase，或重新决策后继续尝试

#### Scenario: `end_turn` 不得跨回合 rebase
- **WHEN** 某次旧决策选择了 `end_turn`，但提交前发现 `round_number`、`window_kind`、`current_side`、`selection_kind` 或 legal actions 已切到新的稳定玩家窗口
- **THEN** orchestrator MUST 将该旧 `end_turn` 视为失效动作
- **THEN** orchestrator MUST 重新决策，而不是把它 rebase 到新窗口
