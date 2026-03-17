## ADDED Requirements

### Requirement: Shop bridge MUST 以轻量动作引用导出商店合法操作
系统 MUST 将商店 legal actions 与 `/apply` 的公共动作协议收敛为“执行锚点 + 必要上下文”。对于购买卡牌、购买遗物、购买药水与移牌服务，动作 `params` 与 metadata MUST 以 `offer_id`、`offer_index`、`kind`、`price`、`canonical_id` 或等效稳定锚点为主；snapshot MUST 作为商品详情的主来源。公共动作协议 MUST NOT 默认重复复制完整 `shop_offer`、`card_preview`、`relic_preview` 或 `potion_preview` 结构。

#### Scenario: 购买动作只保留执行锚点和必要上下文
- **WHEN** bridge 在商店主界面生成某个购买动作
- **THEN** 该动作的 `params` 与 metadata MUST 足以重新定位目标商品并执行购买
- **THEN** 动作结构 MUST NOT 再复制完整商品详情，调用方应通过 `snapshot.metadata.shop_offers[]` 读取商品事实

#### Scenario: `/apply` 仍可基于轻量动作安全校验目标
- **WHEN** 外部调用方提交一个引用 `offer_id` 或等效锚点的商店动作
- **THEN** bridge MUST 能在执行前重新解析当前商店窗口并确认该锚点仍指向原目标
- **THEN** 若目标已变化、已售出或索引漂移，bridge MUST 返回明确拒绝，而不是要求客户端依赖冗余 preview 再次比对

### Requirement: Shop bridge MUST 为用户向动作导出规范化可读标签
系统 MUST 为 `leave_shop` 与其他商店动作提供规范化、可读的公共 label 与参数语义。用户向动作字段 MUST 反映“购买什么”或“离开商店”等决策语义，而不是底层控件名、反射来源或重复拼接的展示文本。

#### Scenario: 离店动作使用规范化公共语义
- **WHEN** bridge 导出离开商店动作
- **THEN** 该动作的 `label`、`params` 与 metadata MUST 表达“离开商店”或等效用户向语义
- **THEN** 公共动作字段 MUST NOT 以 `BackButton` 或等效内部控件名作为主要内容

#### Scenario: 动作 metadata 不重复承载整份商品描述
- **WHEN** bridge 为某个商店动作提供附加 metadata 以支持 trace 或 HUD
- **THEN** metadata MUST 只保留少量动作上下文，例如 `offer_name`、`price` 或 `offer_kind`
- **THEN** metadata MUST NOT 与 snapshot 重复承载整份商品描述、glossary 列表或多层 preview 对象
