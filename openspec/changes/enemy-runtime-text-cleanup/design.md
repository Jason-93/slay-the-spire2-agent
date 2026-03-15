## Context

当前 bridge 已经能导出 `snapshot.enemies[]` 的 richer runtime state，但真实 live 数据里还能看到不少“更像内部实现细节而不是策略输入”的内容：`intent` / `move_name` 直接携带 Godot 富文本标签，`move_name` 有时只是 `2×3` 这种重复数值提示，`keywords` 又会混入 `POWER.SLIPPERY_POWER` 这类内部 id；同时 `enemy.powers[].glossary` 里也会出现与 power 本体名称/说明重复的 identity glossary。对 agent 来说，这些字段并非完全不可用，但会显著降低 prompt 可读性，并让“怪物到底要做什么”仍然需要额外猜测。

这次变更会同时影响 C# runtime reader、enemy 对外 schema 的质量约束，以及 Python live validation。目标不是再加更多 enemy 字段，而是把现有字段收敛成更稳定的 canonical 语义：`intent` / `intent_type` 表达结构化意图，`move_name` 仅在确实有独立招式名时出现，`move_description` 负责给出面向玩家的可读动作描述，`keywords` / `move_glossary` 只保留高价值机制锚点。

## Goals / Non-Goals

**Goals:**
- 清理 enemy `intent`、`intent_raw`、`move_name`、`move_description` 中的富文本残留，使其输出为稳定可读文本。
- 抑制仅重复数值意图或与 `intent` 等价的低价值 `move_name`，避免同一语义在多个字段重复出现。
- 过滤 enemy `keywords` 中的内部 id、低价值重复 token，以及 `enemy.powers[].glossary` 中与 power 本体说明重复、空 hint、模板残留的条目，并尽量保留能帮助模型理解机制的 canonical 术语。
- 在 validation 中把 enemy 文本质量纳入回归检查，避免后续又把 UI markup 或内部标识泄漏给客户端。

**Non-Goals:**
- 本次不新增怪物百科库、长期知识层或额外 enemy schema 分层。
- 本次不改动 enemy action targeting、伤害计算逻辑或 intent 数值推导算法。
- 本次不要求所有敌人都必须导出 `move_name`；无独立招式名时允许为空。

## Decisions

### 决策 1：`move_name` 只在存在独立招式名时保留
- 方案：若当前 `move_name` 只是 `intent` 的富文本/数字变体，或仅重复攻击次数/数值 UI，则对外置空，由 `move_description` 承担主要解释职责。
- 原因：对 agent 来说，“攻势”“策略”“2×3” 这种字段若不能额外提供机制信息，只会制造重复噪音。
- 备选方案：始终保留 runtime 原始 move label。放弃原因是会把 UI 层展示细节暴露给客户端。

### 决策 2：enemy 文本统一走 canonical 规范化，而不是让 Python 再次清洗
- 方案：在 mod 端统一清理 `[font_size]`、富文本标签、纯展示性数值格式，并输出规范化文本给 `intent` / `move_description`。
- 原因：用户已经明确希望 description/rendering 尽量留在 mod 端完成；enemy 文本也应延续同样原则。
- 备选方案：客户端对 enemy 文本二次正则清洗。放弃原因是会把 runtime 差异和文本解析复杂度重新推回 Python 层。

### 决策 3：`keywords` 只保留面向机制理解的稳定锚点
- 方案：过滤明显属于内部标识的 power id、canonical id、类型名和与 powers/relic 已重复表达的低价值 token；优先保留如 `damage`、`debuff`、`artifact` 等机制关键词。
- 原因：`keywords` 的价值在于补充策略理解，而不是泄漏内部对象命名。
- 备选方案：保留当前所有提取结果。放弃原因是会让 `keywords` 变成“噪音回收站”，模型难以区分什么才重要。

### 决策 4：enemy power glossary 复用已有的 identity/模板过滤模型
- 方案：对 `enemy.powers[].glossary` 复用当前 relic / potion 已有的 post-process 过滤思路，去掉与 power 名称或 power description 重复的 identity glossary，以及空 hint、`missing_hint`、模板残留条目。
- 原因：enemy powers 的 glossary 问题本质和 relic / potion 相同，都是“本体说明已经有一份，glossary 又重复一份”。
- 备选方案：保留所有 power glossary，让客户端自行判断。放弃原因是会继续把低质量重复文本塞进 LLM prompt。

### 决策 5：enemy 文本质量用显式 validation 审计兜底
- 方案：扩展 live validation，检查 enemy `intent` / `move_name` / `move_description` / `keywords` / `powers[].glossary` 中的富文本残留、内部 id、重复字段与低质量 glossary。
- 原因：这类问题最容易在真实 runtime 中反复出现，仅靠单元测试不足以覆盖不同怪物/窗口。
- 备选方案：只在日志中提示，不让验证失败。放弃原因是很容易再次把低质量 enemy 文本放进 LLM prompt。

## Risks / Trade-offs

- [Risk] `move_name` 过滤过严，可能误删少数确有语义价值的短标签 -> Mitigation：用“是否仅重复 intent/数值展示”做保守判定，并保留日志。
- [Risk] `keywords` 去噪规则过强，可能把部分有价值的 canonical id 一并删掉 -> Mitigation：优先移除明显内部格式（如 `POWER.*`、类型名），并通过 live 快照回归抽样校验。
- [Risk] enemy power glossary 的 identity 过滤过严，可能误删少量确实有额外补充信息的同名词条 -> Mitigation：同时比较 `glossary_id`、`display_text` 与 `hint` 是否等价，并保留过滤日志。
- [Risk] 不同怪物的 intent 文本来源差异较大，统一规范化可能引入新边缘 case -> Mitigation：采用追加式规则，先处理富文本标签、数字乘号展示和内部 token 三类高频问题。
- [Risk] validation 新增失败条件后，live 检查更容易卡在敌人文本质量问题上 -> Mitigation：让 artifacts 明确记录 enemy path、字段名和失败原因，便于快速定点修复。
