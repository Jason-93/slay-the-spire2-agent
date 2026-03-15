## ADDED Requirements

### Requirement: live runtime bridge 必须导出结构化药水说明
当 `snapshot.phase` 处于可见玩家资源的窗口时，bridge MUST 从 live runtime 导出结构化药水对象，而不是只返回槽位标签。对于当前持有的每一瓶药水，bridge MUST 至少稳定导出 `name`，并在可读时 MUST 补充 `description`、`canonical_potion_id`、`glossary` 或等效稳定说明字段。

#### Scenario: runtime 可读取药水说明时直接导出
- **WHEN** 当前玩家药水槽位中的某瓶药水存在可访问的模型说明、hover tip 或等效 runtime 文本来源
- **THEN** `snapshot.player.potions[]` 对应条目 MUST 直接返回该药水的用户向说明文本
- **THEN** 若存在 glossary 词条，bridge MUST 一并导出结构化 glossary anchors

#### Scenario: runtime 只能读取药水名称时保守降级
- **WHEN** 当前 bridge 只能从槽位节点拿到药水名称，拿不到稳定说明文本
- **THEN** `snapshot.player.potions[]` MUST 仍返回结构化对象
- **THEN** 该条目 MUST 至少包含 `name`
- **THEN** bridge MUST 保持响应成功，而不是因为 description 缺失而失败

### Requirement: live runtime bridge 必须导出当前药水栏上限
bridge MUST 从 live runtime 导出当前玩家药水栏上限，并以 `potion_capacity` 或等效稳定字段写入 `snapshot.player`。当 runtime 读取路径存在版本差异时，bridge MUST 使用保守 fallback，并保持字段语义稳定。

#### Scenario: 战斗快照包含当前药水栏上限
- **WHEN** agent 在战斗中读取 live snapshot
- **THEN** `snapshot.player` MUST 包含 `potion_capacity` 或等效稳定字段
- **THEN** 该字段 MUST 表示当前 run / 角色 / 遗物修饰后的真实药水栏上限，而不是仅依赖调用方默认假设

### Requirement: use_potion 动作 metadata 必须复用结构化药水语义
当 bridge 导出 `use_potion` legal action 时，动作 metadata MUST 复用与 `snapshot.player.potions[]` 一致的药水观察语义，例如提供 `potion_preview`、稳定名称或知识锚点，以便策略层在动作列表中直接理解药水效果。

#### Scenario: use_potion metadata 提供当前药水预览
- **WHEN** `actions` 中存在某个 `type="use_potion"` 的 legal action
- **THEN** 该 action 的 metadata MUST 在可用时提供与对应药水一致的预览信息
- **THEN** 预览中的 `description` 与 `canonical_potion_id` 语义 MUST 与 `snapshot.player.potions[]` 保持一致或等效一致
