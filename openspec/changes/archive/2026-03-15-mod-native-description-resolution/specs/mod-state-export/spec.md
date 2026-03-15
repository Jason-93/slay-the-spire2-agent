## ADDED Requirements

### Requirement: Mod 必须导出单一 canonical description 协议
系统 MUST 在统一状态快照与合法动作元数据中以 `description` 作为唯一 canonical 说明文本字段，并稳定导出 `description_quality`、`description_source` 与 `description_vars` 作为辅助 diagnostics。mod MUST NOT 在公共 schema 中继续保留仅用于历史兼容的重复字段，例如要求调用方在 `description_rendered`、`description_raw` 与 `description` 之间自行判断哪一个可用。若说明中包含 glossary 高亮，`description` MUST 输出为稳定的 markdown 风格强调文本，例如 `**格挡**`。

#### Scenario: snapshot 中的卡牌说明字段可直接消费
- **WHEN** 外部调用方读取 `snapshot.player.hand[]` 中的卡牌对象
- **THEN** 若该卡牌存在说明文本，快照 MUST 直接返回最终可读的 `description`
- **THEN** 若存在可提取的动态变量，快照 MUST 返回 `description_vars`
- **THEN** 调用方 MUST 能仅基于 `description` 与 diagnostics 判断当前说明是已解析、部分解析还是模板回退

#### Scenario: legal action preview 与 snapshot 保持同一说明语义
- **WHEN** bridge 生成 `play_card`、`choose_reward` 或其他带 `card_preview` / `reward_preview` 的合法动作
- **THEN** metadata 中的说明字段 MUST 与当前 `snapshot` 对应对象保持一致语义
- **THEN** 不同导出位置之间 MUST NOT 出现一个已解析、一个仍要求客户端兜底的冲突状态

#### Scenario: glossary 高亮在不同导出位置保持一致
- **WHEN** 某个对象说明中包含 glossary 词条，例如 `格挡`
- **THEN** `snapshot` 与 action preview 中的 `description` MUST 一致使用 `**格挡**` 形式
- **THEN** 调用方 MUST 不需要额外理解游戏富文本标签或再次格式化

### Requirement: Mod 必须为说明解析结果提供稳定扩展点
系统 MUST 允许在不改变基础字段契约的前提下，把相同的说明解析语义扩展到 cards 之外的其他实体，例如 powers、relics、potions 或后续百科对象。新增实体时 MUST 复用相同的质量语义与来源标记，避免每类对象单独定义一套说明字段协议。

#### Scenario: 新实体接入时沿用统一质量语义
- **WHEN** 后续将 relics、potions 或其他可解释对象接入说明导出
- **THEN** 新对象 MUST 继续使用与 cards / powers 一致的 `description`、`description_quality` 与 `description_source` 语义
- **THEN** 外部调用方 MUST 无需为每种实体重新实现一套说明可信度判定逻辑
