# agent-status-ui-bridge Specification

## Purpose
定义外部 agent 通过本地 `/agent-status` bridge 与游戏内 HUD 同步最新决策状态的协议、展示语义与生命周期约束，方便在真实 STS2 运行时直接观察模型决策。
## Requirements
### Requirement: mod 本地 bridge 必须提供扁平 agent 状态同步接口
系统 MUST 在现有本地 bridge 上提供扁平 `/agent-status` endpoint，用于同步当前 agent 的最新调试状态。该接口 MUST 至少支持写入当前状态、读取当前状态和清空当前状态三种语义，并且 MUST 与 `/apply` 的游戏动作执行协议保持解耦。

#### Scenario: 外部 runner 写入最新 agent 状态
- **WHEN** 外部 runner 对 `POST /agent-status` 提交包含 `session_id`、`phase`、`action_id`、`status`、`updated_at` 的有效 JSON
- **THEN** mod MUST 接收并保存这份最新 agent 状态
- **THEN** 返回结果 MUST 明确表示写入已成功

#### Scenario: 调试方读取当前 agent 状态
- **WHEN** 外部进程对 `GET /agent-status` 发起请求
- **THEN** mod MUST 返回当前已保存的最新 agent 状态
- **THEN** 若当前没有状态，返回结果 MUST 仍保持可解析且能表达 `idle`、`empty` 或等效空状态语义

#### Scenario: runner 停止时清空当前 agent 状态
- **WHEN** 外部 runner 对 `DELETE /agent-status` 发起请求
- **THEN** mod MUST 清除当前缓存的 agent 状态
- **THEN** 后续 overlay MUST 不再继续显示旧的动作与理由

#### Scenario: 非法 payload 不得污染当前状态
- **WHEN** 外部进程提交缺少关键字段、无法解析或类型错误的 `/agent-status` 请求体
- **THEN** mod MUST 返回结构化错误响应
- **THEN** 先前已保存的有效 agent 状态 MUST 保持不变

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

#### Scenario: 理由过长时执行稳定截断
- **WHEN** `reason` 或等效文本超过 overlay 可接受长度
- **THEN** mod MUST 对展示文本执行稳定截断、换行或等效摘要策略
- **THEN** overlay MUST 保持可读且不得严重遮挡主要战斗 UI


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

#### Scenario: 新 session 覆盖旧 session
- **WHEN** mod 收到一个 `session_id` 与当前缓存不同的有效 agent 状态
- **THEN** mod MUST 用新 session 的状态覆盖旧状态
- **THEN** overlay MUST 不再显示旧局残留的 `turn`、`step`、`reason` 或动作信息

#### Scenario: runner 更新动作生命周期时 overlay 同步推进
- **WHEN** 同一 `session_id` 下，runner 依次推送 `planned`、`submitted`、`accepted`、`rejected` 或等效阶段状态
- **THEN** overlay MUST 以最新阶段覆盖旧阶段
- **THEN** 玩家 MUST 能在游戏内观察到本次动作的生命周期推进
