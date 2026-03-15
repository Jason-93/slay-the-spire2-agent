## MODIFIED Requirements

### Requirement: 游戏内 mod 必须将最新 agent 状态渲染为只读 overlay
系统 MUST 在游戏进程内渲染一个只读 overlay，用于展示最新一次 agent 决策的摘要信息。overlay MUST 至少能展示当前 `phase`、动作标识或动作标签、`reason`、`status`，并在可用时展示 `confidence`、`turn`、`step` 等调试字段。若存在 `detail`、历史决策或等效扩展调试信息，overlay MUST 以可滚动且不严重遮挡战斗 UI 的方式展示。该 overlay MUST 只反映调试状态，不得直接驱动任何游戏动作。

#### Scenario: 最新状态被同步后出现在游戏 UI
- **WHEN** mod 已收到一条新的有效 agent 状态
- **THEN** 游戏内 overlay MUST 刷新为这条最新状态
- **THEN** 玩家 MUST 能在游戏内直接看到本次决策摘要，而不依赖终端日志

#### Scenario: overlay 不得改变游戏逻辑
- **WHEN** overlay 显示 agent 状态
- **THEN** 该显示 MUST 仅影响 UI 呈现
- **THEN** overlay MUST NOT 自动触发出牌、选奖励、点地图或其他游戏动作

#### Scenario: 历史思路可滚动查看
- **WHEN** overlay 已积累多条 agent 决策历史，且每条都带有 `detail` 或等效思路文本
- **THEN** 玩家 MUST 能通过滚动历史区域查看最近若干条决策的摘要与思路
- **THEN** overlay MUST 不因历史增加而直接把早期思路全部丢失

### Requirement: agent 状态 overlay 必须处理 stale、会话隔离与阶段更新
系统 MUST 将 `/agent-status` 视为“最新状态快照 + 最近历史”协议，并对 stale、跨会话和生命周期切换做显式处理。若状态在约定时间内未刷新，overlay MUST 显示 `stale`、`idle` 或等效语义，而不是无限保留旧状态；若 `session_id` 切换，系统 MUST 以新会话覆盖旧状态并清空旧历史，避免跨局串状态。对于同一条决策的 `planned`、`submitted`、`accepted`、`rejected` 等生命周期推进，overlay MUST 合并为同一历史条目，而不是将每个阶段都当作独立高价值决策重复刷屏。

#### Scenario: 状态超时后进入 stale 或 idle
- **WHEN** overlay 在约定 TTL 内没有收到新的 agent 状态更新
- **THEN** overlay MUST 将当前显示切换为 `stale`、`idle` 或等效失效语义
- **THEN** overlay MUST 不再把旧动作误显示为当前有效决策

#### Scenario: 新 session 覆盖旧 session 与旧历史
- **WHEN** mod 收到一个 `session_id` 与当前缓存不同的有效 agent 状态
- **THEN** mod MUST 用新 session 的状态覆盖旧状态并清空旧历史
- **THEN** overlay MUST 不再显示旧局残留的 `turn`、`step`、`reason` 或动作信息

#### Scenario: 同一决策的生命周期更新被合并展示
- **WHEN** 同一 `session_id` 下，runner 依次推送具有相同决策语义的 `planned`、`submitted`、`accepted` 或 `rejected` 状态
- **THEN** overlay MUST 将这些更新合并到同一条历史决策上
- **THEN** 玩家 MUST 能看到该条决策的最新状态，而不是被重复状态刷屏淹没
