## ADDED Requirements

### Requirement: 系统必须在 live battle 中对动作拒绝执行稳定分类
系统 MUST 在 live runtime autoplay 中对动作拒绝、窗口失配和提交前拦截执行统一分类，至少区分 `recoverable_stale`、`recoverable_timing`、`invalid_policy_decision` 与 `hard_runtime_reject` 四类。分类结果 MUST 能同时进入 trace、summary 或等效 diagnostics，而不能只保留底层异常文本。

#### Scenario: stale_action 被识别为可恢复拒绝
- **WHEN** bridge 返回 `stale_action`、`selection_window_changed` 或等效当前窗口已漂移错误
- **THEN** 系统 MUST 将该次失败分类为 `recoverable_stale`
- **THEN** diagnostics MUST 同时保留原始错误码与分类结果

#### Scenario: 模型返回非法动作被识别为策略错误
- **WHEN** 模型返回的 `action_id` 不属于当前 legal set，或缺少必要 `target_id`
- **THEN** 系统 MUST 将该次失败分类为 `invalid_policy_decision`
- **THEN** 系统 MUST NOT 将其误记为 bridge runtime reject

### Requirement: 系统必须在提交前拦截已知高风险动作窗口
系统 MUST 在真正调用 `/apply` 前检查当前 live 窗口是否满足最低稳定性门槛。若当前处于 transition、非玩家可操作态、selection 切换边缘、或等效高风险窗口，系统 MUST 优先等待或重观测，而不是盲目提交动作。

#### Scenario: 非玩家操作窗口下不提交动作
- **WHEN** 当前 `snapshot.phase` 仍为 `combat`，但 `current_side`、`window_kind` 或等效 metadata 表明此时不应提交玩家动作
- **THEN** 系统 MUST 暂缓本次 `/apply`
- **THEN** trace MUST 记录这是一次 pre-submit gate 拦截，而不是 bridge reject

#### Scenario: selection 切换窗口下先重观测
- **WHEN** 当前快照仍处于额外选牌、窗口切换或等效不稳定边缘态
- **THEN** 系统 MUST 先重新获取 `snapshot/actions`
- **THEN** 只有在重新观测后窗口稳定，系统 MUST 才能继续提交动作
