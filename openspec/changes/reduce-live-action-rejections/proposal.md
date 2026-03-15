## Why

当前 live autoplay 在真实对局里仍然存在较高比例的 `rejected`/`stale_action`/窗口切换失败，导致大模型虽然已经能做出基础决策，但经常因为动作提交时机不稳、窗口识别滞后、重复状态刷写或低价值动作重试而中断整场战斗。随着 HUD、战斗状态导出和动作桥接已经逐步成熟，下一步最需要解决的就是“减少无谓 reject、提升实战连续成功率”。

现在做这件事价值很高：一方面 reject 过多会直接降低整场战斗完成率，另一方面也会污染 HUD 历史和 trace，使我们难以判断到底是模型策略差，还是 runtime 时序与动作契约不够稳。

## What Changes

- 收紧 live action 提交前的本地判定，减少已知高风险窗口下的盲目 `/apply`，例如 transition、selection 切换、非玩家可操作窗口与可观测 stale snapshot。
- 增强 orchestrator 的“拒绝分类 + 有界恢复”能力，把可恢复 reject 与不可恢复 reject 区分开来，避免同一种失败反复打断整场战斗。
- 为动作选择增加更保守的提交门槛与稳定性策略，优先避免容易在窗口边缘被拒绝的动作组合，降低无效提交频率。
- 改进 HUD/trace 对 reject 的展示，把“真实决策失败”与“同一条决策的状态过渡”分开，便于观察 reject 是否正在下降。
- 扩展 live validation，增加针对 reject rate、恢复成功率和 battle 连续完成率的验证产物，便于后续迭代比较。

## Capabilities

### New Capabilities
- `live-action-rejection-recovery`: 定义 live runtime 下动作拒绝分类、恢复预算、提交门槛与 reject 诊断产物。

### Modified Capabilities
- `autoplay-orchestrator`: 增加提交前保护、reject 分类处理与更稳健的 battle 级恢复逻辑。
- `llm-autoplay-runner`: 增加面向 live reject 降噪的运行策略与验证输出。
- `agent-status-ui-bridge`: 调整 HUD 历史语义，减少同一决策状态刷屏，并更清晰展示 reject/恢复过程。
- `live-apply-validation`: 增加针对 reject 率和恢复成功率的 live 验证与 artifacts。

## Impact

- 主要影响 Python 侧 `AutoplayOrchestrator`、live runner、battle validation 脚本与 trace 结构。
- 影响 mod 侧 agent status HUD 和 reject/恢复相关诊断展示，但不要求新增 HTTP 端点。
- 会新增一组围绕 reject 分类、恢复预算、稳定提交门槛的测试与 live artifacts，用于比较优化前后的实战稳定性。
