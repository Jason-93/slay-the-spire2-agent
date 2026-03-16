## ADDED Requirements

### Requirement: Mod MUST 导出 shop phase 的统一状态快照
系统 MUST 在玩家进入商店时识别 shop 决策窗口，并导出 `phase=shop` 的结构化 snapshot。该快照 MUST 包含商店窗口元数据、玩家当前金币、可购买商品 / 服务摘要，以及当前是否可以离开商店等最小决策事实。

#### Scenario: 玩家进入商店主界面
- **WHEN** 玩家到达商店并请求当前 snapshot
- **THEN** mod MUST 返回 `phase=shop`
- **THEN** snapshot metadata MUST 标识 `window_kind=shop_main` 或等效 shop 窗口语义

#### Scenario: 商店快照包含结构化商品信息
- **WHEN** 商店当前可展示卡牌、遗物、药水或移牌服务
- **THEN** snapshot MUST 导出结构化 shop offers，而不是仅返回裸文本列表
- **THEN** 每个 offer MUST 至少包含名称、价格、类别、可购买性与可用时的说明文本

### Requirement: Mod MUST 以统一协议导出商店商品与服务对象
系统 MUST 复用现有 cards / relics / potions 的公共说明协议，为商店对象导出一致的结构。对于商店卡牌、遗物、药水与移牌服务，mod MUST 提供可供 agent 直接消费的名称、类型、价格、描述与必要的 glossary 信息，并明确哪些对象当前因金币不足、容量不足或一次性服务限制而不可购买。

#### Scenario: 商店卡牌与遗物沿用统一说明协议
- **WHEN** 商店中存在可购买卡牌或遗物
- **THEN** 对应导出对象 MUST 复用现有 `description` / `glossary` 语义
- **THEN** 外部调用方 MUST 不需要为商店场景重新适配一套完全不同的说明结构

#### Scenario: 不可购买对象仍稳定导出
- **WHEN** 某个商店对象因金币不足、药水位已满或服务已失效而不可购买
- **THEN** 该对象 MUST 仍以稳定结构出现在 snapshot 中
- **THEN** 导出结果 MUST 明确标识其当前不可购买原因或不可购买状态

