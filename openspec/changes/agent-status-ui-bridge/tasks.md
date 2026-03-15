## 1. Bridge 协议与内存状态

- [x] 1.1 在 `mod/Sts2Mod.StateBridge.Contracts` 中定义 `/agent-status` 对应的请求/响应模型与最小字段校验规则。
- [x] 1.2 在 `LocalBridgeServer` 中新增 `POST /agent-status`、`GET /agent-status`、`DELETE /agent-status` 路由，并保持与 `/apply` 解耦。
- [x] 1.3 在 mod 侧实现单份 `AgentStatusSnapshot` 内存状态容器，支持覆盖更新、读取、清空和 TTL 失效判断。

## 2. 游戏内 overlay

- [x] 2.1 在 in-game runtime 挂载一个只读 overlay 节点，并接入 `AgentStatusSnapshot` 的最新状态读取。
- [x] 2.2 实现 overlay 的摘要渲染规则，至少覆盖 `phase`、动作标签或动作标识、`reason`、`status`、`confidence`、`turn`、`step`。
- [x] 2.3 实现 stale 或 idle、长文本截断和 `session_id` 切换时的 UI 刷新逻辑，避免旧状态残留。

## 3. Runner 同步链路

- [x] 3.1 在 Python bridge client 中新增 `/agent-status` 调用封装，支持写入、读取和清空。
- [x] 3.2 在 autoplay / runner 中于“模型给出计划动作”“提交动作前”“收到 bridge 回执后”推送最新 agent 状态。
- [x] 3.3 在 runner 停止、异常退出或会话切换时主动清理 `/agent-status`，并保证失败时不影响主 autoplay 流程。

## 4. 验证与文档

- [x] 4.1 为 `/agent-status` 的协议和生命周期补充单元测试或等效验证脚本。
- [ ] 4.2 进行一次 live 联调，确认 overlay 能随 `planned -> submitted -> accepted/rejected` 生命周期更新，并在停止后进入 `idle` 或清空。
- [x] 4.3 更新 README 或调试文档，说明 `/agent-status` 的用途、payload 字段和常见联调方式。
