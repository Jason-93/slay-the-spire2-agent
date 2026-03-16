## MODIFIED Requirements

### Requirement: runner 必须用当前 legal actions 与 richer snapshot 驱动模型连续决策
系统 MUST 提供一个 `llm-autoplay-runner`，在每一步从 bridge 读取当前 `snapshot` 与 `legal actions`，再调用 LLM policy 生成动作决策。runner MUST 只允许模型从当前 legal set 中选择动作，并在提交前完成本地校验。在整场 run-flow 中，runner MUST 能跨 `combat`、`reward`、`map`、`event` 等可决策窗口连续执行，而不是一进入 event 就默认退出或误判为未知窗口。当 bridge 已提供 richer runtime state 时，runner MUST 将对决策有价值的 richer fields 一并提供给策略层；当这些字段部分缺失时，runner MUST 退化到基础 snapshot，而不是直接中断运行。

#### Scenario: 模型选择当前合法动作
- **WHEN** runner 拿到当前 decision 的 `legal actions`
- **THEN** runner MUST 将这些动作传给 LLM policy
- **THEN** 若模型返回的 `action_id` 属于当前 legal set，runner MUST 才能提交到 bridge

#### Scenario: 模型返回不存在的 action_id
- **WHEN** 模型返回的 `action_id` 不属于当前 legal set
- **THEN** runner MUST 将该结果视为无效模型输出
- **THEN** runner MUST NOT 直接调用 `/apply`

#### Scenario: richer snapshot 可用时进入策略输入
- **WHEN** bridge 在 combat snapshot 中导出了卡牌描述、结构化 intent、powers 或等效 richer fields
- **THEN** runner MUST 将这些高价值字段纳入策略输入摘要
- **THEN** 策略层 MUST 不再只能依赖卡名与模糊 intent 做判断

#### Scenario: event snapshot 可用时进入策略输入
- **WHEN** bridge 导出了 `phase=event`，并在 snapshot / metadata 中提供事件标题、正文、选项或继续按钮语义
- **THEN** runner MUST 将这些 event 字段纳入策略输入摘要
- **THEN** 策略层 MUST 能基于当前事件文本与 legal actions 做分支选择，而不是直接 halt

#### Scenario: richer 字段缺失时保持兼容运行
- **WHEN** 某次 snapshot 只包含基础字段，而 richer fields 缺失或为空
- **THEN** runner MUST 仍能继续执行当前 autoplay
- **THEN** 运行结果 MUST 体现为“降级运行”，而不是协议错误或强制中断

### Requirement: runner 必须支持 battle 级停止条件、dry-run 与失败回退
runner MUST 支持 dry-run 模式、`max_steps` 限制、人工停止和模型失败中断。dry-run 模式下，runner MUST 完整执行读取与模型决策流程，但 MUST NOT 真的向 bridge 发送 `/apply`。在整场战斗 autoplay 场景下，runner MUST 额外支持 battle 级停止条件，例如战斗结束、最大回合数、最大总动作数、下一玩家回合等待超时、模型 halt、bridge 拒绝或连续失败超过预算。对于 live reject，runner MUST 区分可恢复与不可恢复失败，并优先走可恢复回退路径。对于 run 内非战斗窗口，runner MUST 在 `reward`、`map`、`event` 等窗口继续尝试推进，除非策略显式 halt 或命中配置的停止边界。

#### Scenario: dry-run 模式只记录不执行
- **WHEN** 调用方以 dry-run 模式启动 runner
- **THEN** runner MUST 获取 snapshot、actions 并调用模型
- **THEN** runner MUST 只记录计划动作，而不向 bridge 提交真实写请求

#### Scenario: 达到最大步数后停止
- **WHEN** 自动打牌步数达到 `max_steps`
- **THEN** runner MUST 停止继续请求模型
- **THEN** 结果 MUST 标记为因 `max_steps_exceeded` 或等效原因中断

#### Scenario: event 窗口不会被默认视为未知窗口
- **WHEN** 当前 snapshot.phase 为 `event`，且 legal actions 中存在 `choose_event_option` 或 `continue_event`
- **THEN** runner MUST 将该窗口视为可决策窗口继续执行
- **THEN** runner MUST NOT 直接因为 phase 不在旧名单中而中断运行

#### Scenario: 可恢复 reject 触发 runner 级回退
- **WHEN** live `/apply` 结果被分类为 `recoverable_stale` 或 `recoverable_timing`
- **THEN** runner MUST 优先执行等待、重观测或重新决策，而不是立即将 battle 标记为失败
- **THEN** 若恢复成功，summary MUST 能区分“发生过 reject 但已恢复”

#### Scenario: 不可恢复 reject 直接终止
- **WHEN** live `/apply` 结果被分类为 `invalid_policy_decision` 或 `hard_runtime_reject`
- **THEN** runner MUST 停止继续提交后续动作
- **THEN** stop reason MUST 明确反映 reject 分类，而不是只输出模糊失败文本
