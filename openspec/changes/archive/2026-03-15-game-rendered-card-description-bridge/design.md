## Context

当前 `Sts2RuntimeReflectionReader` 的卡牌说明提取链路，主要还是在 `Description`、`RenderedDescription`、`RenderedText` 等字段之间做反射兜底，再在必要时进入 bridge 侧模板替换。这个方案对 `{Damage:diff()}`、`{Block:diff()}` 这类简单变量还能工作，但对 `CARD.TRUE_GRIT` 这类带条件选择器的描述会直接泄漏 `{IfUpgraded:show:| 随机}`，导致 agent 看到的不是游戏 UI 中真正渲染后的最终文本。

已有运行时检查显示，游戏 `CardModel` 已提供 `GetDescriptionForPile(MegaCrit.Sts2.Core.Entities.Cards.PileType pileType, MegaCrit.Sts2.Core.Entities.Creatures.Creature target)` 与 `GetDescriptionForUpgradePreview()`。这意味着 bridge 不需要继续把“解析 DSL”当作主路径，而应该优先调用游戏自己的最终描述入口，并把现有模板链路降级为 fallback。

这次变更需要同时覆盖 `snapshot.player.hand[]`、`draw_pile_cards`、`discard_pile_cards`、`exhaust_pile_cards` 与 `actions[].metadata.card_preview`，但又不能破坏当前对外 schema。对 agent 来说，公开字段仍应保持单一 canonical `description`；质量来源、回退原因等只保留在日志或内部 diagnostics 中。

## Goals / Non-Goals

**Goals:**
- 优先使用游戏 runtime 已完成上下文渲染的卡牌说明，而不是 bridge 侧模板文本。
- 让 hand、各类 pile cards 与 `card_preview` 共享一致的 canonical description 语义。
- 在最终描述 API 不可用时保留安全 fallback，避免单张卡牌说明失败拖垮整个 `snapshot` 或 `actions`。
- 把诊断信息收敛到日志或内部 diagnostics，保持公共协议精简。

**Non-Goals:**
- 不在本变更中实现通用的 STS2 文本 DSL 解释器。
- 不在本变更中重做 cards / powers / potions 的整体文本 schema。
- 不在本变更中扩展长期知识库、怪物百科或牌库规划能力。

## Decisions

### 1. 以游戏最终描述 API 作为第一优先级

卡牌说明解析将优先尝试 `GetDescriptionForPile(...)` 与 `GetDescriptionForUpgradePreview()` 这类游戏 runtime 自带入口；只有这些入口不可用、调用失败或返回空文本时，才退回现有 `RenderedDescription` / `RenderedText` / 模板 fallback 链路。

这样做的原因是：游戏自己最清楚升级条件、pile 语义与动态变量何时应该展开，bridge 不应长期和游戏 UI 并行维护另一套渲染逻辑。

备选方案是继续增强 `RenderTemplateDescription()`，补更多选择器与条件语法。未采用，因为该路径维护成本高，而且仍可能落后于游戏真实渲染语义。

### 2. 引入统一的卡牌 description 上下文解析器

实现上应把“如何生成 canonical card description”收敛到单一 helper，输入至少包含：
- 当前卡牌实例或模型引用
- description 上下文（hand / draw / discard / exhaust / preview）
- 可选 target

该 helper 负责选择正确的 runtime API、pile 语义与 fallback 顺序；`snapshot.player.hand[]`、pile cards 与 `actions[].metadata.card_preview` 都复用这条链路，而不是各自散落在不同导出点重复拼逻辑。

备选方案是在每个导出分支分别调用不同方法。未采用，因为一旦 fallback 顺序或 glossary 规范化需要调整，很容易再次出现 hand 与 preview 语义不一致。

### 3. pile / preview 语义显式映射到 runtime 上下文

bridge 需要把对外导出的观察位置映射到游戏内部的 description context：
- `snapshot.player.hand[]` 使用当前手牌所对应的 live pile 语义。
- `draw_pile_cards`、`discard_pile_cards`、`exhaust_pile_cards` 使用各自 pile 对应的 `PileType` 或等效上下文。
- `card_preview` 在升级预览或奖励预览场景下优先使用 `GetDescriptionForUpgradePreview()`，否则复用与来源卡牌一致的 pile 语义。

这样做可以避免把某个 hand 描述直接机械复制给所有 pile cards，减少“同一张卡在不同上下文展示不同说明”时的误差。

备选方案是始终只用当前实例上的 `RenderedDescription`。未采用，因为它并不保证已经覆盖 pile 与 preview 的完整语义。

### 4. 公共协议继续保持单一 `description`

对外 schema 不新增 `description_rendered`、`description_quality`、`description_source`、`description_vars` 等公开字段。公开协议继续只保留面向 agent 的 canonical `description`；解析来源、失败阶段、原始模板、pile context 与异常信息进入日志或内部 diagnostics。

这样做可以避免策略层再次承担“挑哪个 description 字段可信”的负担，也符合当前仓库已经收敛公共 schema 的方向。

备选方案是同时公开 canonical 文本和一组调试字段。未采用，因为这会重新把排障细节泄漏给 client。

## Risks / Trade-offs

- [`PileType` 映射错误导致文本与 UI 轻微漂移] -> 在日志中记录 description context 与最终 source，并用 `TRUE_GRIT`、升级预览、pile cards 做回归验证。
- [部分版本或对象缺少最终描述 API] -> 保留现有 `RenderedDescription` 与模板 fallback 链路，确保 bridge 仍能返回可读文本。
- [target 相关描述在无目标上下文下不完全一致] -> helper 接受可选 target；拿不到稳定 target 时优先返回无目标 canonical 文本，并在日志中记录降级。
- [统一 resolver 改造会影响多个导出点] -> 通过单一 helper 复用逻辑，并补 hand / piles / preview 的一致性测试，减少分叉行为。

## Migration Plan

1. 先在 `Sts2RuntimeReflectionReader` 内实现统一的 card description resolver，并接入游戏最终描述 API。
2. 再把 hand、piles 与 `card_preview` 全部切换到新 resolver，保留现有 fallback 顺序作为兜底。
3. 补充针对 `TRUE_GRIT`、升级预览与 pile descriptions 的回归测试。
4. 最后做一次 live 验证，确认导出的 `description` 与游戏 UI 一致，且 diagnostics 只出现在日志中。

若新路径在真实运行时出现兼容性问题，可临时回退到旧的 `RenderedDescription` / 模板链路，因为公开 schema 不变，回滚成本较低。

## Open Questions

- `GetDescriptionForPile(...)` 在所有已支持 pile 上是否都要求非空 target，还是允许空 target 安全工作。
- 某些奖励或特殊选牌窗口中的 `card_preview` 是否需要单独的 preview mode，而不能简单复用 pile 语义。
