# in-game-runtime-bridge Specification

## Purpose
定义 STS2 bridge 作为真实游戏内 mod 运行时的状态导出约束，确保 live `health`、`snapshot`、`actions` 在受控线程上下文中稳定可用。
## Requirements
### Requirement: 游戏内 mod 必须暴露 live runtime bridge
系统 MUST 能以真实 STS2 mod 的形式运行在游戏进程内，并通过 loopback bridge 对外暴露 live `health`、`snapshot`、`actions` 能力。该 bridge SHALL 复用统一的决策窗口模型，并在游戏内无活动 run、运行时未就绪或版本不兼容时返回可诊断状态，而不是崩溃或阻塞游戏。对于战斗结束后的奖励窗口，bridge MUST 稳定识别并导出 `phase = reward`，不得在 reward 已显示时错误回落到 `combat` 或继续伪造玩家战斗动作。

#### Scenario: 游戏内 bridge 成功附着到活动 run
- **WHEN** STS2 已启动、mod 已加载且玩家进入一局活动 run
- **THEN** `health` MUST 返回可识别的 in-game runtime 模式
- **THEN** `snapshot` MUST 返回当前决策窗口的 live 状态
- **THEN** `actions` MUST 返回与该窗口对应的 legal actions

#### Scenario: 游戏已启动但当前没有活动 run
- **WHEN** STS2 已启动且 mod 已加载，但玩家仍在主菜单或尚未进入 run
- **THEN** `health` MUST 返回 bridge 已加载但 run 未就绪的状态说明
- **THEN** `snapshot` MUST NOT 伪造战斗或地图数据
- **THEN** bridge MUST 保持可继续服务，直到 run 就绪

#### Scenario: reward 界面显示时导出 reward phase
- **WHEN** 玩家已经结束战斗并进入奖励界面，且 runtime 可观察到 reward screen、reward buttons 或等效 reward 信号
- **THEN** `snapshot.phase` MUST 返回 `reward`
- **THEN** `snapshot.rewards` MUST 返回当前可见奖励文本
- **THEN** `actions` MUST 返回 `choose_reward`、`skip_reward` 或等效 reward 合法动作，而不是 `end_turn`

#### Scenario: 战斗结束过渡态不得伪装为玩家战斗回合
- **WHEN** 当前战斗敌人已经全部清空，但 reward UI 仍在挂载或切换中
- **THEN** bridge MUST 优先进入 reward 识别或保守降级路径
- **THEN** bridge MUST NOT 持续导出 `window_kind = player_turn` 与可重复提交的 `end_turn` 作为主要对外语义

#### Scenario: runtime 读取失败时保持 fail-safe
- **WHEN** 反射读取、游戏节点发现或窗口识别过程中发生异常
- **THEN** bridge MUST 返回结构化错误或降级状态
- **THEN** mod MUST NOT 使游戏进程崩溃
- **THEN** 后续请求 MUST 仍可继续探测健康状态

### Requirement: bridge 必须在受控线程上下文导出 live state
系统 MUST 在游戏主线程或等效的受控调度点读取、刷新和导出游戏状态，不得在任意 HTTP 请求线程直接对 STS2 或 Godot 对象做不安全访问。若当前请求无法立即读取 live state，bridge MUST 返回明确失败语义或最近一次可接受的快照策略说明。

#### Scenario: HTTP 请求与游戏主线程并发发生
- **WHEN** 外部进程在游戏运行过程中并发请求 `snapshot` 或 `actions`
- **THEN** bridge MUST 通过受控调度或快照缓存来读取状态
- **THEN** bridge MUST NOT 直接在 HTTP 线程上执行不安全的游戏对象访问

#### Scenario: 状态版本在 live 更新后推进
- **WHEN** 当前决策窗口内容发生变化，例如手牌、敌人、奖励或可选地图点变化
- **THEN** 导出的 `state_version` MUST 对应推进
- **THEN** 新的 `decision_id` MUST 反映最新的 live 决策上下文

### Requirement: 手牌卡牌必须导出稳定且可区分的运行时 card_id
系统 MUST 为 `snapshot.player.hand` 中的每一张手牌导出稳定的 `card_id`，并确保同名、同费用、同升级状态的重复手牌在同一决策窗口内仍然可以被区分。该 `card_id` MUST 与当前 live 牌实例保持一致，并 SHALL 被对应的 `play_card` legal action 通过 `params.card_id` 直接引用。

#### Scenario: 重复手牌仍然拥有不同 card_id
- **WHEN** 玩家当前手牌中同时存在两张或更多张表面属性相同的卡牌
- **THEN** `/snapshot.player.hand` 中每张手牌的 `card_id` MUST 彼此不同
- **THEN** 卡牌的 `name` MAY 相同，但 bridge MUST 仍能稳定区分这些实例

#### Scenario: legal actions 与 hand 中的 card_id 一一对应
- **WHEN** bridge 生成当前窗口的 `play_card` legal actions
- **THEN** 每个 `play_card` action 的 `params.card_id` MUST 对应到 `snapshot.player.hand` 中的一张具体手牌
- **THEN** `action_id` MUST 反映该 `card_id` 所代表的实例级差异

### Requirement: live snapshot 与 actions 必须导出可读的用户向文本
系统 MUST 对 in-game runtime bridge 中的主要文本字段执行统一解析，至少覆盖 relics、potions、rewards、map nodes、cards、powers、enemies 与 action labels。当字段背后存在 `LocString`、动态变量或类似本地化容器时，bridge MUST 在 mod 端直接输出面向玩家的最终可读文本，而不得把模板替换职责下放给 Python client、policy 或其他外部调用方。对于 cards，当 runtime 暴露 `GetDescriptionForPile(...)`、`GetDescriptionForUpgradePreview()` 或等效最终描述 API 时，bridge MUST 优先使用这些 API 生成 canonical `description`，并根据 hand / draw / discard / exhaust / preview 的上下文选择对应的 pile 或 preview 语义；只有在这些最终描述入口不可用时，bridge 才能退回 `RenderedDescription`、`RenderedText` 或模板 fallback。对于 relics，bridge MUST 不再只导出名称，而是输出结构化 relic 对象，并优先从 relic 模型、hover tip、`Description`、`SmartDescription`、localization 或等效 runtime 文本来源解析 canonical `description`。对于带说明的实体，对外协议中的 `description` MUST 作为唯一 canonical 文本字段；bridge MUST NOT 再要求调用方在 `description`、`description_rendered`、`description_raw` 之间自行挑选真实语义。若原始文本包含 `[gold]格挡[/gold]` 这类 glossary 富文本高亮，bridge MUST 在对外 `description` 中将其规范化为 `**格挡**` 这类稳定标记。

#### Scenario: relic 说明由 mod 端直接导出为 canonical description
- **WHEN** 玩家持有的某个 relic 在 runtime 中存在可读 description、hover tip 或等效文本来源
- **THEN** `snapshot.player.relics[]` MUST 直接导出该 relic 的 canonical `description`
- **THEN** 外部 client MUST NOT 需要再根据 relic 名称查表或自行渲染说明文本

#### Scenario: relic 暂时无说明时仍返回结构化对象
- **WHEN** 某个 relic 当前只能从 runtime 中读取到名称，拿不到稳定的 description
- **THEN** bridge MUST 仍返回该 relic 的结构化对象
- **THEN** bridge MUST 保持整个 `snapshot` 成功，而不是因单个 relic 文本失败中断响应

### Requirement: 文本解析失败时必须提供可诊断的降级信息
系统 MUST 在文本解析失败、只能拿到模板、或仅能部分解析时保持 fail-safe，并在日志、内部 metadata 或等效 diagnostics 结构中暴露足够的调试信息。对于 cards，diagnostics MUST 至少能够定位对象路径、`card_id` 或 `canonical_card_id`、description context、选择的 source 与失败阶段。对于 relics，diagnostics MUST 至少能够定位 relic 名称或 `canonical_relic_id`、对象路径与 description 的 fallback 阶段。bridge MUST 将“最终可读文本”的公开语义继续收敛到单个 `description` 字段，而不是让客户端通过额外公开 schema 猜测哪些文本仍含占位符。bridge MAY 在日志中保留调试原文，但 MUST NOT 因为个别文本字段解析失败而使整个 `snapshot` 或 `actions` 构建失败。

#### Scenario: relic description 读取失败时记录日志并安全降级
- **WHEN** 某个 relic 无法从 runtime 文本来源中稳定解析 description
- **THEN** bridge MUST 记录包含 relic 标识、对象路径与 fallback 阶段的 warning 或等效 diagnostics
- **THEN** 对外 `snapshot.player.relics[]` MUST 仍返回至少包含 `name` 的结构化对象

### Requirement: 卡牌奖励选择界面必须作为 reward phase 导出并可连续决策
当奖励链路进入“选牌二级界面”（卡牌奖励选择）时，bridge MUST 将当前窗口导出为 `snapshot.phase="reward"`，并导出可选卡牌的用户向文本到 `snapshot.rewards`，同时生成对应的 `choose_reward` legal actions，使外部 agent 可以在同一 reward 链路中继续选择具体卡牌或完成该奖励步骤。

#### Scenario: 进入卡牌奖励选择界面时导出 reward phase
- **WHEN** 玩家在 `NRewardsScreen` 选择了“将一张牌添加到你的牌组。”并进入卡牌奖励选择界面
- **THEN** `snapshot.phase` MUST 等于 `reward`
- **THEN** `metadata.window_kind` MUST 标记为可区分的 reward 子窗口（例如 `reward_card_selection`）
- **THEN** `metadata.reward_subphase` MUST 标记为 `card_reward_selection`
- **THEN** `snapshot.rewards` MUST 为非空数组，按展示顺序包含每张可选卡牌的可读名称
- **THEN** `actions` MUST 为每个可选卡牌生成一个 `type="choose_reward"` 的 legal action，且其 `params.reward_index` MUST 与 `snapshot.rewards` 的索引一致

#### Scenario: reward buttons 不可用时不得回落到 combat_transition
- **WHEN** 当前没有存活敌人且 `NRewardsScreen` 不可见或 reward buttons 为 0，但卡牌奖励选择界面处于可交互状态
- **THEN** bridge MUST NOT 导出 `metadata.window_kind="combat_transition"` 作为当前决策窗口
- **THEN** bridge MUST 按卡牌奖励选择界面导出 reward 决策窗口与 legal actions

#### Scenario: 文本解析失败时仍提供可诊断且可执行的 choices
- **WHEN** 某些可选卡牌的本地化文本无法解析，只能使用 fallback 文本
- **THEN** `snapshot.rewards` MUST 仍包含与可选项数量一致的条目（例如 `card_<index>`）
- **THEN** bridge MUST 在 `metadata.text_diagnostics` 或等效 diagnostics 中指出对应条目使用了 fallback 与解析来源
- **THEN** `choose_reward` legal actions MUST 仍可按 `reward_index` 执行，不得因单个文本失败而缺失动作

#### Scenario: 不可跳过时不生成 skip_reward
- **WHEN** 当前卡牌奖励选择界面不存在跳过/关闭控件或该奖励规则不允许跳过
- **THEN** bridge MUST NOT 生成 `type="skip_reward"` 的 legal action
- **THEN** bridge MUST 在 `metadata` 中标记跳过不可用的原因（例如 `reward_skip_available=false` 与 `reward_skip_reason`）

### Requirement: reward 收尾前进窗口必须导出可执行动作
当奖励链路已经没有可领取奖励，但界面仍停留在需要玩家点击“前进/继续”后才能进入地图的窗口时，bridge MUST 将该窗口导出为 reward 链路中的可区分子窗口，并提供至少一个可执行 legal action，使外部 agent 能显式推进到地图，而不是停留在空 reward 窗口。

#### Scenario: 普通奖励收尾后出现前进按钮
- **WHEN** 玩家已经领完当前奖励，界面显示“前进/继续”按钮，且点击后才会进入地图
- **THEN** `snapshot.phase` MUST 仍可保持为 `reward` 或等效 reward 链路 phase
- **THEN** `metadata.window_kind` MUST 标记为可区分的 reward 收尾子窗口，而不是继续复用空 `reward_choice`
- **THEN** `actions` MUST 至少包含一个可执行的前进/继续 legal action

#### Scenario: 空 reward 窗口不得再被导出为可交互状态
- **WHEN** 当前 `reward_count=0`，且界面实际上处于“前进/继续”窗口
- **THEN** bridge MUST NOT 导出 `rewards=[]` 且 `actions=[]` 的稳定空 reward 窗口作为最终结果
- **THEN** bridge MUST 要么导出 continue/advance 动作，要么显式标记为短暂过渡态并附带 diagnostics

### Requirement: reward 收尾到 map 的推进信号必须可诊断
bridge MUST 在 reward 收尾、提交前进动作、进入地图三个阶段导出稳定的 metadata / diagnostics，便于 runner 与 live 验证脚本判断当前卡在“未点前进”“前进已提交等待切图”还是“已经进入 map”。

#### Scenario: 前进动作提交后进入房间过渡
- **WHEN** 外部通过 `/apply` 成功提交 reward 收尾前进动作
- **THEN** action response metadata MUST 标记这是 reward continue/advance 语义
- **THEN** 后续 `snapshot` 或 metadata MUST 能区分房间过渡中与地图已就绪两种状态

#### Scenario: 地图出现后不再保留 reward 收尾语义
- **WHEN** 地图已经出现并可选择下一个节点
- **THEN** `snapshot.phase` MUST 推进为 `map`
- **THEN** `metadata.window_kind` MUST 不再保留 reward 收尾子窗口标记
- **THEN** `actions` MUST 导出 `choose_map_node` legal actions

### Requirement: bridge 必须稳定导出 reward 到 map 的 run-flow 推进
系统 MUST 在 reward 链路结束后、地图出现前、地图选路后进入下一房间前，以及重新进入 `combat` 前，持续导出与真实窗口一致的 `snapshot` 与 metadata。bridge MUST 为 runner 提供稳定的 phase / window diagnostics，使其能够区分“仍在 reward”“地图已就绪”“房间过渡中”和“下一场战斗已进入”。

#### Scenario: reward 完成后进入 map 窗口
- **WHEN** 玩家完成当前奖励链路，界面从 `reward` 推进到 `map`
- **THEN** bridge MUST 导出 `snapshot.phase = map` 或等效 map phase
- **THEN** metadata MUST 明确标记地图窗口已就绪，而不是继续保留 reward 语义
- **THEN** bridge MUST NOT 继续导出过期的 reward diagnostics 作为当前主窗口

#### Scenario: map 选路后进入房间过渡
- **WHEN** 外部已经提交 `choose_map_node`，但下一房间或下一场战斗尚未完全载入
- **THEN** bridge MUST 导出可轮询的过渡态 `snapshot`
- **THEN** metadata MUST 标记这是地图选路后的过渡窗口，而不是把它误判回 reward 或稳定 map ready

#### Scenario: 下一房间进入 combat 决策窗口
- **WHEN** 地图选路后的房间加载完成并重新出现战斗决策
- **THEN** bridge MUST 导出 `snapshot.phase = combat`
- **THEN** 对应的 `decision_id` 与 `state_version` MUST 推进到新的 live 决策上下文

### Requirement: map 阶段必须导出可用 legal actions 与 diagnostics
系统 MUST 在地图窗口可交互时导出稳定的 `snapshot.map_nodes` 与 `choose_map_node` legal actions；在地图节点暂不可达或文本只能 fallback 时，bridge MUST 保持响应可诊断且动作仍可执行，便于 runner 安全推进。

#### Scenario: reward 后地图节点可正常导出
- **WHEN** 奖励链路结束且地图已经出现可供选择的下一个节点
- **THEN** `snapshot.phase` MUST 为 `map`
- **THEN** `snapshot.map_nodes` MUST 包含当前可达节点的稳定列表
- **THEN** `actions` MUST 导出与这些节点对应的 `choose_map_node` legal actions

#### Scenario: 地图短暂不可选时导出过渡诊断
- **WHEN** 地图界面已经切出，但当前帧还没有稳定的可达节点或可执行动作
- **THEN** bridge MUST 仍返回可序列化的 `snapshot` 与 `actions`
- **THEN** metadata MUST 说明这是暂时过渡、无可达节点或等效可诊断状态

#### Scenario: map 文本 fallback 时仍保持可执行
- **WHEN** 地图节点文本只能使用 fallback 名称或内部标签
- **THEN** `snapshot.map_nodes` 与 `actions[].label` MUST 仍保持一一对应
- **THEN** 每个 `choose_map_node` action MUST 仍能通过稳定参数执行，不得仅因 label fallback 而失效

### Requirement: 无活动 run 时必须导出 menu phase 与可执行开局动作
当 STS2 已启动且 mod 已加载，但当前没有活动 run（例如处于主菜单、开局配置、角色选择等流程）时，bridge MUST 仍然能够导出结构化快照与 legal actions，以支持自动化进入 run。此时 `snapshot` MUST 使用 `phase="menu"`（或等效稳定值）表示当前处于菜单/开局流程；并且 MUST NOT 伪造 `combat`、`map`、`reward` 的 run 内数据。

#### Scenario: 主菜单存在 Continue 时导出 continue_run
- **WHEN** 当前处于主菜单且 Continue/继续 按钮可用
- **THEN** `snapshot.phase` MUST 等于 `menu`
- **THEN** `actions` MUST 包含 `type="continue_run"` 的 legal action
- **THEN** 该 action 的 `label` MUST 为玩家可读的按钮文本或等效可读文本

#### Scenario: 主菜单无存档时导出 start_new_run
- **WHEN** 当前处于主菜单且 Continue/继续 不可用，但 New Run/开始 等入口可用
- **THEN** `snapshot.phase` MUST 等于 `menu`
- **THEN** `actions` MUST 包含 `type="start_new_run"` 的 legal action
- **THEN** bridge MUST 在 `metadata` 中提供 `menu_detection_source` 或等效 diagnostics，便于定位识别路径

#### Scenario: 进入新 run 配置后导出角色选择与确认动作
- **WHEN** 玩家已进入新 run 配置流程，且界面存在角色列表与“开始/确认”按钮
- **THEN** `actions` MUST 包含一个或多个 `type="select_character"` 的 legal actions（每个角色一个）
- **THEN** `actions` MUST 在可用时包含 `type="confirm_start_run"` 的 legal action
- **THEN** `select_character` MUST 通过 `params.character_id` 或等效稳定参数区分不同角色

#### Scenario: 不确定菜单状态时必须 fail-safe
- **WHEN** bridge 无法稳定识别当前菜单流程（例如被遮挡弹窗、版本不兼容、字段探测失败）
- **THEN** bridge MUST 返回可序列化的 `snapshot`，其 `phase` MUST 为 `menu` 或 `unknown` 的稳定值
- **THEN** bridge MUST NOT 导出可能误触危险路径的动作（例如 Exit/Abandon/删除存档 等）
- **THEN** bridge MUST 在 `metadata` 中返回可诊断信息（例如探测失败原因或候选控件摘要）

### Requirement: live runtime bridge 必须尽可能稳定读取 combat piles
当 `snapshot.phase="combat"` 时，bridge MUST 尽可能从 live runtime 读取当前玩家的抽牌堆、弃牌堆、消耗堆内容，并将其导出到统一快照。若某个 pile 暂时不可读、节点缺失或只部分可解析，bridge MUST 对该 pile 独立降级，而不是让整个 combat snapshot 失败。

#### Scenario: live runtime 成功读取三类 pile
- **WHEN** 当前玩家的 `DrawPile`、`DiscardPile`、`ExhaustPile` 在 runtime 中都可访问
- **THEN** `snapshot.player` MUST 导出三类 pile 的结构化卡牌列表
- **THEN** 这些 pile contents MUST 与同一帧里的 pile 计数字段保持一致或等效一致

#### Scenario: 单个 pile 读取失败时保持 fail-safe
- **WHEN** 某一个 pile 的 runtime collection 暂时不可读或其中个别卡牌无法完整解析
- **THEN** bridge MUST 仍然返回可序列化的 combat snapshot
- **THEN** 失败的 pile MUST 独立降级为可接受的空列表或最小 fallback 列表
- **THEN** metadata MUST 提供该 pile 的 source、fallback 或等效 diagnostics

### Requirement: live runtime bridge 必须稳定提取 enemy enrich fields 并按字段降级
当 `snapshot.phase="combat"` 时，bridge MUST 尽可能从 live runtime 读取敌人的当前招式文本、trait/tag、关键词或等效 richer enemy fields。若某个敌人的某个扩展字段暂时不可读，bridge MUST 对该 enemy 独立降级，而不是让整个 enemy 列表或 combat snapshot 失败。

#### Scenario: live runtime 成功读取敌人的当前招式说明
- **WHEN** 某个敌人的当前行动对象、显示文本或等效节点在 runtime 中可访问
- **THEN** `snapshot.enemies[]` MUST 导出该敌人的 `move_name`、`move_description` 或等效 richer fields
- **THEN** 若能解析 glossary，bridge MUST 一并导出对应的结构化 glossary anchors

#### Scenario: 单个敌人的 enrich 字段读取失败时保持 fail-safe
- **WHEN** 某个敌人的 move 文本、trait 容器或关键词来源暂时不可读
- **THEN** bridge MUST 仍然返回可序列化的 `snapshot.enemies[]`
- **THEN** 该敌人的基础字段（如 `name`、`hp`、`intent`、`powers`）MUST 继续可用
- **THEN** metadata MUST 提供该 enemy 或字段的 source、fallback 或等效 diagnostics

### Requirement: live runtime glossary hint 必须优先来自游戏真实文本来源
当 bridge 为 cards、powers、potions、enemy move 或等效 runtime 对象导出 glossary anchors 时，`hint` MUST 优先来自游戏 runtime 可读的真实词条来源，例如 `HoverTip.Description`、模型 `Description` / `SmartDescription`、`LocString` 或等效 localization 结果，而不是默认使用手写摘要文本。

#### Scenario: runtime 可读取术语 hover tip 时直接导出真实说明
- **WHEN** glossary term 对应的 runtime 对象可提供 `HoverTip` 或等效术语说明节点
- **THEN** 导出的 glossary `hint` MUST 使用该 runtime 节点解析出的文本
- **THEN** glossary `source` MUST 标识为 `runtime_hover_tip` 或等效真实来源，而不是 `fallback_builtin`

#### Scenario: 没有 hover tip 时回退到模型描述或 localization
- **WHEN** runtime 对象不存在可读 `HoverTip`，但存在 `Description`、`SmartDescription`、`LocString` 或等效 localization 入口
- **THEN** bridge MUST 继续尝试从这些来源解析 glossary `hint`
- **THEN** 只有在这些真实来源都不可用时，bridge 才可以进入 fallback

### Requirement: live runtime glossary fallback 必须显式告警且不得伪装成真实来源
当 glossary `hint` 无法从游戏 runtime 或 localization 获得时，bridge MAY 导出空 hint 或最小 fallback，但 MUST 在日志或 diagnostics 中显式告警，并且 MUST NOT 把 fallback 结果标记成 `description_text`、`runtime_hover_tip` 或其他看似真实的来源。

#### Scenario: glossary hint 解析失败时打印 warning 并保持 fail-safe
- **WHEN** 某个 glossary term 只能依赖最小 fallback 或最终拿不到 hint
- **THEN** bridge MUST 继续返回可序列化的 glossary anchor
- **THEN** bridge MUST 在日志中打印包含 glossary id、对象路径与 fallback 阶段的 warning

#### Scenario: fallback source 语义对外可区分
- **WHEN** glossary `hint` 来自 built-in fallback 或根本缺失
- **THEN** glossary `source` MUST 标识为 `fallback_builtin`、`missing_hint` 或等效可区分来源
- **THEN** 调用方 MUST 能据此区分“真实游戏说明”和“bridge 临时兜底”

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

### Requirement: 战斗窗口必须区分稳定玩家回合、敌方回合与额外选择窗口
当 `snapshot.phase="combat"` 时，bridge MUST 区分至少三类对外语义：稳定可决策的 `player_turn`、不可提交普通玩家动作的 `enemy_turn` / `combat_transition`，以及战斗内额外选牌窗口。对于非稳定玩家回合窗口，bridge MUST 不导出普通 `play_card` 与 `end_turn` 作为 legal actions。若 runtime 观察到 card selection overlay、player hand selection state 或等效选择界面信号，bridge MUST 优先导出额外选择窗口语义，而不是默认回退成普通 `player_turn`。

#### Scenario: 敌方回合只导出 enemy_turn 且无普通玩家动作
- **WHEN** 当前战斗轮到敌方行动，玩家无法继续提交出牌或结束回合
- **THEN** `metadata.window_kind` MUST 标记为 `enemy_turn` 或等效稳定值
- **THEN** `actions` MUST 不包含普通 `play_card` 或 `end_turn`

#### Scenario: 回合切换过渡中不得暴露过期玩家动作
- **WHEN** 玩家刚提交 `end_turn`，但新一轮玩家决策窗口尚未真正稳定
- **THEN** bridge MUST 将该阶段导出为 `combat_transition`、`enemy_turn` 或等效过渡窗口
- **THEN** bridge MUST NOT 继续暴露上一拍的普通玩家动作集合

#### Scenario: 额外选牌窗口优先于普通 player_turn 导出
- **WHEN** 当前战斗实际处于额外选牌窗口而不是常规出牌窗口
- **THEN** `metadata.window_kind` MUST 优先标记该额外选择窗口
- **THEN** bridge MUST 不再把该窗口默认导出为普通 `player_turn`
- **THEN** `actions` MUST 仅导出与该选择窗口匹配的 legal actions

### Requirement: 回合切换与选择窗口必须提供可诊断 metadata
bridge MUST 为战斗中的回合切换与额外选择窗口导出可诊断 metadata，以便 runner 能区分“等待敌方结算”“等待新回合稳定”“进入二级选牌窗口”。相关 metadata MUST 至少覆盖当前 `window_kind`，并 SHOULD 包含 `current_side`、`selection_kind`、`selection_source_card_id`、`transition_kind`、`overlay_top_type` 或等效字段。

#### Scenario: end_turn 后可诊断等待敌方结算
- **WHEN** 玩家已成功提交 `end_turn`，且接下来处于等待敌方行动的阶段
- **THEN** `snapshot.metadata` MUST 包含可区分当前等待阶段的稳定诊断字段
- **THEN** runner MUST 能仅依据这些字段判断当前不应继续提交普通玩家动作

#### Scenario: combat overlay 选牌窗口导出 overlay diagnostics
- **WHEN** bridge 通过 overlay top screen 或等效覆盖层节点识别到战斗额外选牌窗口
- **THEN** `snapshot.metadata` MUST 导出 `overlay_top_type` 或等效覆盖层类型诊断
- **THEN** diagnostics MUST 能区分“overlay 识别命中”“player hand 识别命中”或等效识别来源

### Requirement: live runtime bridge 必须导出结构化药水说明
当 `snapshot.phase` 处于可见玩家资源的窗口时，bridge MUST 从 live runtime 导出结构化药水对象，而不是只返回槽位标签。对于当前持有的每一瓶药水，bridge MUST 至少稳定导出 `name`，并在可读时 MUST 补充 `description`、`canonical_potion_id`、`glossary` 或等效稳定说明字段。

#### Scenario: runtime 可读取药水说明时直接导出
- **WHEN** 当前玩家药水槽位中的某瓶药水存在可访问的模型说明、hover tip 或等效 runtime 文本来源
- **THEN** `snapshot.player.potions[]` 对应条目 MUST 直接返回该药水的用户向说明文本
- **THEN** 若存在 glossary 词条，bridge MUST 一并导出结构化 glossary anchors

#### Scenario: runtime 只能读取药水名称时保守降级
- **WHEN** 当前 bridge 只能从槽位节点拿到药水名称，拿不到稳定说明文本
- **THEN** `snapshot.player.potions[]` MUST 仍返回结构化对象
- **THEN** 该条目 MUST 至少包含 `name`
- **THEN** bridge MUST 保持响应成功，而不是因为 description 缺失而失败

### Requirement: live runtime bridge 必须导出当前药水栏上限
bridge MUST 从 live runtime 导出当前玩家药水栏上限，并以 `potion_capacity` 或等效稳定字段写入 `snapshot.player`。当 runtime 读取路径存在版本差异时，bridge MUST 使用保守 fallback，并保持字段语义稳定。

#### Scenario: 战斗快照包含当前药水栏上限
- **WHEN** agent 在战斗中读取 live snapshot
- **THEN** `snapshot.player` MUST 包含 `potion_capacity` 或等效稳定字段
- **THEN** 该字段 MUST 表示当前 run / 角色 / 遗物修饰后的真实药水栏上限，而不是仅依赖调用方默认假设

### Requirement: use_potion 动作 metadata 必须复用结构化药水语义
当 bridge 导出 `use_potion` legal action 时，动作 metadata MUST 复用与 `snapshot.player.potions[]` 一致的药水观察语义，例如提供 `potion_preview`、稳定名称或知识锚点，以便策略层在动作列表中直接理解药水效果。

#### Scenario: use_potion metadata 提供当前药水预览
- **WHEN** `actions` 中存在某个 `type="use_potion"` 的 legal action
- **THEN** 该 action 的 metadata MUST 在可用时提供与对应药水一致的预览信息
- **THEN** 预览中的 `description` 与 `canonical_potion_id` 语义 MUST 与 `snapshot.player.potions[]` 保持一致或等效一致

### Requirement: live runtime 药水说明必须优先使用已渲染文本并清理低质量 glossary
当 bridge 从 live runtime 导出 `snapshot.player.potions[]` 时，药水本体 `description` MUST 优先使用游戏已经渲染完成的可读文本，而不是直接透传仍含占位符的 hover tip 模板。对于药水 glossary，bridge MUST 在 runtime 解析后执行质量过滤，只保留真实术语说明；若某条 glossary 只能得到模板化或缺失的 hint，bridge MUST 记录 diagnostics 并过滤该条目。

#### Scenario: hover tip 仍是模板时回退到可读 canonical description
- **WHEN** 某瓶药水的 runtime hover tip 或等效文本来源仍包含 `{StrengthPower}`、`{Block}` 或其他未完成渲染的模板占位
- **THEN** `snapshot.player.potions[]` 的 canonical `description` MUST NOT 直接使用该模板文本
- **THEN** bridge MUST 继续尝试已渲染 description、localization 或等效真实文本来源

#### Scenario: 低质量 potion glossary 条目被过滤并留下日志
- **WHEN** 某瓶药水的 glossary anchor 为空 hint、`missing_hint`、模板残留，或与药水自身 description 重复
- **THEN** bridge MUST 将该条目从最终 potion glossary 中过滤掉
- **THEN** bridge MUST 在日志或等效 diagnostics 中记录药水标识、对象路径、来源与过滤原因

 `move_glossary` 时，MUST 过滤 power id、canonical id、类型名或等效内部 token，并去掉与 powers、intent 或 move 文本完全重复的低价值项。若过滤后没有稳定的高价值关键字，bridge MAY 返回空数组，但 MUST 保持整个 enemy 对象成功导出。

#### Scenario: keyword 提取结果包含 power id 时被过滤
- **WHEN** 某个敌人的 keyword 候选中包含 `POWER.SLIPPERY_POWER` 或等效内部对象标识
- **THEN** 最终 `snapshot.enemies[].keywords` MUST NOT 包含该内部 id
- **THEN** bridge MUST 优先保留真正描述机制的术语或 glossary 锚点

#### Scenario: enemy keyword 过滤后仍保持 fail-safe
- **WHEN** 某个敌人的 keyword 候选大多属于内部 token、重复 move 术语或低价值噪音
- **THEN** bridge MUST 仍返回可序列化的 enemy 对象
- **THEN** `keywords` MAY 降级为空数组，但 MUST NOT 因过滤逻辑使整个 combat snapshot 失败

### Requirement: live runtime enemy power glossary 必须过滤重复本体说明与低质量条目
当 bridge 为 `snapshot.enemies[].powers[]` 导出 `glossary` 时，MUST 在 runtime 解析后执行质量过滤，只保留真正补充术语语义的 glossary anchors。若某条 glossary 与 power 本体名称或 canonical `description` 重复，或者只能得到空 hint、`missing_hint`、模板化 hint，bridge MUST 记录 diagnostics 并过滤该条目。

#### Scenario: enemy power glossary 与 power description 重复时被过滤
- **WHEN** 某个 enemy power 的 glossary anchor 仅重复该 power 的名称或整段 power 说明
- **THEN** bridge MUST 将该 glossary 条目从最终 `snapshot.enemies[].powers[].glossary` 中过滤掉
- **THEN** `description` MUST 继续作为该 power 的 canonical 本体说明

#### Scenario: enemy power glossary 低质量时过滤并记录日志
- **WHEN** 某个 enemy power 的 glossary anchor 为空 hint、`missing_hint` 或模板残留
- **THEN** bridge MUST 过滤该条目
- **THEN** bridge MUST 在日志或等效 diagnostics 中记录 enemy 标识、power 标识、路径、来源与过滤原因

### Requirement: live runtime bridge 必须将 use_potion 映射到真实药水槽位实例
当 `actions` 中存在 `type="use_potion"` 时，in-game runtime bridge MUST 基于当前玩家药水栏重新定位该药水实例，并使用游戏内真实的药水使用入口执行。bridge MUST 优先使用 `potion_index` 做槽位定位，并在可用时用 `canonical_potion_id`、名称或等效实例特征做一致性复核。

#### Scenario: 通过 potion_index 定位并使用当前药水
- **WHEN** 当前玩家药水栏中第 `<potion_index>` 个槽位与 legal action 中的 `use_potion` 语义一致
- **THEN** bridge MUST 使用该槽位实例执行药水使用流程
- **THEN** 执行后的 live state MUST 反映药水已被消耗、移除或进入新的决策上下文

#### Scenario: 槽位已变化时拒绝执行
- **WHEN** legal action 中的 `potion_index` 指向的当前槽位已经为空、换成了别的药水，或与导出时的药水语义不一致
- **THEN** bridge MUST 拒绝执行该动作
- **THEN** 返回结果 MUST 标记为 `stale_action`、`invalid_action` 或等效错误原因

### Requirement: live runtime bridge 必须为药水动作导出阶段化 diagnostics
当 `use_potion` 被提交到 in-game queue 并进入真实执行链路时，bridge MUST 记录药水动作的阶段化 metadata，至少覆盖药水槽位、候选运行时入口、最终选中的 `runtime_handler` 与失败阶段，便于排查“未入队”“已消费但失败”“运行时入口不兼容”等问题。

#### Scenario: 药水动作成功执行时返回 handler diagnostics
- **WHEN** 某个 `use_potion` 请求在游戏线程中被成功消费并执行
- **THEN** action response metadata MUST 包含药水槽位索引与实际使用的 `runtime_handler`
- **THEN** metadata SHOULD 包含 `queue_stage`、执行耗时或等效阶段信息

#### Scenario: 运行时入口不兼容时仍保持 fail-safe
- **WHEN** bridge 无法解析当前版本对应的药水使用入口，或调用入口后立即抛出运行时异常
- **THEN** bridge MUST 返回结构化失败回执
- **THEN** 返回 metadata MUST 包含失败发生的阶段与候选 handler 诊断
- **THEN** mod MUST NOT 因单次药水执行失败而导致整个 bridge 不可用

