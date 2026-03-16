## MODIFIED Requirements

### Requirement: 游戏内 mod 必须暴露 live runtime bridge
系统 MUST 能以真实 STS2 mod 的形式运行在游戏进程内，并通过 loopback bridge 对外暴露 live `health`、`snapshot`、`actions` 能力。该 bridge SHALL 复用统一的决策窗口模型，并在游戏内无活动 run、运行时未就绪或版本不兼容时返回可诊断状态，而不是崩溃或阻塞游戏。对于战斗结束后的奖励窗口，bridge MUST 稳定识别并导出 `phase = reward`，不得在 reward 已显示时错误回落到 `combat` 或继续伪造玩家战斗动作；对于 event 房间，bridge MUST 在可识别时稳定导出 `phase = event`，不得把 event 误判为 `combat_transition`、空 `map` 或未知窗口。

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

#### Scenario: event 界面显示时导出 event phase
- **WHEN** 当前房间为 `EventRoom` 或等效事件房间，且 runtime 可观察到事件正文、事件选项或继续按钮
- **THEN** `snapshot.phase` MUST 返回 `event`
- **THEN** `snapshot.metadata.window_kind` MUST 标记 `event_choice`、`event_continue` 或等效 event 子窗口
- **THEN** `actions` MUST 返回与当前事件子窗口匹配的 event 合法动作，而不是继续暴露 `end_turn`、`choose_map_node` 或空动作集合

#### Scenario: 战斗结束过渡态不得伪装为玩家战斗回合
- **WHEN** 当前战斗敌人已经全部清空，但 reward UI 仍在挂载或切换中
- **THEN** bridge MUST 优先进入 reward 识别或保守降级路径
- **THEN** bridge MUST NOT 持续导出 `window_kind = player_turn` 与可重复提交的 `end_turn` 作为主要对外语义

#### Scenario: event 房间不得误判为 combat_transition
- **WHEN** 当前 run 已进入事件房间，且没有存活敌人、没有普通奖励按钮，但事件界面已经存在可读正文或可点击项
- **THEN** bridge MUST NOT 将当前窗口长期导出为 `phase = combat` 且 `window_kind = combat_transition`
- **THEN** bridge MUST 优先识别 event 或进入带 diagnostics 的 `event_transition`

#### Scenario: runtime 读取失败时保持 fail-safe
- **WHEN** 反射读取、游戏节点发现或窗口识别过程中发生异常
- **THEN** bridge MUST 返回结构化错误或降级状态
- **THEN** mod MUST NOT 使游戏进程崩溃
- **THEN** 后续请求 MUST 仍可继续探测健康状态

### Requirement: bridge 必须稳定导出 reward 到 map 的 run-flow 推进
系统 MUST 在 reward 链路结束后、地图出现前、地图选路后进入下一房间前，以及重新进入 `combat` 前，持续导出与真实窗口一致的 `snapshot` 与 metadata。bridge MUST 为 runner 提供稳定的 phase / window diagnostics，使其能够区分“仍在 reward”“仍在 event”“地图已就绪”“房间过渡中”和“下一场战斗已进入”。

#### Scenario: reward 完成后进入 map 窗口
- **WHEN** 玩家完成当前奖励链路，界面从 `reward` 推进到 `map`
- **THEN** bridge MUST 导出 `snapshot.phase = map` 或等效 map phase
- **THEN** metadata MUST 明确标记地图窗口已就绪，而不是继续保留 reward 语义
- **THEN** bridge MUST NOT 继续导出过期的 reward diagnostics 作为当前主窗口

#### Scenario: event 完成后进入 map 或后续窗口
- **WHEN** 玩家完成当前 event 链路，界面离开事件窗口并进入地图、战斗、奖励或其他稳定 run 内窗口
- **THEN** bridge MUST 推进 `snapshot.phase` 到新的真实窗口语义
- **THEN** metadata MUST 不再保留过期的 `event_choice` 或 `event_continue` 主窗口标记
- **THEN** 新的 `decision_id` 与 `state_version` MUST 反映新的 live 决策上下文

#### Scenario: map 选路后进入房间过渡
- **WHEN** 外部已经提交 `choose_map_node`，但下一房间或下一场战斗尚未完全载入
- **THEN** bridge MUST 导出可轮询的过渡态 `snapshot`
- **THEN** metadata MUST 标记这是地图选路后的过渡窗口，而不是把它误判回 reward、event 或稳定 map ready

#### Scenario: 下一房间进入 combat 决策窗口
- **WHEN** 地图选路后的房间加载完成并重新出现战斗决策
- **THEN** bridge MUST 导出 `snapshot.phase = combat`
- **THEN** 对应的 `decision_id` 与 `state_version` MUST 推进到新的 live 决策上下文
