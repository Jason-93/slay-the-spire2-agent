## Context

当前系统已经具备 live `snapshot`、`actions`、`/apply` 闭环，外部 runner 能够调用大模型完成自动打牌；但模型的最新决策、理由、置信度与 bridge 回执仍主要停留在终端输出和 trace 文件中。出现 reward、map、combat selection 等窗口切换问题时，开发者需要在游戏、控制台和日志之间来回对照，定位成本较高。

现有 `LocalBridgeServer` 已证明“外部进程 -> mod -> 游戏进程”链路可行，因此本次设计优先复用现有本地 HTTP bridge，而不是增加文件轮询或新的独立通道。用户已经明确希望接口保持扁平，避免 `/agent/status` 这类分层路径与额外服务拆分。

## Goals / Non-Goals

**Goals:**
- 通过新增扁平 `/agent-status` 接口，把外部 agent 的最新决策状态同步到 mod 进程内。
- 在游戏 UI 中渲染一个轻量级只读 overlay，直接展示动作、理由、置信度和执行状态。
- 保证 overlay 生命周期可控，避免跨局串状态、旧状态残留或 UI 长文本污染。
- 尽量少改现有桥接结构，沿用 `LocalBridgeServer`、in-game node 和现有 runner 生命周期。

**Non-Goals:**
- 不在本次变更中实现游戏内可交互控制面板。
- 不把完整 trace、完整 prompt 或长历史决策都塞进 overlay。
- 不改变 `/apply`、`/snapshot`、`/actions` 的既有协议语义。
- 不引入额外本地数据库、消息队列或文件轮询机制。

## Decisions

### 决策 1：使用扁平 `/agent-status` endpoint，而不是文件同步或 `/agent/status`
- 选择：在 `LocalBridgeServer` 中直接新增 `POST /agent-status`、`GET /agent-status`、`DELETE /agent-status`。
- 原因：当前 bridge 已经统一承载本地 HTTP 能力，新增同风格 endpoint 成本最低，也最符合仓库现有接口风格：`/health`、`/snapshot`、`/actions`、`/apply`。
- 备选方案：
  - 文件轮询：实现简单，但有编码、轮询延迟和 stale 清理问题。
  - `/agent/status`：语义可行，但与现有扁平 endpoint 风格不一致。

### 决策 2：mod 内仅维护一份最新 `AgentStatusSnapshot` 内存态
- 选择：bridge server 在收到请求后更新单份内存对象；overlay 每帧或每 tick 直接读取，不额外引入 provider、service、repository 分层。
- 原因：需求是“看最新状态”，不是存储历史；单份快照足以支撑调试，且最容易避免过度设计。
- 备选方案：维护历史队列或独立服务层。优势有限，但会增加状态同步复杂度和代码噪音。

### 决策 3：payload 聚焦“最新决策生命周期”，不复用 `/apply` 请求体
- 选择：`/agent-status` 使用独立 payload，至少包含 `session_id`、`phase`、`action_id`、`action_label`、`reason`、`confidence`、`status`、`turn`、`step`、`updated_at`。
- 原因：overlay 关心的是“模型解释和动作执行阶段”，而不是游戏动作参数本身；与 `/apply` 解耦更清晰。
- 备选方案：直接复用 `/apply` metadata。这样会混淆“动作执行协议”和“调试 UI 协议”，不利于后续扩展。

### 决策 4：overlay 只展示摘要，并在 mod 侧处理 stale、truncate 与 session 隔离
- 选择：overlay 默认展示最近一次状态；超出长度的 `reason` 进行截断；若超时未更新则显示 `stale` 或 `idle`；若 `session_id` 变化则覆盖旧状态。
- 原因：这些规则与 UI 呈现强相关，放在 mod 侧更容易保证展示一致性，runner 只负责推送事实状态。
- 备选方案：全部让 Python 端预处理。这样会让 UI 行为分散到客户端，调试更难统一。

### 决策 5：runner 在三个关键时点推送状态
- 选择：至少在“模型给出计划动作后”“准备提交动作时”“收到 bridge 回执后”更新 `/agent-status`；停止运行或退出时调用 `DELETE /agent-status`。
- 原因：这样能把“计划 -> 提交中 -> 接受/拒绝”的完整生命周期显示在游戏里，覆盖当前最有价值的调试信息。
- 备选方案：仅在最终结果后同步一次。实现更简单，但无法观察时序问题和 `409`、`stale_action` 之类竞争态。

## Risks / Trade-offs

- [长理由遮挡游戏 UI] -> mod 侧限制最大显示行数和字符数，必要时增加折叠或热键切换。
- [runner 异常退出导致旧状态残留] -> 增加 TTL 和 `DELETE /agent-status` 清理路径，overlay 超时后自动进入 `idle`。
- [多局或重连时串状态] -> payload 强制携带 `session_id`，新会话覆盖旧状态并重置显示。
- [新增 endpoint 被误判为写游戏状态] -> 明确该接口仅更新调试 UI，不受写动作开关控制，也不得触发游戏逻辑。
- [重绘过于频繁] -> overlay 只读内存态，不做文件 I/O；文本重建仅在状态变化时发生。

## Migration Plan

1. 先在 mod 侧落地 `AgentStatusSnapshot`、`/agent-status` 和最小 overlay，保持为纯新增能力。
2. 在 Python bridge client / runner 增加状态推送，但默认仅在 autoplay 调试链路使用。
3. 补充 live 验证：确认 endpoint 可读写、overlay 能显示最新状态、runner 停止后能清空。
4. 若实现期间发现 UI 占位或字段不足，再在同一能力下增量扩展 payload，而不回退到文件同步方案。

## Open Questions

- overlay 是否需要默认显示，还是通过热键切换显示。
- 是否要保留最近 3 条状态历史；v1 更建议仅显示最新一条，先保证稳定性。
- `confidence` 在不同 policy 后端未必总是可用；实现时需要允许为空并保持 UI 稳定。
