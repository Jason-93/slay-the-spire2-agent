## ADDED Requirements

### Requirement: Orchestrator MUST 支持 shop phase 的稳定窗口编排
系统 MUST 将 `shop` 视为与 `event`、`reward`、`map` 并列的非战斗决策窗口。在 live runtime 中，orchestrator MUST 先等待商店窗口稳定，再调用 policy 或执行配置化的 shop mode 逻辑，而不是在窗口切换中盲目提交购买动作。

#### Scenario: 商店窗口尚未稳定时先等待
- **WHEN** autoplay 观测到当前正在从地图或战斗过渡到商店，且 shop legal actions 尚未稳定
- **THEN** orchestrator MUST 进入等待 / 重观测路径
- **THEN** orchestrator MUST NOT 在该时刻直接请求 policy 返回购买动作

#### Scenario: 稳定商店窗口后再请求策略
- **WHEN** autoplay 观测到稳定的 `shop` snapshot 与 legal actions
- **THEN** orchestrator MUST 以 shop phase 调用 policy 或 shop mode 逻辑
- **THEN** 后续 trace MUST 记录商店动作、购买结果或 halt 原因

### Requirement: Orchestrator MUST 提供显式 shop_mode
系统 MUST 为商店场景提供独立的 `shop_mode`，至少支持 `halt`、`safe-default` 与 `llm`。默认配置 SHOULD 偏保守；在 `halt` 模式下，orchestrator MUST 在进入商店时停止并保留当前状态，避免未授权的自动消费。

#### Scenario: `shop_mode=halt` 时停止在商店
- **WHEN** autoplay 进入商店且配置 `shop_mode=halt`
- **THEN** orchestrator MUST 停止继续自动推进
- **THEN** 结果 MUST 记录停止原因为 shop phase reached 或等效原因

#### Scenario: `shop_mode=safe-default` 时保守离开
- **WHEN** autoplay 进入商店且配置 `shop_mode=safe-default`
- **THEN** orchestrator MUST 只执行预定义的保守动作，例如直接离开商店
- **THEN** orchestrator MUST NOT 在没有显式策略判断的前提下自动购买商品

#### Scenario: `shop_mode=llm` 时允许策略选择商店动作
- **WHEN** autoplay 进入稳定商店窗口且配置 `shop_mode=llm`
- **THEN** orchestrator MUST 把商店 snapshot 与 legal actions 提供给 policy
- **THEN** orchestrator MUST 支持提交购买或离开商店动作，并沿用现有 reject / recovery 机制
