## ADDED Requirements

### Requirement: Shop bridge MUST 输出带语义单位的商品与服务说明
系统 MUST 为商店中的卡牌、遗物、药水与服务项输出对 agent 可直接理解的说明文本。若游戏运行时文本遗漏了数值单位、只剩图标路径或仅保留裸数字，bridge MUST 结合变量来源与商店上下文补全为带明确语义的可读说明，而不是继续暴露歧义文本。

#### Scenario: 商店移除服务的价格增幅只剩裸数字
- **WHEN** 商店移除服务的运行时说明包含 `Amount`、`PriceIncrease` 或等效价格增量变量，且游戏文本只渲染为 `增加25。`
- **THEN** snapshot MUST 输出带价格语义的完整说明，例如 `增加25金币。`
- **THEN** bridge MUST 优先依据运行时对象或动态方法解析该数值，而不是只按固定中文文案替换

#### Scenario: 商店卡牌说明把能量收益渲染成图标路径
- **WHEN** 商店卡牌的已渲染说明包含能量图标资源路径或等效非文本占位
- **THEN** snapshot MUST 将其归一化为 agent 可读的文本，例如 `获得2能量。`
- **THEN** bridge MUST 保留其他已正确渲染的描述内容与 glossary 信息
