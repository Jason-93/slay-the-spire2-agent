## Context

当前工程已经具备 `combat`、`reward`、`map`、`event` 等窗口的状态导出、合法动作生成与 live autoplay 编排能力，但商店仍是整局自动化中的明显断点。商店场景同时涉及多类对象（可购买卡牌、遗物、药水、移除卡牌服务、离开按钮）、多种资源约束（金钱、药水栏、牌组规划）以及购买后窗口结构变化，因此不能只复用现有 reward/map 协议，需要补一层 shop 专用的窗口模型与动作语义。

约束包括：必须优先从 runtime 读取真实商店状态，不能把商店商品表写死在 mod 中；公共协议要尽量精简，供 LLM 直接消费；`/apply` 仍需遵守 stale-action / 窗口漂移保护；autoplay 默认不能在 shop 里无约束乱买，必须保留 `halt` / `safe-default` / `llm` 的模式边界。

## Goals / Non-Goals

**Goals:**
- 为 `shop` phase 提供稳定的 snapshot metadata 与 legal actions。
- 统一导出 shop 商品/服务信息，至少覆盖名称、价格、类别、可购买性与必要说明文本。
- 支持真实执行购买卡牌、购买遗物、购买药水、移除卡牌与离开商店动作。
- 让 orchestrator 能像处理 `event` / `reward` 一样处理 shop，并在窗口漂移时安全恢复。

**Non-Goals:**
- 本次不做复杂的商店长期经济规划或全局牌库构筑策略。
- 本次不尝试覆盖未来第三方 mod 自定义商店 UI 的所有变体。
- 本次不引入新的外部依赖或单独的 shop 专属 HTTP 端点。

## Decisions

### 1. 使用独立 `shop` phase，而不是把商店伪装成 `event` 或 `reward`
- 选择：在 mod 端显式识别商店窗口，并导出 `phase=shop`、`window_kind=shop_main` / 等效 shop metadata。
- 原因：商店既不是一次性 reward，也不是普通 event；强行复用会让 policy 误解“购买”和“跳过”的语义，增加 transition 误判。
- 备选：继续塞进 `event` 或 `reward`。放弃原因是字段语义混乱，后续扩展移牌、药水容量校验时会越来越难维护。

### 2. 商品与服务统一抽象为 `shop_offers[] + actions[]`
- 选择：snapshot 中导出结构化 `shop_offers` / shop metadata，actions 中则按真实可执行项拆成 `buy_shop_card`、`buy_shop_relic`、`buy_shop_potion`、`purge_shop_card`、`leave_shop`。
- 原因：LLM 需要先看全量商店事实，再在 legal actions 里做选择；只导出动作不导出商品上下文会降低可解释性。
- 备选：只保留动作 metadata。放弃原因是商品解释会分散在各 action 中，协议重复且难做 HUD / trace 展示。

### 3. 优先从 runtime hover / 实例对象提取说明，不维护手写商店词条表
- 选择：卡牌、遗物、药水的名称、价格、说明、glossary 沿用现有 runtime 提取链路，shop 只负责组织成商店视图。
- 原因：能复用现有 description / glossary 体系，也更容易泛化到后续游戏更新。
- 备选：在商店场景单独做一套商品说明表。放弃原因是重复维护且容易与真实游戏文本漂移。

### 4. orchestrator 为 shop 引入显式模式，而不是默认自动购买
- 选择：新增 `shop_mode`，至少支持 `halt`、`safe-default`、`llm`；默认 `halt`。
- 原因：商店决策成本高、不可逆，默认自动买东西风险明显高于 reward / map。
- 备选：默认跟随 `event_mode` 或 `reward_mode`。放弃原因是商店的资源消耗与长期规划语义不同，用户需要单独控制。

### 5. `/apply` 的商店动作继续复用现有 stale-window 校验模型
- 选择：生成商店 action 时写入稳定锚点（offer index / runtime node / 价格 / 名称等），执行前重新解析当前 shop 窗口并校验目标仍匹配。
- 原因：商店购买后剩余商品布局和价格可能变化，不做校验容易点错或重复消费。
- 备选：只按按钮序号直接点击。放弃原因是购买后索引漂移风险高。

## Risks / Trade-offs

- [商店 UI 识别依赖 runtime 结构，版本更新后可能漂移] → 通过 fixture + live validation 固化最小识别面，并在 metadata / 日志里记录 detection source。
- [购买后窗口快速重排，容易触发 stale_action] → 对商店动作沿用当前 gate / recovery 逻辑，并优先使用稳定锚点重观测。
- [LLM 在商店中过度消费金币] → 默认 `shop_mode=halt`，`safe-default` 仅允许“离开商店”或极保守动作，真实购买交给 `llm` 模式。
- [商品说明抽取不完整会降低决策质量] → 复用现有 description/glossary 提取链路，缺口通过日志与 validation artifacts 排查，而不是在公共协议里堆 diagnostics。
