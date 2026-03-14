## MODIFIED Requirements

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
