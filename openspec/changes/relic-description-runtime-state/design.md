## Context

当前 bridge 对 relic 的导出仍停留在 `IReadOnlyList<string>`：runtime 侧通过 `ExtractLabels(...)` 只把 relic 名称扔进 `snapshot.player.relics`。这比早期“只要能看见 relic 名字”已经够用，但对 agent 决策明显不够：例如 `燃烧之血`、`战纹涂料`、`永冻冰晶` 都会改变战斗策略，可只看名字时，大模型既不知道效果文本，也无法挂到稳定知识锚点上。

仓库里已经有结构化 potion、power、card schema，可以复用同样思路：把 relic 从“标签字符串”升级为“带 canonical description 的结构化对象”。这次变更的难点不在协议设计，而在于如何从 live runtime 里稳定拿到 relic 说明，同时避免为了单个 relic 说明失败让整个 `snapshot` 降级。

## Goals / Non-Goals

**Goals:**
- 把 `snapshot.player.relics` 升级为结构化对象列表，并至少稳定导出 `name`。
- 在可用时为 relic 导出 `description`、`canonical_relic_id` 与 glossary / diagnostics 友好字段。
- 让 live runtime、fixture、Python models 与验证脚本对该 schema 一致。
- 对 description 缺失或解析失败的 relic 保持 fail-safe。

**Non-Goals:**
- 不在本变更中为 relic 增加动作执行能力。
- 不在本变更中构建完整 relic 百科或长期策略知识库。
- 不要求一次性覆盖所有版本差异下的每一条 relic 深层 metadata，只先保证结构化名称与说明文本。

## Decisions

### 1. `player.relics` 直接升级为结构化对象，而不是新增平行字段

设计上直接把 `player.relics` 从字符串数组升级为对象数组，而不是保留 `relics: string[]` 再新增 `relic_states` 或等效平行字段。这样与 `player.potions`、`powers` 的消费方式更一致，也避免调用方同时维护两套 relic 语义。

备选方案是保持旧字段不动，新增 `player.relic_details`。未采用，因为这会让策略层在两个 relic 字段之间做兼容分流，长期成本更高。

### 2. relic 说明优先复用 runtime 文本来源

runtime 侧应优先探测 relic 模型、hover tip、`Description` / `SmartDescription` / `RulesText` / localization 等真实文本来源，再做富文本规范化。仅在这些入口都失败时，才退回到“只有名称”的最小结构。

备选方案是手写一张 relic 说明表。未采用，因为维护成本高，而且不利于后续扩展到不同语言与游戏更新。

### 3. 复用现有说明对象收敛原则

对外 relic schema 继续采用单一 canonical `description`；不重新公开 `description_quality`、`description_source`、`description_vars`。这些诊断信息只留在日志或内部 diagnostics。这样可避免 relic 成为又一类需要客户端理解内部解析状态的特殊对象。

### 4. fixture 和 decode 必须先于 live 实现同步

因为这是公共 schema 的 breaking change，必须先更新 contracts、fixture provider 与 Python decode，再接入 live runtime 读取。这样可以用 fixture 测试先锁住 schema，再用 live 验证检查 description 质量，而不是直接在 live 上边改边猜。

## Risks / Trade-offs

- [Breaking change 会影响现有 client / policy] → 先在 fixture 和 Python tests 中统一改为结构化 relic schema，并在 proposal / specs 中显式标注 breaking。
- [部分 relic 拿不到稳定 description] → 返回最小结构 `{name, description=null}` 或等效空语义，并在日志打印 diagnostics。
- [relic 文本来源存在版本差异] → 复用当前 `RuntimeTextResolver` / glossary / fallback pipeline，尽量通过多源探测而不是单字段强绑定。
- [payload 体积增加] → relic 数量通常较少，且结构化收益远大于额外负载，当前可接受。

## Migration Plan

1. 先更新 contracts、fixture provider 与 Python models，把 `player.relics` 切到结构化对象。
2. 再在 runtime reader 中实现 relic description 与 canonical id 提取。
3. 补 fixture / Python / live validation，确保 relic 说明在结构上稳定，在 live 中可读。
4. 最后视需要更新 runner / policy 对 relic 摘要的呈现方式。

如需回滚，可把 runtime reader 暂时退回只填充 `name`，但仍保留结构化对象 schema；这样能避免再次来回切换公共协议。

## Open Questions

- 现有 runtime 中是否能稳定拿到 relic 的 canonical id，还是要先接受部分 relic 仅返回 `name + description`。
- glossary 对 relic 是否总有高价值，还是第一阶段只要求 `description`，glossary 作为可选增强。
