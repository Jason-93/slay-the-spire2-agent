## Context

当前商店场景已经能在 live runtime 中稳定识别 `phase=shop`，并支持购买卡牌、遗物、药水、移牌服务以及离开商店。但在对外协议层，商店输出仍保留了较重的“实现痕迹”：`snapshot.metadata.shop_offers` 中同时携带公共字段和按类型嵌套的 preview，对应 action metadata 又再复制一遍完整对象，导致字段重复、层级偏深、不同消费方很难快速判断“哪一层才是 canonical 信息”。此外，像 `BackButton` 这类 UI 内部标签曾直接暴露给外部，也说明当前结构仍过于贴近底层节点，而不是面向 agent 决策。 

这个变更需要跨 mod 导出、bridge action metadata、fixture 校验与 Python 消费层一起收敛协议，因此适合先明确结构设计，再进入实现。

## Goals / Non-Goals

**Goals:**
- 定义商店商品的最小 canonical 输出结构，确保 `shop_offers` 可直接被 agent / LLM 消费。
- 减少 snapshot 与 actions 间的重复嵌套字段，只保留决策必需信息与稳定锚点。
- 明确服务项、不可购买原因、离店动作等边界情况的统一语义。
- 为后续扩展更多商店对象或 UI 变体保留稳定公共协议，而不是继续堆叠特例字段。

**Non-Goals:**
- 本次不改变商店识别、真实购买执行、价格计算等基础能力。
- 本次不引入新的商店专用 HTTP 端点。
- 本次不解决所有卡牌/遗物/药水 description 本身的内容质量问题，只处理结构质量与字段语义。

## Decisions

### 1. 以 `shop_offers[]` 作为商店事实的唯一 canonical 列表
- 选择：把 `snapshot.metadata.shop_offers` 定义为商店商品事实的唯一主视图，要求每个 offer 自带通用字段（如 `offer_id`、`kind`、`name`、`price`、`purchasable`、`unavailable_reason`、`description`、`glossary`、`canonical_id`），并按需追加少量类型特有字段。
- 原因：agent 在做商店决策时首先需要“看全局商品列表”；若 snapshot 已经完整，actions 就不应重复携带整份商品信息。
- 备选：继续在 `shop_offer.card` / `shop_offer.relic` / `shop_offer.potion` 下复制一套 preview。放弃原因是重复严重，且调用方要额外判断嵌套层级。

### 2. action metadata 改为“轻量引用 + 少量执行上下文”
- 选择：商店 legal action 的 `params` 与 metadata 只保留执行锚点（如 `offer_id`、`offer_index`、`price`、必要 canonical id）与极少量动作特有上下文；不再默认复制完整 `shop_offer` 与 `card_preview`/`relic_preview`/`potion_preview`。
- 原因：snapshot 已承载完整商店事实，action 的职责应是“怎么执行”，而不是再次充当商品详情容器。
- 备选：维持当前 snapshot/actions 各自重复一份完整结构。放弃原因是容易产生 drift，也让 trace 与 LLM prompt 冗长。

### 3. 规范可读标签，禁止暴露底层 UI 内部名作为用户向字段
- 选择：对 `leave_shop`、服务项标题等字段建立用户向规范化文本；内部节点名只进入日志或内部 metadata，不进入公共 label/description 字段。
- 原因：`BackButton`、`MerchantButton` 之类值不适合作为 agent 的决策上下文，会污染 prompt 与调试面板。
- 备选：保留底层 label 原样导出。放弃原因是与“公共协议面向决策而非面向反射排障”的方向冲突。

### 4. 诊断与反射细节留在日志，不进入公共 schema
- 选择：像 detection source、节点类型、反射 fallback 之类信息默认不进入核心 offer 结构；若仍需保留，也只放在可选 metadata 且避免影响主消费路径。
- 原因：这些信息对定位 live 缺口有价值，但不应干扰上层 agent 的稳定字段理解。
- 备选：继续把大量检测来源直接暴露在每个 offer/action 中。放弃原因是噪音高、长期兼容成本大。

## Risks / Trade-offs

- [客户端已依赖当前冗余字段] → 通过 spec 明确 canonical 新结构，并在实现阶段同步更新 Python 消费层与验证脚本。
- [过度裁剪后丢失调试信息] → 将诊断移到日志与可选调试 metadata，而不是完全删除排障入口。
- [不同商品类型需要的特有字段不完全一致] → 先定义最小公共字段，再为少数类型保留受控的可选扩展字段。
- [archive 后旧 spec 语义与新结构衔接不清] → 通过 delta specs 明确 snapshot 与 action metadata 的 canonical 语义，避免实现层自行解释。
