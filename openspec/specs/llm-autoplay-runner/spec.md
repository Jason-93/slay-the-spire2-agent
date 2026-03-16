# llm-autoplay-runner Specification

## Purpose
定义基于本地 HTTP bridge 和 OpenAI 兼容模型接口的自动打牌执行闭环，确保 STS2 live runtime 可以安全地完成“读状态、调模型、提动作、记录 trace”的端到端自动决策流程。
## Requirements
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

#### Scenario: 模型只在稳定窗口上收到决策输入
- **WHEN** runner 拿到某次 live `combat` observation 与 `legal actions`
- **THEN** runner MUST 先确认该 observation 已满足稳定窗口条件
- **THEN** 只有稳定后，runner MUST 才能把当前 legal actions 与 snapshot 传给 LLM policy

#### Scenario: 模型返回后窗口漂移触发重决策
- **WHEN** 模型已返回某个 `action_id`，但提交前 runner 发现 `phase`、`window_kind`、`current_side`、`round_number`、`selection_kind` 或 legal actions 已变化
- **THEN** runner MUST 放弃该次旧模型输出并重新观测最新状态
- **THEN** runner MUST 在窗口重新稳定后再次请求模型，而不是直接调用 `/apply`


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

#### Scenario: gate 检测到窗口漂移后进入恢复
- **WHEN** runner 在提交前发现旧动作对应窗口已经失稳或变更
- **THEN** runner MUST 执行 reobserve -> restabilize -> redecide
- **THEN** 若恢复成功，runner MUST 继续 battle autoplay，而不是把这次漂移直接视作终止错误

#### Scenario: `end_turn` 与 `use_potion` 不跨窗口复用
- **WHEN** 某次模型输出为 `end_turn` 或 `use_potion`，且提交前 stable window 已变化
- **THEN** runner MUST 作废该模型输出并重新请求模型
- **THEN** runner MUST NOT 通过 rebase 把这类低信息动作提交到新窗口



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

#### Scenario: battle 完成后输出摘要
- **WHEN** runner 因战斗结束而停止
- **THEN** `RunSummary` 或等效结果 MUST 记录 `turns_completed`、`total_actions`、`battle_completed`
- **THEN** 调用方 MUST 能区分“战斗完成”与“中途被安全边界打断”

#### Scenario: 等待敌方回合也有可诊断记录
- **WHEN** runner 在敌方回合或动画窗口中等待下一次玩家决策机会
- **THEN** trace MUST 能标记当前步骤处于等待态或非玩家回合观察态
- **THEN** 后续分析 MUST 能区分“模型没有动作”与“runner 正在等待下一玩家回合”

#### Scenario: trace 记录稳定窗口门控结果
- **WHEN** runner 在 live battle 中进行一次决策尝试
- **THEN** 该步 trace MUST 记录 `gate_status`、`gate_reason`、是否发生 restabilize / redecide，以及最终是否提交动作
- **THEN** 调用方 MUST 能从 trace 判断该步是正常通过、同窗口 rebase 还是因窗口漂移重新决策

#### Scenario: summary 能定位提前结束回合问题
- **WHEN** 某次 battle 运行中出现错误 `end_turn`、频繁 gate miss 或多次重新决策
- **THEN** summary MUST 记录对应计数、最近一次关键上下文与最终 stop reason
- **THEN** artifacts MUST 足以区分“策略主动结束回合”和“时序漂移导致的错误结束回合”



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

### Requirement: runner 必须基于卡牌描述质量做策略输入降级
当 snapshot 中的卡牌 `description_rendered`、`description_vars` 或等效质量字段显示该描述仍处于模板回退时，runner MUST 采用安全降级策略组织模型输入，而不是把模板占位符文本直接当作高置信事实。若描述已经完成真实值解析，runner MUST 优先向策略层提供这些高质量字段。

#### Scenario: 已解析真实值的卡牌优先进入策略输入
- **WHEN** 当前 snapshot 中某张卡牌已提供不含模板占位符的 `description_rendered` 与可用的 `description_vars`
- **THEN** runner MUST 优先将这些字段纳入策略输入摘要
- **THEN** 策略层 MUST 不再只依赖卡名和 glossary 猜测效果

#### Scenario: 模板回退卡牌触发安全降级
- **WHEN** 当前 snapshot 中某张卡牌的 `description_rendered` 仍含模板占位符，或 `description_vars` 缺少真实值
- **THEN** runner MUST 将其视为低质量描述输入
- **THEN** runner MUST 优先回退到卡名、traits、glossary 与其他稳定事实，而不是把未解析模板原样提升为高置信描述

### Requirement: runner 必须向模型提供 battle 级摘要而不只提供当前快照
在整场战斗 autoplay 模式下，runner MUST 在当前 `snapshot` 与 `legal actions` 之外，向策略层补充 battle 级摘要，至少覆盖最近动作、最近 bridge 结果、当前回合索引、当前 battle 的累计动作数、等待态 / 过渡态 / 额外选牌态，以及最近一次可恢复失败信息。该摘要 MUST 保持简洁并可重复序列化到 trace。

#### Scenario: battle 中途再次进入玩家回合
- **WHEN** runner 在敌方回合等待后重新回到玩家回合并再次调用模型
- **THEN** 模型输入 MUST 能看到 battle 已进行到第几个玩家回合
- **THEN** 模型输入 MUST 能看到最近一次等待或恢复发生了什么

#### Scenario: 进入额外选牌窗口时保持上下文连续
- **WHEN** runner 在 battle 中因打牌效果进入 `choose_combat_card` 或等效额外选牌窗口
- **THEN** 模型输入 MUST 明确标识当前不是普通出牌选择，而是额外选牌子决策
- **THEN** battle 摘要 MUST 保留导致该窗口出现的上一手动作线索

### Requirement: runner 必须把 battle 级恢复结果写入 trace 与 summary
runner MUST 在 trace 与最终摘要中记录每次可恢复竞争态、恢复是否成功、恢复后重新执行的动作，以及 battle 最终是正常完成还是因恢复预算、等待超时、模型连续失败等原因中断。

#### Scenario: battle 正常完成且曾发生恢复
- **WHEN** runner 在同一场战斗中至少经历一次恢复，但最终仍成功离开 `combat`
- **THEN** trace MUST 能标出恢复发生的步骤与后续恢复成功的动作
- **THEN** summary MUST 能区分“battle_completed=true”与“期间发生过 recovery”

#### Scenario: battle 因恢复失败而停止
- **WHEN** runner 多次恢复后仍无法重新得到稳定决策窗口
- **THEN** summary MUST 记录 battle 未完成
- **THEN** stop reason MUST 明确反映是恢复链路失败，而不是普通 halt

### Requirement: runner 必须支持 reward 决策模式并安全执行 reward 动作
runner MUST 支持在 `snapshot.phase = reward` 时对奖励窗口做出决策，并通过 bridge 提交 `choose_reward` / `skip_reward` 等 reward 动作。runner MUST 提供显式的 reward 决策模式开关，默认 MUST 为安全模式（不自动领取奖励），避免在未配置策略时对跑局结果产生不可控影响。

#### Scenario: 默认 reward 模式为 halt
- **WHEN** 调用方未显式启用 reward 决策，且 runner 观测到 `snapshot.phase = reward`
- **THEN** runner MUST 停止继续自动决策并返回明确的停止原因（例如 `reward_phase_reached`）
- **THEN** runner MUST NOT 对 bridge 发起真实 `/apply`

#### Scenario: reward_mode=skip 时仅自动跳过奖励
- **WHEN** 调用方将 reward 决策模式设为 `skip` 且当前 legal actions 中包含 `skip_reward`
- **THEN** runner MUST 直接提交 `skip_reward` 并等待窗口推进
- **THEN** runner MUST 在 trace 中记录该决策与 bridge 回执

#### Scenario: reward_mode=llm 时允许模型选择 reward 动作
- **WHEN** 调用方将 reward 决策模式设为 `llm` 且当前 legal actions 中存在 `choose_reward` 或 `skip_reward`
- **THEN** runner MUST 将 reward legal actions 提供给 LLM policy 生成决策
- **THEN** 若模型返回的 `action_id` 属于当前 legal set，runner MUST 才能提交到 bridge；否则 MUST 视为无效输出并按失败回退语义处理

## MODIFIED Requirements

### Requirement: runner 必须支持回合级停止条件、dry-run 与失败回退
runner MUST 支持 dry-run 模式、`max_steps` 限制、人工停止和模型失败中断。dry-run 模式下，runner MUST 完整执行读取与模型决策流程，但 MUST NOT 真的向 bridge 发送 `/apply`。在多步 autoplay 场景下，runner MUST 额外支持回合级停止条件，例如玩家回合结束、phase 切换、只剩 `end_turn`、模型 halt、bridge 拒绝或单回合动作数达到上限。

当 runner 启用了 reward 决策模式（非 `halt`）时，`reward` phase MUST NOT 被简单视为“停止条件”；runner MUST 继续在 reward 窗口完成一次或多次 reward 动作提交，直到 phase 推进到后续窗口或命中其他停止条件。

#### Scenario: dry-run 模式只记录不执行
- **WHEN** 调用方以 dry-run 模式启动 runner
- **THEN** runner MUST 获取 snapshot、actions 并调用模型
- **THEN** runner MUST 只记录计划动作，而不向 bridge 提交真实写请求

#### Scenario: 达到最大步数后停止
- **WHEN** 自动打牌步数达到 `max_steps`
- **THEN** runner MUST 停止继续请求模型
- **THEN** 结果 MUST 标记为因 `max_steps_exceeded` 或等效原因中断

#### Scenario: 只剩 end_turn 时结束本回合
- **WHEN** 当前玩家回合的 legal actions 只剩 `end_turn`
- **THEN** runner MUST 能按配置自动结束当前回合，或明确以回合完成状态停止
- **THEN** 运行结果 MUST 能区分这是“正常结束本回合”而不是异常中断

#### Scenario: reward_mode 启用时进入 reward 不应直接停止
- **WHEN** runner 已启用 reward 决策模式（非 `halt`），且观测到 `snapshot.phase = reward`
- **THEN** runner MUST 进入 reward 决策与提交流程，而不是把 `phase_changed` 作为立即停止原因
- **THEN** 若 reward legal actions 为空或无法安全选择，runner MUST 以明确 reason 停止，而不是无休止等待

#### Scenario: 模型连续失败后中断
- **WHEN** 模型请求失败、解析失败或返回非法动作，且已达到允许的重试上限
- **THEN** runner MUST 中断当前 autoplay
- **THEN** 结果 MUST 明确记录失败原因，而不是继续盲打

### Requirement: runner 必须提供面向多步回合执行的调试入口
系统 MUST 提供一个本地可执行的调试入口，用于连接 OpenAI 兼容接口和 live bridge 完成端到端联调。该入口 MUST 支持通过参数或环境变量设置 `base_url`、`model`、`api_key`、`bridge_base_url`、`dry_run` 与 `trace_dir`。对于多步 autoplay，该入口 MUST 支持配置单回合动作上限或等效安全边界。该入口 MUST 支持配置 reward 决策模式（例如 `reward_mode=halt|skip|llm`），以便在真实游戏中验证 reward 行为。

#### Scenario: 使用本地 chat completions 接口启动完整玩家回合 autoplay
- **WHEN** 调用方把 `base_url` 设为 `http://127.0.0.1:8080/v1`，并启用多步回合模式
- **THEN** 调试入口 MUST 能连接 live bridge 并连续执行多步决策
- **THEN** 调试入口 MUST 在当前玩家回合结束或命中安全停止条件后退出

#### Scenario: CLI 参数覆盖回合级默认配置
- **WHEN** 调用方在命令行显式传入回合级参数，如单回合动作上限或是否自动 `end_turn`
- **THEN** 调试入口 MUST 使用这些参数覆盖默认值
- **THEN** 实际运行配置 MUST 可在 trace 或启动日志中被确认

#### Scenario: CLI 参数显式启用 reward 决策模式
- **WHEN** 调用方在命令行显式传入 reward 决策参数（例如 `--reward-mode skip`）
- **THEN** 调试入口 MUST 按该模式处理 `snapshot.phase = reward` 的窗口
- **THEN** 调试入口 MUST 在 trace 中记录 reward 决策的输入与输出

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

#### Scenario: 同一玩家回合内连续执行多步
- **WHEN** 当前 phase 为 `combat`，且玩家回合仍可继续提交 legal actions
- **THEN** runner MUST 在每次动作执行后重新读取最新 `snapshot` 与 `legal actions`
- **THEN** runner MUST 基于最新 live state 继续请求模型决策，直到命中停止条件

#### Scenario: 渲染描述与词条锚点可用时进入策略输入
- **WHEN** bridge 已在当前 snapshot 中导出 `description_rendered`、`description_vars` 或 glossary 锚点
- **THEN** runner MUST 优先把这些字段纳入策略输入摘要
- **THEN** 策略层 MUST 不再只能依赖卡名与模板文本猜测效果



### Requirement: runner 必须用当前 legal actions 驱动模型单步决策
系统 MUST 提供一个 `llm-autoplay-runner`，在每一步从 bridge 读取当前 `snapshot` 与 `legal actions`，再调用 LLM policy 生成动作决策。runner MUST 只允许模型从当前 legal set 中选择动作，并在提交前完成本地校验。

#### Scenario: 模型选择当前合法动作
- **WHEN** runner 拿到当前 decision 的 `legal actions`
- **THEN** runner MUST 将这些动作传给 LLM policy
- **THEN** 若模型返回的 `action_id` 属于当前 legal set，runner MUST 才能提交到 bridge

#### Scenario: 模型返回不存在的 action_id
- **WHEN** 模型返回的 `action_id` 不属于当前 legal set
- **THEN** runner MUST 将该结果视为无效模型输出
- **THEN** runner MUST NOT 直接调用 `/apply`

### Requirement: runner 必须支持 dry-run、停止条件与失败回退
runner MUST 支持 dry-run 模式、`max_steps` 限制、人工停止和模型失败中断。dry-run 模式下，runner MUST 完整执行读取与模型决策流程，但 MUST NOT 真的向 bridge 发送 `/apply`。

#### Scenario: dry-run 模式只记录不执行
- **WHEN** 调用方以 dry-run 模式启动 runner
- **THEN** runner MUST 获取 snapshot、actions 并调用模型
- **THEN** runner MUST 只记录计划动作，而不向 bridge 提交真实写请求

#### Scenario: 达到最大步数后停止
- **WHEN** 自动打牌步数达到 `max_steps`
- **THEN** runner MUST 停止继续请求模型
- **THEN** 结果 MUST 标记为因 `max_steps_exceeded` 或等效原因中断

#### Scenario: 模型连续失败后中断
- **WHEN** 模型请求失败、解析失败或返回非法动作，且已达到允许的重试上限
- **THEN** runner MUST 中断当前 autoplay
- **THEN** 结果 MUST 明确记录失败原因，而不是继续盲打

### Requirement: runner 必须为每一步落盘可复盘 trace
runner MUST 为每一步保存结构化 trace，至少包含当前 snapshot、legal actions、模型输出、bridge 回执与时间戳。若模型请求已发出，trace SHOULD 包含请求摘要、原始响应文本或等效诊断字段，便于回放与排障。

#### Scenario: 正常执行一步动作
- **WHEN** runner 完成一轮“读取状态 -> 调模型 -> 提交动作”
- **THEN** trace MUST 记录 observation、legal actions、policy_output 与 bridge_result
- **THEN** trace MUST 能唯一对应到当前 `decision_id`

#### Scenario: 模型侧失败也有 trace
- **WHEN** runner 在模型请求或响应解析阶段失败
- **THEN** trace MUST 记录失败时的 snapshot、legal actions 与错误信息
- **THEN** 后续分析 MUST 能区分是模型失败还是 bridge 失败

### Requirement: runner 必须提供面向本地兼容接口的调试入口
系统 MUST 提供一个本地可执行的调试入口，用于连接 OpenAI 兼容接口和 live bridge 完成端到端联调。该入口 MUST 支持通过参数或环境变量设置 `base_url`、`model`、`api_key`、`bridge_base_url`、`dry_run` 与 `trace_dir`。

#### Scenario: 使用本地 chat completions 接口启动 autoplay
- **WHEN** 调用方把 `base_url` 设为 `http://127.0.0.1:8080/v1`
- **THEN** 调试入口 MUST 能正常构造 LLM policy
- **THEN** 调试入口 MUST 能连接 live bridge 并开始自动决策循环

#### Scenario: CLI 参数覆盖默认配置
- **WHEN** 调用方在命令行显式传入 `--base-url`、`--model` 或 `--trace-dir`
- **THEN** 调试入口 MUST 使用这些参数覆盖默认值
- **THEN** 实际运行配置 MUST 可在 trace 或启动日志中被确认

### Requirement: runner 必须为多步执行落盘可复盘 trace 与回合摘要
runner MUST 为每一步保存结构化 trace，至少包含当前 snapshot、legal actions、模型输出、bridge 回执与时间戳。若模型请求已发出，trace SHOULD 包含请求摘要、原始响应文本或等效诊断字段，便于回放与排障。对于多步 autoplay，运行结果 MUST 能总结本回合执行了多少步、为何停止、是否正常完成该回合。

#### Scenario: 正常执行多步动作
- **WHEN** runner 在同一玩家回合内完成多轮“读取状态 -> 调模型 -> 提交动作”
- **THEN** 每一步 trace MUST 记录 observation、legal actions、policy_output 与 bridge_result
- **THEN** trace MUST 能区分这些记录属于同一次回合级 autoplay

#### Scenario: 本回合正常结束后输出摘要
- **WHEN** runner 因玩家回合结束、phase 切换或自动 `end_turn` 成功而停止
- **THEN** `RunSummary` 或等效结果 MUST 记录本回合执行动作数与停止原因
- **THEN** 调用方 MUST 能区分“回合完成”与“异常中断”

#### Scenario: 模型侧失败也有 trace
- **WHEN** runner 在模型请求或响应解析阶段失败
- **THEN** trace MUST 记录失败时的 snapshot、legal actions 与错误信息
- **THEN** 后续分析 MUST 能区分是模型失败还是 bridge 失败

### Requirement: runner 必须处理 reward 收尾前进动作
当 reward 链路进入“前进/继续”按钮窗口时，runner MUST 将其视为 reward 链路中的可执行步骤，而不是把它误判为空 reward 或异常卡死。只要 bridge 已导出对应 legal action，runner MUST 能提交该动作并继续等待地图出现。

#### Scenario: reward 收尾窗口存在 continue/advance 动作
- **WHEN** `snapshot.phase=reward`，且 metadata 表示 reward 收尾子窗口，`actions` 中存在 continue/advance 对应 legal action
- **THEN** runner MUST 优先执行该动作，而不是因 `rewards=[]` 或空策略空间而停止
- **THEN** 提交动作后 runner MUST 继续推进到 `map` 或房间过渡状态

#### Scenario: reward 收尾窗口没有动作时视为 bridge 异常
- **WHEN** runner 观察到 reward 收尾窗口，但 `actions=[]` 持续存在并超过安全等待预算
- **THEN** runner MUST 将该情况记录为 bridge/phase 导出异常
- **THEN** 运行结果与 trace MUST 能明确区分这类失败，而不是只输出泛化的 `transition_timeout`

### Requirement: live 验证必须覆盖 reward continue 到 map 链路
系统 MUST 提供自动化验证路径，能够在真实游戏运行时覆盖“奖励收尾 -> 点击前进/继续 -> 进入地图”这一链路，并把空 reward、前进动作提交、地图出现等关键节点写入 artifacts。

#### Scenario: live 验证成功进入地图
- **WHEN** 游戏处于 reward 收尾窗口，且 bridge 允许写入
- **THEN** 验证脚本 MUST 能识别并提交 continue/advance 动作
- **THEN** artifacts MUST 记录动作提交前后快照与最终进入 `map` 的结果

#### Scenario: live 验证发现空 reward 卡死
- **WHEN** 游戏停留在 `phase=reward` 且 `reward_count=0`、`actions=[]` 的状态超过阈值
- **THEN** 验证脚本 MUST 将该情况判定为失败
- **THEN** artifacts MUST 记录最后一个 reward 子窗口、最后一次动作与超时前的 diagnostics

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
