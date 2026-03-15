## MODIFIED Requirements

### Requirement: live snapshot 与 actions 必须导出可读的用户向文本
系统 MUST 对 in-game runtime bridge 中的主要文本字段执行统一解析，至少覆盖 relics、potions、rewards、map nodes、cards、powers、enemies 与 action labels。当字段背后存在 `LocString`、动态变量或类似本地化容器时，bridge MUST 在 mod 端直接输出面向玩家的最终可读文本，而不得把模板替换职责下放给 Python client、policy 或其他外部调用方。对于 cards，当 runtime 暴露 `GetDescriptionForPile(...)`、`GetDescriptionForUpgradePreview()` 或等效最终描述 API 时，bridge MUST 优先使用这些 API 生成 canonical `description`，并根据 hand / draw / discard / exhaust / preview 的上下文选择对应的 pile 或 preview 语义；只有在这些最终描述入口不可用时，bridge 才能退回 `RenderedDescription`、`RenderedText` 或模板 fallback。对于带说明的实体，对外协议中的 `description` MUST 作为唯一 canonical 文本字段；bridge MUST NOT 再要求调用方在 `description`、`description_rendered`、`description_raw` 之间自行挑选真实语义。若原始文本包含 `[gold]格挡[/gold]` 这类 glossary 富文本高亮，bridge MUST 在对外 `description` 中将其规范化为 `**格挡**` 这类稳定标记。

#### Scenario: 手牌说明优先使用游戏最终描述 API
- **WHEN** 玩家手牌中的某张卡牌存在可调用的 `GetDescriptionForPile(...)` 或等效最终描述入口
- **THEN** `snapshot.player.hand[].description` MUST 优先来自该最终描述 API，而不是 bridge 侧模板替换
- **THEN** 对应文本 MUST 与游戏 UI 当前展示的语义一致或等效一致

#### Scenario: pile cards 与 preview 使用匹配上下文的最终描述
- **WHEN** bridge 导出 `draw_pile_cards`、`discard_pile_cards`、`exhaust_pile_cards` 或 `actions[].metadata.card_preview`
- **THEN** bridge MUST 根据所在 pile 或 preview 上下文选择匹配的最终描述入口
- **THEN** `card_preview` 在升级预览语义可用时 MUST 优先使用 `GetDescriptionForUpgradePreview()` 或等效 API

#### Scenario: 最终描述入口缺失时仍可回退
- **WHEN** 某张卡牌当前无法稳定调用最终描述 API
- **THEN** bridge MAY 回退到 `RenderedDescription`、`RenderedText` 或模板 fallback
- **THEN** 外部 client MUST 仍只消费单个 canonical `description`，不需要理解内部回退顺序

### Requirement: 文本解析失败时必须提供可诊断的降级信息
系统 MUST 在文本解析失败、只能拿到模板、或仅能部分解析时保持 fail-safe，并在日志、内部 metadata 或等效 diagnostics 结构中暴露足够的调试信息。对于 cards，diagnostics MUST 至少能够定位对象路径、`card_id` 或 `canonical_card_id`、description context、选择的 source 与失败阶段。bridge MUST 将“最终可读文本”的公开语义继续收敛到单个 `description` 字段，而不是让客户端通过额外公开 schema 猜测哪些文本仍含占位符。bridge MAY 在日志中保留调试原文，但 MUST NOT 因为个别文本字段解析失败而使整个 `snapshot` 或 `actions` 构建失败。

#### Scenario: 最终描述失败时记录日志并安全回退
- **WHEN** 某张卡牌调用最终描述 API 失败、返回空文本或仍残留模板 DSL
- **THEN** bridge MUST 记录包含 card 标识、上下文与 fallback 阶段的 warning 或等效 diagnostics
- **THEN** 对外 `snapshot` 或 `actions` MUST 仍返回可序列化结果

#### Scenario: diagnostics 不再通过公开说明字段泄漏给客户端
- **WHEN** bridge 需要暴露 description 的解析来源、变量或失败原因
- **THEN** 这些信息 MUST 进入日志、内部 diagnostics 或等效排障通道
- **THEN** 公共 schema MUST NOT 重新引入 `description_quality`、`description_source`、`description_vars` 或等效公开字段

### Requirement: live runtime bridge 必须将手牌描述绑定到当前卡牌实例的动态值
系统 MUST 在真实 STS2 进程内，优先基于当前卡牌实例与当前 description context 解析卡牌说明，而不是长期依赖模板文本或静态定义。对于同名重复手牌，bridge MUST 以实例级语义读取数值并生成 description，确保导出的文本与该 `card_id` 所代表的当前卡牌一致。对于 pile cards，bridge MUST 将对应 pile context 传入最终描述入口；对于 preview，bridge MUST 在可用时使用升级预览或等效 preview context，而不是直接复用 hand description。若 runtime bridge 无法从当前实例或上下文中稳定读取最终文本，bridge MUST 安全回退，但 MUST NOT 把失败卡牌扩散为整个 live snapshot 的构建失败。

#### Scenario: 同名重复手牌仍按实例级语义导出 description
- **WHEN** 玩家手牌中同时存在多张同名卡牌，且其中部分实例因升级、临时效果或其他 runtime 状态产生不同说明语义
- **THEN** bridge MUST 按实例读取并导出每张卡牌的 `description`
- **THEN** 每张卡牌导出的文本 MUST 与其自身 `card_id` 对应，而不是共享静态模板

#### Scenario: pile 与 preview 不直接复用 hand description
- **WHEN** 同一张卡牌同时以 pile card、hand card 或 `card_preview` 的形式被导出
- **THEN** bridge MUST 根据各自 context 生成 description
- **THEN** bridge MUST NOT 无条件把 hand description 直接复制到 pile 或 preview
