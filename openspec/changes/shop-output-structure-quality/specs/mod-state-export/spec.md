## ADDED Requirements

### Requirement: Mod MUST 以 canonical offer 结构导出商店快照
系统 MUST 将 `snapshot.metadata.shop_offers` 作为商店商品与服务事实的唯一 canonical 列表。每个 `shop_offer` MUST 使用统一公共字段表达决策必需信息，至少包含 `offer_id`、`kind`、`name`、`price`、`purchasable`、`unavailable_reason`、`description`、`glossary` 与 `canonical_id` 或等效稳定标识。商店卡牌、遗物、药水与服务项 MAY 追加少量类型特有字段，但公共 schema MUST NOT 再以深层 `card`、`relic`、`potion` preview 复制一套同义详情。

#### Scenario: 商店卡牌与服务项共享统一公共字段
- **WHEN** 商店快照同时包含卡牌、遗物、药水与移牌服务
- **THEN** `snapshot.metadata.shop_offers[]` 中的每个对象 MUST 使用一致的公共字段表达名称、价格、可购买性与说明文本
- **THEN** 调用方 MUST 能仅基于 `shop_offers[]` 完成商品浏览，而不需要再解析额外嵌套 preview 才能获得同义信息

#### Scenario: 不可购买对象仍以稳定 canonical 结构导出
- **WHEN** 某个商品或服务因金币不足、药水槽已满或一次性服务已使用而不可购买
- **THEN** 对应 `shop_offer` MUST 继续出现在 `shop_offers[]` 中
- **THEN** 该对象 MUST 通过 `purchasable=false` 与 `unavailable_reason` 或等效字段表达当前限制，而不是退化为缺失对象或不透明文本

### Requirement: Mod MUST 让商店公共字段面向 agent 决策而非底层 UI 反射
系统 MUST 保证商店快照中的用户向字段使用规范化、可读的公共语义，而不是直接暴露底层 UI 节点名、反射字段名或调试导向值。定位商店识别问题所需的 detection source、节点路径或 fallback 细节 MAY 进入日志或受控调试 metadata，但 MUST NOT 干扰 `shop_offers[]` 的主消费路径。

#### Scenario: 商店快照不暴露底层 UI 名作为公共标签
- **WHEN** mod 从商店 UI 中提取离店按钮、服务标题或商品标签
- **THEN** 对外导出的 `name`、`description`、`label` 或等效公共字段 MUST 使用用户可理解文本
- **THEN** 公共 schema MUST NOT 直接暴露 `BackButton`、节点路径或等效内部命名作为主要决策字段

#### Scenario: 诊断细节留在日志而不是污染主 schema
- **WHEN** 某个 shop offer 需要依赖 fallback 或反射路径才能完成导出
- **THEN** mod MAY 记录诊断日志或受控调试信息
- **THEN** `snapshot.metadata.shop_offers[]` 的主结构 MUST 仍保持精简稳定，不得为排障目的复制大量内部实现细节
