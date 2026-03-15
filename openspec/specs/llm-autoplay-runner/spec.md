# llm-autoplay-runner Specification

## Purpose
定义基于本地 HTTP bridge 和 OpenAI 兼容模型接口的自动打牌执行闭环，确保 STS2 live runtime 可以安全地完成“读状态、调模型、提动作、记录 trace”的端到端自动决策流程。
## Requirements
### Requirement: runner 必须用当前 legal actions 与 richer snapshot 驱动模型连续决策
系统 MUST 提供一个 `llm-autoplay-runner`，在每一步从 bridge 读取当前 `snapshot` 与 `legal actions`，再调用 LLM policy 生成动作决策。runner MUST 只允许模型从当前 legal set 中选择动作，并在提交前完成本地校验。在 `combat` 中，runner MUST 能跨多个玩家回合连续执行，而不是在单个玩家回合结束后默认退出。当 bridge 已提供 richer runtime state 时，runner MUST 将对战斗决策有价值的 richer fields 一并提供给策略层；当这些字段部分缺失时，runner MUST 退化到基础 snapshot，而不是直接中断运行。

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

#### Scenario: richer 字段缺失时保持兼容运行
- **WHEN** 某次 snapshot 只包含基础字段，而 richer fields 缺失或为空
- **THEN** runner MUST 仍能继续执行当前 autoplay
- **THEN** 运行结果 MUST 体现为“降级运行”，而不是协议错误或强制中断

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

