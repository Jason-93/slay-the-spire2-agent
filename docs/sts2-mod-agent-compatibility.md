# STS2 mod 与 Python agent 的兼容性说明

## 已对齐的核心协议

C# bridge 侧与 Python `sts2_agent` 当前共享以下稳定字段：

- `session_id`
- `decision_id`
- `state_version`
- `phase`
- `player`
- `enemies`
- `rewards`
- `map_nodes`
- `terminal`
- `action_id`
- `type`
- `params`
- `target_constraints`

兼容性元数据统一放在 `compatibility` 中，便于 agent 判断当前 bridge 是否可安全使用：

- `protocol_version`
- `mod_version`
- `game_version`
- `provider_mode`
- `read_only`
- `ready`
- `status`

## 本次变更后的真实 bridge 约束

### 1. provider mode 必须被 agent 显式识别

agent 侧不应再把所有运行态都视为单一 `runtime`，而应区分：

- `fixture`
- `runtime-host`
- `in-game-runtime`

只有 `in-game-runtime` 且 `read_only=false` 时，才应尝试真正提交写动作。

### 2. 奖励跳过动作统一为 `skip_reward`

真实 bridge 已把奖励跳过动作固定为 `skip_reward`，Python 原型也已同步。后续若实现 `HttpGameBridge`，不要再依赖旧的 `skip` 名称。

### 3. 写动作必须携带当前 `decision_id`

`POST /apply` 的最小请求体建议为：

```json
{
  "decision_id": "dec-...",
  "action_id": "act-...",
  "params": {}
}
```

agent 不应仅凭 `action_id` 盲发请求；`decision_id` 是 stale action 拦截的第一道保护。

### 4. 动作结果需要映射为三类结论

真实 bridge 会返回：

- `accepted`
- `rejected`
- `failed`

Python 侧后续接入真实 HTTP bridge 时，建议把：

- `accepted` 映射为当前 `ActionStatus.ACCEPTED`
- `rejected` 映射为可恢复失败，并保留 `error_code`
- `failed` 映射为中断或基础设施错误，触发 fail-closed

## 推荐的 Python 适配点

当前仓库还没有真实 `HttpGameBridge`。后续实现时，建议最少补齐以下逻辑：

- `attach_or_start()`: 探测本地 loopback bridge 是否在线。
- `get_snapshot()`: 调用 `GET /snapshot`。
- `get_legal_actions()`: 调用 `GET /actions`。
- `submit_action()`: 调用 `POST /apply`，并把返回结果转换为 `ActionResult`。
- `stop()` / `reset()`: 真实 STS2 bridge 目前没有对应远程生命周期接口，可先在适配层定义为 no-op 或仅清理本地状态。

## agent 侧需要保留的防御性策略

- 对每次决策都重新拉取 `snapshot` 与 `actions`，不要缓存跨窗口动作。
- 当 `/health` 显示 `read_only=true` 时，只做观测，不提交动作。
- 收到 `stale_decision`、`illegal_action`、`runtime_not_ready` 时，应重新读取状态而不是重试旧动作。
- 收到 `failed` 或连接错误时，应让 orchestrator fail-closed，避免连续误操作。

## 当前仍未覆盖的真实窗口

以下窗口仍应视为后续扩展点，而不是首版能力：

- 商店购买
- 事件分支
- 篝火操作
- 遗物交互
- 药水使用与复杂目标选择

因此，agent 设计上应允许“窗口可读但不可写”的阶段存在，不要假设每个 `phase` 都有可执行动作。
