## ADDED Requirements

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
