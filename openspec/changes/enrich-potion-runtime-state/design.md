## Context

当前 bridge 已经能在 `combat` 快照里导出卡牌、敌人、powers、牌堆与 run_state，但 `player.potions` 仍停留在字符串数组。mod 侧实际上已经能枚举药水槽位，因此本次不是“能不能看到药水”，而是“怎样把药水补充成可决策的资源对象”。这个变更会同时影响 C# runtime contracts、Python models / HTTP decode、fixture、LLM summary，以及 `use_potion` 相关 metadata。

## Goals / Non-Goals

**Goals:**
- 将 `player.potions` 升级为结构化 `PotionView`，至少提供 `name`、`description`、`canonical_potion_id` 与可选 glossary。
- 在 `player` 上补充稳定的药水栏容量字段，优先使用单值 `potion_capacity`，让上层能结合 `len(potions)` 直接推导剩余空间。
- 让 `use_potion` 的 legal action metadata 能引用当前药水对象，避免策略层在动作列表和快照之间再次按名称猜测关联。
- 保持 fail-safe：若 live runtime 暂时拿不到某瓶药水的描述，仍返回最小 potion object，而不是让整份快照失败。

**Non-Goals:**
- 本次不实现所有药水的目标细分、自动选目标策略或完整 use-potion 执行增强。
- 本次不扩展到遗物槽位、背包页或战后掉落药水选择窗口。
- 本次不引入独立“资源百科库”；仅预留稳定知识锚点。

## Decisions

### 决策 1：直接把 `player.potions` 升级为结构化对象，而不是新增并行 `potion_details`
- 方案：将 `player.potions` 从 `list[str]` 升级为 `list[PotionView]`，并让每个对象至少包含 `name`，其余 richer 字段按可选策略追加。
- 原因：大模型和策略层最常直接读取 `player.potions`；如果继续保留字符串数组，再新增 `potion_details`，会制造双轨协议和重复同步成本。
- 代价：这是一次 breaking schema 变更，需要同时更新 Python decode、fixtures 与 tests。
- 备选方案：保留 `potions: list[str]`，新增 `potion_details`。放弃原因是调用方仍需要手动 join 两套结构，不利于 prompt 直接消费。

### 决策 2：容量信息先用 `potion_capacity` 单值表达
- 方案：在 `player` 上增加 `potion_capacity`，当前已占用槽位继续由 `len(potions)` 表达。
- 原因：用户当前最需要的是“上限”；用单值即可回答“战后还能不能接药水”。剩余空间可以稳定推导，避免先引入更重的 slot schema。
- 备选方案：导出完整 `potion_slots` 数组。放弃原因是当前需求还没要求空槽逐一建模，复杂度高于收益。

### 决策 3：PotionView 复用现有说明对象语义
- 方案：PotionView 采用与 card / power 相近的导出方式，包含 `description`、`glossary`、`canonical_potion_id`，并允许 description 缺失时保底返回 `name`。
- 原因：这样 Python policy、trace 与未来知识层可以复用现有“说明 + glossary + canonical id”消费路径，不必为药水再造一套解释协议。
- 备选方案：只导出 `description` 而不导出 glossary / canonical id。放弃原因是这会削弱后续百科锚点与术语提示能力。

### 决策 4：`use_potion` action metadata 引用 potion preview，而不改动动作主参数
- 方案：保留当前 `use_potion` 动作基本触发方式，同时在 metadata 中增加 `potion_preview` 或等效结构化引用。
- 原因：这样可以先增强决策上下文，不必在同一变更里同时重写 potion apply 路径。
- 备选方案：同时把 `use_potion` 参数改成实例级 `potion_id`。放弃原因是当前用户需求聚焦观察质量，动作实例化可以后续再独立强化。

## Risks / Trade-offs

- [Risk] `player.potions` 改型会影响现有 Python client / fixtures / tests -> Mitigation：在同一 change 中同步更新 models、decode、policy summary 与 fixtures，避免半迁移状态。
- [Risk] 某些药水 runtime 只能拿到槽位名或短标签，描述提取不稳定 -> Mitigation：PotionView 允许 `description=null`，并在 mod 端优先尝试 hover tip / model description / localization 多路径。
- [Risk] `potion_capacity` 在不同角色或遗物修饰下读取路径可能不一致 -> Mitigation：先定义稳定字段语义，runtime 端允许保守 fallback 到已知默认值并记录 diagnostics。
- [Risk] `use_potion` 仍按名称触发时，重复同名药水的长期扩展性有限 -> Mitigation：本次先解决观察问题，并在设计中保留后续升级到实例级 `potion_id` 的空间。
