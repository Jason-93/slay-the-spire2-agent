## MODIFIED Requirements

### Requirement: Mod 必须导出统一且可扩展的决策窗口状态快照
系统 MUST 在 Slay the Spire 2 运行过程中识别当前决策窗口，并导出统一结构的状态快照，至少覆盖 `combat`、`reward`、`map`、`terminal` 四类窗口，并包含 `session_id`、`decision_id`、`state_version`、`phase` 等元数据。对于 `combat` 快照，mod MUST 在保持现有玩家、敌人、牌区与窗口元数据的同时，支持追加 richer state 字段，例如卡牌描述、升级态、目标类型、traits、结构化敌方 intent、玩家/敌方 powers，以及最小 `run_state` 上下文；新增字段 MUST 以追加式、可选字段方式导出，避免破坏现有消费方。

#### Scenario: 玩家处于战斗回合时请求 richer combat snapshot
- **WHEN** 外部调用方在玩家可行动的战斗回合请求当前快照
- **THEN** mod 返回一份 `combat` 类型的结构化状态快照，包含现有基础状态与已支持的 richer card/enemy/player fields
- **THEN** 若部分 richer 字段当前无法稳定读取，响应 MUST 仍保持 snapshot 有效，并以空值或缺省值兼容返回

## ADDED Requirements

### Requirement: Mod 必须导出最小整局规划上下文
系统 MUST 在不影响当前决策窗口导出的前提下，为 snapshot 提供最小 `run_state` 上下文，至少覆盖 `act`、`floor`、`current_room_type` 与可用的地图位置信息，以支撑后续牌库与路线规划能力。

#### Scenario: agent 在战斗中读取当前整局上下文
- **WHEN** 外部 agent 在进行中的战斗里请求 snapshot
- **THEN** 响应 MUST 包含当前所处 act、floor 与房间类型
- **THEN** 若当前 runtime 已能识别地图坐标或可达节点，mod MUST 一并导出这些最小规划上下文
