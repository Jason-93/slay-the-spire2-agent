## ADDED Requirements

### Requirement: bridge 必须支持 use_potion 的真实受控执行
系统 MUST 在 `apply action` 链路中支持 `type="use_potion"` 的真实执行，而不是仅把该动作暴露在 legal actions 中。bridge MUST 基于当前 live 决策窗口重新校验药水实例与使用条件，并在执行完成后返回与其他核心动作一致的结构化回执。

#### Scenario: 合法 use_potion 被成功接受并执行
- **WHEN** 当前 phase 允许使用药水，且 legal actions 中存在某个 `use_potion`
- **THEN** bridge MUST 能基于该 action 的参数定位当前药水实例并触发真实游戏内使用流程
- **THEN** 返回结果 MUST 标记为已接受或等效成功状态
- **THEN** 返回 metadata MUST 包含 `action_type="use_potion"`、`potion_index` 与 `runtime_handler` 或等效诊断字段

#### Scenario: 药水实例已变化时拒绝旧 use_potion
- **WHEN** 外部 agent 提交的 `use_potion` 对应 `potion_index` 或实例语义已不再匹配当前 live 药水栏
- **THEN** bridge MUST 拒绝执行该动作
- **THEN** 返回结果 MUST 标记为 `stale_action`、`invalid_action` 或等效可恢复错误原因

### Requirement: bridge 必须为 use_potion 返回可区分的失败语义
当 `use_potion` 提交后无法完成真实执行时，bridge MUST 区分“当前窗口不允许使用”“药水需要目标但当前协议未提供”“运行时入口不可用”“药水已不存在或不可点击”等不同失败阶段，而不是统一退化为无上下文失败。

#### Scenario: 当前规则不允许使用药水时返回结构化拒绝
- **WHEN** 当前 phase、窗口或规则不允许使用该瓶药水
- **THEN** bridge MUST 拒绝执行该动作
- **THEN** 返回结果 MUST 标记为 `not_allowed`、`runtime_incompatible` 或等效结构化错误码

#### Scenario: 药水需要目标但协议未提供目标参数
- **WHEN** 当前 `use_potion` 对应的真实运行时逻辑要求额外目标，而该 action 未提供目标参数
- **THEN** bridge MUST NOT 猜测目标并直接执行
- **THEN** 返回结果 MUST 标记为 `target_required`、`runtime_incompatible` 或等效错误原因
