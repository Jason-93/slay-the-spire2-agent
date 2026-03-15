## Context

当前 relic 已经能够导出结构化 `description`，但 `glossary` 仍沿用通用 glossary 提取链路，导致两个突出问题：第一，relic 自身常被再次识别成 glossary 项，形成“主 description 说一遍、glossary hint 再说一遍”的重复；第二，relic description 中命中的二级术语（如 `格挡`）会落到通用 fallback，出现 `hint=null`、`missing_hint` 或带模板变量的低质量 hint。对 agent 来说，这些冗余与脏数据会干扰 prompt 压缩和决策。

这次变更不调整 relic 主体 schema，而是在现有 `ExtractGlossaryAnchors(...)` 与 relic 专用提取路径之间增加更严格的 relic glossary 收敛规则。约束包括：优先保留真正对主 description 有补充价值的 glossary、过滤与 relic 主体重复的锚点、避免把低质量 fallback 直接暴露给客户端。

## Goals / Non-Goals

**Goals:**
- 让 `snapshot.player.relics[].glossary` 只保留对决策有补充价值的 glossary 项。
- 避免 relic 自身 title/hint 以 glossary 形式重复出现。
- 对二级术语优先输出已渲染、非模板、非空的 hint；拿不到时优先过滤而不是暴露脏数据。
- 保留日志 diagnostics，便于后续继续定位 glossary sourcing 问题。

**Non-Goals:**
- 不修改 relic 主体 `description` 的生成链路。
- 不扩展新的客户端字段或公开更多 diagnostics。
- 不在本次变更里引入完整的全量 glossary 百科表。

## Decisions

### 1. relic glossary 在 relic 路径上做二次过滤，而不是改全局 glossary 语义
在 `DescribeRelic(...)` 生成 glossary 后，增加 relic 专用的 post-process：按 `display_text`、`hint`、`canonical_relic_id` 与主 `description` 做重复检测，过滤“只是把 relic 自己再说一遍”的 glossary 项。

不直接修改全局 glossary 提取契约，因为 cards、powers、enemies 仍可能需要当前通用行为；relic 的重复问题最突出，先局部收敛更安全。

### 2. 对低质量 hint 采用“优先丢弃，日志保留”策略
对于 `hint=null`、`source=missing_hint`、仍包含模板占位符，或与主 description 近似重复的 relic glossary 项，优先不对外返回，同时在日志中记录被过滤原因。

不继续把低质量 hint 暴露给客户端再让上层猜，因为这会污染 agent 输入，并且与当前“公共 schema 尽量精简”的方向冲突。

### 3. 二级术语 hint 继续优先走 runtime 真实来源
像 `格挡` 这类术语，优先从 hover tip、模型说明、localization 等真实来源解析；若最终仍只能得到低质量 fallback，则不强行保留该 glossary 项。也就是说，glossary 的目标是“少而准”，而不是“命中术语就一定导出”。

### 4. validation 增加 relic glossary 质量断言
fixture / live validation 增加最小质量约束：relic glossary 不应包含空 hint、不应包含明显模板、不应出现仅重复 relic 自身说明的条目。这样后续继续改 runtime 文本链路时，能及时发现回归。

## Risks / Trade-offs

- [过滤过严导致 glossary 数量下降] → 优先保留真正提供新增语义的术语项，并通过日志记录被过滤原因，便于回调阈值。
- [重复判定过于依赖中文文本相似度] → 先使用保守规则（完全相同、规范化后相同、显然只是 relic 名称自身）而不是激进模糊匹配。
- [不同语言下 hint 来源差异较大] → 过滤条件优先基于结构信号（空 hint、模板残留、missing source），减少对单语言文本的强耦合。
- [局部 special-case 增加代码复杂度] → 将 relic post-process 控制在 relic 提取路径内，不扩散到 cards/potions/enemies。

## Migration Plan

1. 在 relic 提取路径增加 glossary post-process 与 diagnostics。
2. 更新 fixture / Python tests / live validation 断言。
3. 用真实 runtime 验证常见 relic（如 `永冻冰晶`、`燃烧之血`）的 glossary 已去重且 hint 质量可接受。
4. 若 live 中发现过滤过严，可仅回调阈值，不需要改公共 schema。

## Open Questions

- 对于没有稳定二级 hint 的术语，是否应该完全过滤，还是允许保留 `display_text` 但隐藏 `hint`；本次先倾向完全过滤低价值项。
- 后续是否要把 glossary quality 收敛规则推广到 powers / enemies；本 change 先只覆盖 relic。
