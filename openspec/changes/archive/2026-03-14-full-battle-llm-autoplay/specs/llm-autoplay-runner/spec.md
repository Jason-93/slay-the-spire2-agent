## MODIFIED Requirements

### Requirement: runner 必须用当前 legal actions 驱动模型连续决策
系统 MUST 提供一个 `llm-autoplay-runner`，在每一步从 bridge 读取当前 `snapshot` 与 `legal actions`，再调用 LLM policy 生成动作决策。runner MUST 只允许模型从当前 legal set 中选择动作，并在提交前完成本地校验。在 `combat` 中，runner MUST 能跨多个玩家回合连续执行，而不是在单个玩家回合结束后默认退出。

#### Scenario: 模型选择当前合法动作
- **WHEN** runner 拿到当前 decision 的 `legal actions`
- **THEN** runner MUST 将这些动作传给 LLM policy
- **THEN** 若模型返回的 `action_id` 属于当前 legal set，runner MUST 才能提交到 bridge

#### Scenario: 模型返回不存在的 action_id
- **WHEN** 模型返回的 `action_id` 不属于当前 legal set
- **THEN** runner MUST 将该结果视为无效模型输出
- **THEN** runner MUST NOT 直接调用 `/apply`

#### Scenario: 同一战斗内跨回合连续执行
- **WHEN** 当前 encounter 仍处于 `combat`，且前一个玩家回合已结束
- **THEN** runner MUST 在下一次重新进入玩家回合时继续读取最新 `snapshot` 与 `legal actions`
- **THEN** runner MUST 基于最新 live state 恢复模型决策，而不是要求调用方重新启动 runner

### Requirement: runner 必须支持 battle 级停止条件、dry-run 与失败回退
runner MUST 支持 dry-run 模式、`max_steps` 限制、人工停止和模型失败中断。dry-run 模式下，runner MUST 完整执行读取与模型决策流程，但 MUST NOT 真的向 bridge 发送 `/apply`。在整场战斗 autoplay 场景下，runner MUST 额外支持 battle 级停止条件，例如战斗结束、最大回合数、最大总动作数、下一玩家回合等待超时、模型 halt、bridge 拒绝或连续失败超过预算。

#### Scenario: dry-run 模式只记录不执行
- **WHEN** 调用方以 dry-run 模式启动 runner
- **THEN** runner MUST 获取 snapshot、actions 并调用模型
- **THEN** runner MUST 只记录计划动作，而不向 bridge 提交真实写请求

#### Scenario: 达到最大步数后停止
- **WHEN** 自动打牌步数达到 `max_steps`
- **THEN** runner MUST 停止继续请求模型
- **THEN** 结果 MUST 标记为因 `max_steps_exceeded` 或等效原因中断

#### Scenario: 只剩 end_turn 时结束当前玩家回合但继续 battle
- **WHEN** 当前玩家回合 legal actions 只剩 `end_turn`，且 battle autoplay 仍在继续
- **THEN** runner MUST 能按配置自动结束当前回合
- **THEN** runner MUST 在后续重新进入玩家回合时继续运行，直到战斗结束或命中 battle 级停止条件

#### Scenario: 战斗结束后正常退出
- **WHEN** runner 观察到 `snapshot.phase != "combat"` 或 `snapshot.terminal = true`
- **THEN** runner MUST 将本次运行标记为 battle 已完成
- **THEN** runner MUST 以“正常完成战斗”而不是“异常中断”退出

#### Scenario: 下一玩家回合等待超时
- **WHEN** runner 已成功结束当前玩家回合，但在配置的等待时间内始终没有重新进入下一个玩家回合，也没有离开 `combat`
- **THEN** runner MUST 停止继续运行
- **THEN** 结果 MUST 记录 `next_player_turn_timeout` 或等效原因

#### Scenario: 模型连续失败后中断
- **WHEN** 模型请求失败、解析失败、bridge 拒绝或可恢复竞争态超过允许的连续失败预算
- **THEN** runner MUST 中断当前 autoplay
- **THEN** 结果 MUST 明确记录失败原因，而不是继续盲打

### Requirement: runner 必须为整场战斗执行落盘可复盘 trace 与 battle 摘要
runner MUST 为每一步保存结构化 trace，至少包含当前 snapshot、legal actions、模型输出、bridge 回执与时间戳。若模型请求已发出，trace SHOULD 包含请求摘要、原始响应文本或等效诊断字段，便于回放与排障。对于整场战斗 autoplay，运行结果 MUST 能总结已完成回合数、总动作数、是否真正打完战斗以及最终停止原因。

#### Scenario: 正常执行跨多个玩家回合
- **WHEN** runner 在同一场战斗中完成多轮“玩家回合决策 -> 敌方回合等待 -> 下一玩家回合继续决策”
- **THEN** trace MUST 记录每一步的 observation、legal actions、policy_output 与 bridge_result
- **THEN** trace MUST 能区分这些记录属于哪一个玩家回合以及同一次 battle autoplay

#### Scenario: battle 完成后输出摘要
- **WHEN** runner 因战斗结束而停止
- **THEN** `RunSummary` 或等效结果 MUST 记录 `turns_completed`、`total_actions`、`battle_completed`
- **THEN** 调用方 MUST 能区分“战斗完成”与“中途被安全边界打断”

#### Scenario: 等待敌方回合也有可诊断记录
- **WHEN** runner 在敌方回合或动画窗口中等待下一次玩家决策机会
- **THEN** trace MUST 能标记当前步骤处于等待态或非玩家回合观察态
- **THEN** 后续分析 MUST 能区分“模型没有动作”与“runner 正在等待下一玩家回合”

### Requirement: runner 必须提供面向整场战斗执行的调试入口
系统 MUST 提供一个本地可执行的调试入口，用于连接 OpenAI 兼容接口和 live bridge 完成端到端联调。该入口 MUST 支持通过参数或环境变量设置 `base_url`、`model`、`api_key`、`bridge_base_url`、`dry_run` 与 `trace_dir`。对于整场战斗 autoplay，该入口 MUST 支持配置 battle 级安全边界，如最大回合数、最大总动作数与等待超时。

#### Scenario: 使用本地 chat completions 接口启动整场战斗 autoplay
- **WHEN** 调用方把 `base_url` 设为 `http://127.0.0.1:8080/v1`，并启用 battle autoplay 模式
- **THEN** 调试入口 MUST 能连接 live bridge 并跨多个玩家回合持续运行
- **THEN** 调试入口 MUST 在战斗结束或命中 battle 级停止条件后退出

#### Scenario: CLI 参数覆盖 battle 级默认配置
- **WHEN** 调用方在命令行显式传入 battle 级参数，如最大回合数、最大总动作数或下一玩家回合等待超时
- **THEN** 调试入口 MUST 使用这些参数覆盖默认值
- **THEN** 实际运行配置 MUST 可在 trace、摘要或启动输出中被确认
