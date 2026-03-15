## Context

当前 runtime state 主要围绕“当前窗口能不能做动作”设计，足以支撑基础 bridge 闭环与简单 autoplay，但对战斗理解仍然过于瘦身。以 combat 为例，手牌只稳定暴露 `name/cost/playable`，敌人只稳定暴露 `hp/block/intent`，而对 agent 真正重要的卡牌描述、升级态、目标类型、traits、玩家/敌方 powers、结构化敌方 intent、run-level 规划上下文都没有稳定契约。

与此同时，项目已经进入“从能跑通到能打得更像样”的阶段。后续无论是 richer prompt、规则策略、牌库长期规划，还是外挂怪物/卡牌百科，都要求 snapshot 能承载更多事实层信息，并且为派生语义与静态知识留下稳定锚点。这个变化跨越 mod contracts、runtime reader、Python models、HTTP bridge、LLM policy 摘要与测试体系，属于典型的跨模块 schema 演进。

## Goals / Non-Goals

**Goals:**
- 为 combat snapshot 建立可扩展的 richer schema，优先补齐卡牌描述、升级态、目标类型、traits、结构化 intent 与 powers 等高价值字段。
- 在不破坏现有 autoplay 的前提下，引入 `run_state` 层，逐步承载 `act/floor/room/map` 等整局规划事实。
- 明确区分 runtime facts、派生语义与静态知识锚点；第一阶段只落地前两者中的事实层与少量锚点，不把百科内容直接塞进 live payload。
- 保持协议追加式演进：旧字段继续可用，新字段尽量可选，fixture/live runtime 缺失字段时也能安全退化。
- 让 Python 侧策略层能够直接消费 richer snapshot，为后续更强 agent 留出稳定接口。

**Non-Goals:**
- 本次不直接实现完整牌库长期规划器或路线规划器。
- 本次不内置完整怪物机制百科、卡牌百科或离线知识库，只预留 `canonical_*`/稳定锚点与对接方式。
- 本次不要求一次性补齐所有职业、所有怪物、所有特效字段；优先覆盖当前 Ironclad 战斗闭环中最影响决策质量的字段。
- 本次不重写现有 orchestrator 决策框架，只扩充其可见状态与兼容路径。

## Decisions

### 1. 采用分层 schema：`combat_state` / `run_state` / `metadata`
- 决策：保持当前顶层 snapshot 语义不变，但内部对象按“当前战斗事实”和“整局事实”组织，避免把长期规划字段继续散落在 `metadata` 或临时键中。
- 原因：战斗决策与长期规划的更新频率、来源与稳定性不同；分层后更利于后续引入 `derived_state` 或外挂知识层，而不破坏 bridge 契约。
- 备选方案：继续把新字段平铺到现有 `player/enemies/metadata`。未采用，因为字段会快速失控，也不利于未来版本演进。

### 2. 运行时协议使用追加式、可选字段演进
- 决策：保留现有 `CardView`、`EnemyState`、`PlayerState` 的已存在字段，同时追加 richer 字段；fixture 或 runtime 暂时拿不到的字段允许为 `null`/空集合。
- 原因：当前 Python 侧、trace、fixtures、live scripts 都依赖现有基础字段，直接重构为全新 schema 会放大迁移成本并增加联调风险。
- 备选方案：一次性设计 `v2` 并替换所有旧字段。未采用，因为当前项目更需要快速提升状态质量，而不是协议大迁移。

### 3. 卡牌与敌人对象同时保留实例标识与知识锚点
- 决策：为卡牌、敌人预留 `instance_*_id` 与 `canonical_*_id` 两类标识；前者服务 live 动作与 trace，后者服务未来的百科、统计与长期规划。
- 原因：同名牌、同类怪在运行时需要区分实例，而长期知识必须依赖稳定模板标识，二者不能混用。
- 备选方案：仅保留当前运行时 id 或仅依赖名字。未采用，因为这会阻碍百科与跨战斗统计，也无法稳定处理同名实例。

### 4. 第一阶段优先导出“高价值事实”，不急于内建百科
- 决策：第一阶段重点补齐 `description`、`upgraded`、`target_type`、`traits`、结构化 `intent`、`powers[]`、`run_state.act/floor/room/map` 等；百科解释、怪物脚本与策略标签留到后续能力处理。
- 原因：当前大模型“打得蠢”的主因是看不清局面，而不是完全没有先验知识。先补事实层，能立刻提升决策质量，也为之后百科接入提供可靠底座。
- 备选方案：直接外挂静态卡牌/怪物数据库。未采用，因为 live runtime 与静态知识先天会偏离，且没有稳定 `canonical_id` 前很难安全对齐。

### 5. intent 采用结构化字段，而不是只保留单个字符串
- 决策：在保留 `intent_raw`/兼容 `intent` 的同时，补充 `intent_type`、`intent_damage`、`intent_hits`、`intent_block`、`intent_effects[]` 等结构化字段；若某个子字段拿不到，允许为空。
- 原因：单个 `intent` 字符串对 LLM 和测试都过于脆弱，难以区分攻击、多段、加格挡、上 debuff 等战术含义。
- 备选方案：继续依赖原始文本或 `unknown`。未采用，因为这正是当前战斗决策质量差的主要瓶颈之一。

### 6. Python 侧 LLM 摘要保留压缩视图，但必须包含 richer 字段
- 决策：`ChatCompletionsPolicy` 继续发送裁剪后的 snapshot，而不是完整原始对象；但裁剪逻辑必须把新引入的高价值字段带上，并对缺失字段作稳定归一化。
- 原因：完整 payload 很快会膨胀，既增加 token 成本，也不利于小模型对关键信息聚焦。
- 备选方案：把所有 runtime 字段原样塞给模型。未采用，因为这会显著增加噪声与上下文长度。

## Risks / Trade-offs

- [Runtime 反射字段名不稳定] → 先从已有 `RuntimeTextResolver`、`ResolveCardCost`、现有 hand/enemy 读取路径扩展；对 `powers`、结构化 intent 做小范围 spike，并在缺失时安全回退为空。
- [schema 追加后 payload 体积上升] → Python 侧对 LLM 维持压缩摘要；trace 保留完整状态，prompt 只带决策所需子集。
- [fixture 与 live runtime 能力不一致] → 先更新 fixture contracts，再补 live validation；所有新增字段定义为可选，确保 fixture/live 差异不会直接打断 autoplay。
- [过早设计百科锚点导致过度工程] → 只预留 `canonical_*` 与最小知识引用接口，不在本 change 中引入真正的 catalog 内容。
- [旧调用方兼容性受影响] → 不删除旧字段，不改变现有基础字段语义；新逻辑采用 append-only 与默认值策略。

## Migration Plan

1. 先扩展 mod contracts 与 runtime reader，使 richer card/enemy/player/run fields 能在 fixture 和 live runtime 中导出。
2. 更新 Python models、HTTP bridge 解析与 tests，确保 richer 字段可以被正常序列化、反序列化与 trace。
3. 更新 LLM snapshot 摘要与相关策略测试，确保 richer fields 已进入模型输入，但缺失字段时仍可正常运行。
4. 执行 fixture/unit/live validation，记录至少一次 richer state 导出质量样例。
5. 后续若需要真正引入百科或规划层，在本 schema 基础上追加 `derived_state`/catalog，而不是再次重构 runtime facts。

## Open Questions

- `powers[]` 在 STS2 runtime 中的稳定反射入口名称是什么，是否需要按玩家/敌人分别适配？
- 结构化 intent 能否直接从 runtime 读到数值字段，还是需要结合文本解析做保守推断？
- `canonical_card_id` / `canonical_enemy_id` 是否能从现有 runtime object 安全提取，还是第一阶段先只落空并预留字段？
- `run_state.master_deck` 是否适合在本 change 一并落地，还是先只做 `act/floor/room/map` 的最小规划上下文？
