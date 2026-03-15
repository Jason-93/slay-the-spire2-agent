## MODIFIED Requirements

### Requirement: runner 必须支持 battle 级停止条件、dry-run 与失败回退
runner MUST 支持 dry-run 模式、`max_steps` 限制、人工停止和模型失败中断。dry-run 模式下，runner MUST 完整执行读取与模型决策流程，但 MUST NOT 真的向 bridge 发送 `/apply`。在整场战斗 autoplay 场景下，runner MUST 额外支持 battle 级停止条件，例如战斗结束、最大回合数、最大总动作数、下一玩家回合等待超时、模型 halt、bridge 拒绝或连续失败超过预算。对于 live reject，runner MUST 区分可恢复与不可恢复失败，并优先走可恢复回退路径。

#### Scenario: dry-run 模式只记录不执行
- **WHEN** 调用方以 dry-run 模式启动 runner
- **THEN** runner MUST 获取 snapshot、actions 并调用模型
- **THEN** runner MUST 只记录计划动作，而不向 bridge 提交真实写请求

#### Scenario: 达到最大步数后停止
- **WHEN** 自动打牌步数达到 `max_steps`
- **THEN** runner MUST 停止继续请求模型
- **THEN** 结果 MUST 标记为因 `max_steps_exceeded` 或等效原因中断

#### Scenario: 可恢复 reject 触发 runner 级回退
- **WHEN** live `/apply` 结果被分类为 `recoverable_stale` 或 `recoverable_timing`
- **THEN** runner MUST 优先执行等待、重观测或重新决策，而不是立即将 battle 标记为失败
- **THEN** 若恢复成功，summary MUST 能区分“发生过 reject 但已恢复”

#### Scenario: 不可恢复 reject 直接终止
- **WHEN** live `/apply` 结果被分类为 `invalid_policy_decision` 或 `hard_runtime_reject`
- **THEN** runner MUST 停止继续提交后续动作
- **THEN** stop reason MUST 明确反映 reject 分类，而不是只输出模糊失败文本

### Requirement: runner 必须为整场战斗执行落盘可复盘 trace 与 battle 摘要
runner MUST 为每一步保存结构化 trace，至少包含当前 snapshot、legal actions、模型输出、bridge 回执与时间戳。若模型请求已发出，trace SHOULD 包含请求摘要、原始响应文本或等效诊断字段，便于回放与排障。对于整场战斗 autoplay，运行结果 MUST 能总结已完成回合数、总动作数、是否真正打完战斗以及最终停止原因；若 battle 过程中发生 reject 或恢复，summary MUST 额外记录 reject 计数、恢复计数与分类汇总。

#### Scenario: 正常执行跨多个玩家回合
- **WHEN** runner 在同一场战斗中完成多轮“玩家回合决策 -> 敌方回合等待 -> 下一玩家回合继续决策”
- **THEN** trace MUST 记录每一步的 observation、legal actions、policy_output 与 bridge_result
- **THEN** trace MUST 能区分这些记录属于哪一个玩家回合以及同一次 battle autoplay

#### Scenario: battle 完成后输出带 reject 统计的摘要
- **WHEN** runner 因战斗结束而停止
- **THEN** `RunSummary` 或等效结果 MUST 记录 `turns_completed`、`total_actions`、`battle_completed`
- **THEN** 若 battle 过程中出现 reject 或恢复，summary MUST 同时记录 reject 次数、恢复成功次数与最终 stop reason
