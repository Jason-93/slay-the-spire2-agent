## MODIFIED Requirements

### Requirement: runner 必须用当前 legal actions 与 richer snapshot 驱动模型连续决策
系统 MUST 提供一个 `llm-autoplay-runner`，在每一步从 bridge 读取当前 `snapshot` 与 `legal actions`，再调用 LLM policy 生成动作决策。runner MUST 只允许模型从当前 legal set 中选择动作，并在提交前完成本地校验。在 `combat` 中，runner MUST 能跨多个玩家回合连续执行，而不是在单个玩家回合结束后默认退出。当 bridge 已提供 richer runtime state 时，runner MUST 将对战斗决策有价值的 richer fields 一并提供给策略层；当这些字段部分缺失时，runner MUST 退化到基础 snapshot，而不是直接中断运行。对于 live runtime，runner MUST 先等待稳定决策窗口，再调用模型；若模型返回后窗口发生漂移，runner MUST 重新观测并重做决策，而不是继续提交旧动作。

#### Scenario: 模型只在稳定窗口上收到决策输入
- **WHEN** runner 拿到某次 live `combat` observation 与 `legal actions`
- **THEN** runner MUST 先确认该 observation 已满足稳定窗口条件
- **THEN** 只有稳定后，runner MUST 才能把当前 legal actions 与 snapshot 传给 LLM policy

#### Scenario: 模型返回后窗口漂移触发重决策
- **WHEN** 模型已返回某个 `action_id`，但提交前 runner 发现 `phase`、`window_kind`、`current_side`、`round_number`、`selection_kind` 或 legal actions 已变化
- **THEN** runner MUST 放弃该次旧模型输出并重新观测最新状态
- **THEN** runner MUST 在窗口重新稳定后再次请求模型，而不是直接调用 `/apply`

#### Scenario: richer snapshot 可用时进入策略输入
- **WHEN** bridge 在 combat snapshot 中导出了卡牌描述、结构化 intent、powers 或等效 richer fields
- **THEN** runner MUST 将这些高价值字段纳入策略输入摘要
- **THEN** 策略层 MUST 不再只能依赖卡名与模糊 intent 做判断

#### Scenario: richer 字段缺失时保持兼容运行
- **WHEN** 某次 snapshot 只包含基础字段，而 richer fields 缺失或为空
- **THEN** runner MUST 仍能继续执行当前 autoplay
- **THEN** 运行结果 MUST 体现为“降级运行”，而不是协议错误或强制中断

### Requirement: runner 必须支持 battle 级停止条件、dry-run 与失败回退
runner MUST 支持 dry-run 模式、`max_steps` 限制、人工停止和模型失败中断。dry-run 模式下，runner MUST 完整执行读取与模型决策流程，但 MUST NOT 真的向 bridge 发送 `/apply`。在整场战斗 autoplay 场景下，runner MUST 额外支持 battle 级停止条件，例如战斗结束、最大回合数、最大总动作数、下一玩家回合等待超时、模型 halt、bridge 拒绝或连续失败超过预算。对于 live reject，runner MUST 区分可恢复与不可恢复失败，并优先走可恢复回退路径。对于 pre-submit gate 检测到的窗口漂移，runner MUST 把它视作可恢复的重观测 / 重决策路径，而不是把旧动作强行提交。

#### Scenario: gate 检测到窗口漂移后进入恢复
- **WHEN** runner 在提交前发现旧动作对应窗口已经失稳或变更
- **THEN** runner MUST 执行 reobserve -> restabilize -> redecide
- **THEN** 若恢复成功，runner MUST 继续 battle autoplay，而不是把这次漂移直接视作终止错误

#### Scenario: `end_turn` 与 `use_potion` 不跨窗口复用
- **WHEN** 某次模型输出为 `end_turn` 或 `use_potion`，且提交前 stable window 已变化
- **THEN** runner MUST 作废该模型输出并重新请求模型
- **THEN** runner MUST NOT 通过 rebase 把这类低信息动作提交到新窗口

### Requirement: runner 必须为整场战斗执行落盘可复盘 trace 与 battle 摘要
runner MUST 为每一步保存结构化 trace，至少包含当前 snapshot、legal actions、模型输出、bridge 回执与时间戳。若模型请求已发出，trace SHOULD 包含请求摘要、原始响应文本或等效诊断字段，便于回放与排障。对于整场战斗 autoplay，运行结果 MUST 能总结已完成回合数、总动作数、是否真正打完战斗以及最终停止原因；若 battle 过程中发生 reject、稳定窗口等待或重决策，summary MUST 额外记录 gate 分类、恢复计数与分类汇总。

#### Scenario: trace 记录稳定窗口门控结果
- **WHEN** runner 在 live battle 中进行一次决策尝试
- **THEN** 该步 trace MUST 记录 `gate_status`、`gate_reason`、是否发生 restabilize / redecide，以及最终是否提交动作
- **THEN** 调用方 MUST 能从 trace 判断该步是正常通过、同窗口 rebase 还是因窗口漂移重新决策

#### Scenario: summary 能定位提前结束回合问题
- **WHEN** 某次 battle 运行中出现错误 `end_turn`、频繁 gate miss 或多次重新决策
- **THEN** summary MUST 记录对应计数、最近一次关键上下文与最终 stop reason
- **THEN** artifacts MUST 足以区分“策略主动结束回合”和“时序漂移导致的错误结束回合”
