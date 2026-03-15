## ADDED Requirements

### Requirement: live runtime bridge 必须将 use_potion 映射到真实药水槽位实例
当 `actions` 中存在 `type="use_potion"` 时，in-game runtime bridge MUST 基于当前玩家药水栏重新定位该药水实例，并使用游戏内真实的药水使用入口执行。bridge MUST 优先使用 `potion_index` 做槽位定位，并在可用时用 `canonical_potion_id`、名称或等效实例特征做一致性复核。

#### Scenario: 通过 potion_index 定位并使用当前药水
- **WHEN** 当前玩家药水栏中第 `<potion_index>` 个槽位与 legal action 中的 `use_potion` 语义一致
- **THEN** bridge MUST 使用该槽位实例执行药水使用流程
- **THEN** 执行后的 live state MUST 反映药水已被消耗、移除或进入新的决策上下文

#### Scenario: 槽位已变化时拒绝执行
- **WHEN** legal action 中的 `potion_index` 指向的当前槽位已经为空、换成了别的药水，或与导出时的药水语义不一致
- **THEN** bridge MUST 拒绝执行该动作
- **THEN** 返回结果 MUST 标记为 `stale_action`、`invalid_action` 或等效错误原因

### Requirement: live runtime bridge 必须为药水动作导出阶段化 diagnostics
当 `use_potion` 被提交到 in-game queue 并进入真实执行链路时，bridge MUST 记录药水动作的阶段化 metadata，至少覆盖药水槽位、候选运行时入口、最终选中的 `runtime_handler` 与失败阶段，便于排查“未入队”“已消费但失败”“运行时入口不兼容”等问题。

#### Scenario: 药水动作成功执行时返回 handler diagnostics
- **WHEN** 某个 `use_potion` 请求在游戏线程中被成功消费并执行
- **THEN** action response metadata MUST 包含药水槽位索引与实际使用的 `runtime_handler`
- **THEN** metadata SHOULD 包含 `queue_stage`、执行耗时或等效阶段信息

#### Scenario: 运行时入口不兼容时仍保持 fail-safe
- **WHEN** bridge 无法解析当前版本对应的药水使用入口，或调用入口后立即抛出运行时异常
- **THEN** bridge MUST 返回结构化失败回执
- **THEN** 返回 metadata MUST 包含失败发生的阶段与候选 handler 诊断
- **THEN** mod MUST NOT 因单次药水执行失败而导致整个 bridge 不可用
