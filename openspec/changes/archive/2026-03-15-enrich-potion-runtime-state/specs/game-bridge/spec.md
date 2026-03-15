## ADDED Requirements

### Requirement: Bridge 必须导出结构化药水状态与药水栏容量
系统 MUST 在 `snapshot.player` 中导出面向决策的结构化药水状态，而不是仅提供药水名称列表。`player.potions` MUST 表示当前持有药水的结构化列表；每个条目至少 MUST 包含 `name`，并在可用时补充 `description`、`canonical_potion_id`、`glossary` 或等效稳定字段。`player` 同时 MUST 导出 `potion_capacity` 或等效稳定容量字段，用于表示当前药水栏上限。

#### Scenario: 战斗快照包含结构化药水与容量
- **WHEN** agent 在战斗中请求当前快照，且玩家持有至少一瓶药水
- **THEN** `snapshot.player.potions` MUST 返回结构化药水对象列表，而不是纯字符串数组
- **THEN** 每个药水对象 MUST 至少包含 `name`
- **THEN** `snapshot.player` MUST 同时返回 `potion_capacity` 或等效稳定字段

#### Scenario: 药水描述暂不可读时仍保持稳定结构
- **WHEN** bridge 当前只能识别药水名称，但暂时无法稳定解析某瓶药水的说明文本
- **THEN** 对应 `player.potions[]` 条目 MUST 仍然作为结构化对象返回
- **THEN** 该条目的 `description` 在缺失时 MUST 显式返回空值、缺省值或等效稳定空语义
- **THEN** bridge MUST NOT 因单瓶药水说明缺失而让整个 `snapshot` 失效

### Requirement: 药水动作必须能与结构化药水观察稳定关联
当 `actions` 中存在 `use_potion` 时，bridge MUST 让调用方能够把该动作与 `snapshot.player.potions[]` 中的具体药水稳定关联。bridge 即使继续沿用当前动作主参数，仍 MUST 在参数或 metadata 中提供足以定位对应药水对象的稳定信息。

#### Scenario: use_potion legal action 可关联到当前药水对象
- **WHEN** 当前 `actions` 中存在某个 `type="use_potion"` 的 legal action
- **THEN** 该 action MUST 能通过参数或 metadata 指向 `snapshot.player.potions[]` 中的一瓶当前药水
- **THEN** 调用方 MUST 不需要仅靠字符串模糊匹配来判断动作对应哪瓶药水
