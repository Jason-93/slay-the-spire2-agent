## Why

当前自动打牌链路已经能够调用大模型并执行动作，但调试时只能依赖终端日志和 trace 文件，无法在游戏内直接看到“模型准备做什么、为什么这样做、动作是否被接受”。这会显著拖慢 live 联调、问题复现和策略迭代，尤其在 reward、map、额外选牌等多阶段窗口切换时更难定位错误来源。

## What Changes

- 新增一个面向 mod 的 agent 状态同步能力，允许外部 runner 通过本地 bridge 主动推送“最新决策结果、理由与执行状态”到游戏进程内。
- 在本地 bridge 新增扁平接口 `/agent-status`，支持写入、读取与清空当前 agent UI 状态，不复用 `/apply` 的动作语义。
- 在游戏内 mod 挂载一个轻量级 overlay，将最近一次大模型决策、理由、置信度和执行状态直接显示到 UI。
- 为状态同步定义超时失效、会话隔离与文本截断规则，避免旧决策残留、UI 遮挡或跨局串状态。
- 更新 autoplay / runner 调试链路，使其在生成决策、提交动作、收到 bridge 回执后同步刷新 overlay 状态。

## Capabilities

### New Capabilities
- `agent-status-ui-bridge`: 定义外部 agent 通过本地 bridge 将最新决策状态同步到游戏内 overlay 的协议、生命周期和展示约束。

### Modified Capabilities
- None.

## Impact

- 受影响代码主要包括 `mod/Sts2Mod.StateBridge/Server/`、`mod/Sts2Mod.StateBridge/InGame/`、`src/sts2_agent/orchestrator.py`、`src/sts2_agent/policy/` 与相关调试脚本。
- 本地 HTTP bridge 将新增 `/agent-status` endpoint，但不影响既有 `/health`、`/snapshot`、`/actions`、`/apply` 语义。
- 游戏内将新增一个只读调试 overlay；它不直接改变游戏状态，也不应受写动作开关约束。
