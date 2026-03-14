## MODIFIED Requirements

### Requirement: live snapshot 与 actions 必须导出可读的用户向文本
系统 MUST 对 in-game runtime bridge 中的主要文本字段执行统一解析，至少覆盖 relics、potions、rewards、map nodes、cards、powers、enemies 与 action labels。当字段背后存在 `LocString`、动态变量或类似本地化容器时，bridge MUST 在 mod 端直接输出面向玩家的最终可读文本，而不得把模板替换职责下放给 Python client、policy 或其他外部调用方。对于带说明的实体，对外协议中的 `description` MUST 作为唯一 canonical 文本字段；bridge MUST NOT 再要求调用方在 `description`、`description_rendered`、`description_raw` 之间自行挑选真实语义。若原始文本包含 `[gold]格挡[/gold]` 这类 glossary 富文本高亮，bridge MUST 在对外 `description` 中将其规范化为 `**格挡**` 这类稳定标记。

#### Scenario: 基础手牌说明由 mod 端直接解析为 canonical description
- **WHEN** 玩家手牌中的 `Strike`、`Defend` 等卡牌说明包含 `{Damage:diff()}`、`{Block:diff()}` 或等效模板占位符
- **THEN** `snapshot.player.hand[].description` MUST 由 mod 端直接导出最终可读文本
- **THEN** 对应的 `actions[].metadata.card_preview.description` MUST 与快照语义一致
- **THEN** 外部 client MUST NOT 需要再次执行模板替换或在多个说明字段间自行兜底

#### Scenario: power 说明由 mod 端统一给出可消费语义
- **WHEN** 玩家或敌人 powers 的说明文本依赖 runtime 数值、富文本标签或本地化变量
- **THEN** `snapshot.player.powers[]` 与 `snapshot.enemies[].powers[]` MUST 直接导出可读的 `description`
- **THEN** bridge MUST 同时保留结构化数值来源，便于外部 agent 判断说明可信度

#### Scenario: glossary 高亮以 markdown 风格导出
- **WHEN** 某条说明文本中包含 glossary 词条高亮，例如 `[gold]格挡[/gold]`
- **THEN** 对外 `description` MUST 导出为 `**格挡**`
- **THEN** bridge MUST NOT 在公共文本字段中继续暴露游戏内部富文本标签

### Requirement: 文本解析失败时必须提供可诊断的降级信息
系统 MUST 在文本解析失败、只能拿到模板、或仅能部分解析时保持 fail-safe，并在 metadata 或等效 diagnostics 结构中暴露足够的调试信息。bridge MUST 将“最终可读文本”“质量等级”“解析来源”“变量表”作为服务端语义统一导出，而不是让客户端通过猜测字符串内容来判断是否仍含占位符。bridge MAY 在 diagnostics 中保留调试原文，但 MUST NOT 依赖公共 schema 中的重复兼容文本字段。bridge MUST NOT 因为个别文本字段解析失败而使整个 `snapshot` 或 `actions` 构建失败。

#### Scenario: 仍含模板占位符时导出 template_fallback 诊断
- **WHEN** 某张卡牌或 power 的说明文本在 mod 端仍无法完全解析，最终 `description` 仍保留模板占位符
- **THEN** 对应对象 MUST 导出 `description_quality="template_fallback"` 或等效稳定值
- **THEN** 对应对象 MUST 导出 `description_source` 与可诊断的 `description_vars`
- **THEN** 外部 client MUST 能仅通过这些服务端字段识别当前文本不可完全信任，而不需要自行扫描模板语法

#### Scenario: 解析失败时快照仍可稳定返回
- **WHEN** 某个 runtime 对象的文本字段无法通过本地化、动态变量或约定字段解析
- **THEN** bridge MUST 仍然返回可序列化的 `snapshot` 或 `actions` 响应
- **THEN** diagnostics MUST 指出该字段使用了 fallback、partial 或 unresolved 语义
- **THEN** 面向 agent 的主字段仍 MUST 保持稳定可读，不得退化为对象类名或不可序列化值
