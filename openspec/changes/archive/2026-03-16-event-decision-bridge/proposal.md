## Why

当前 bridge 与 runner 主要覆盖 combat、reward、map、menu，但 run 中常见的 event 房间仍缺少稳定导出与执行支持，导致自动流程在进入事件后要么卡在误判的 `combat_transition`，要么只能停下交还人工。要继续打通“从开局到整局 run”的自动化闭环，event 必须成为一等决策窗口。

## What Changes

- 为 live runtime 新增 event 窗口识别，稳定导出 `phase=event`、事件标题、正文、可选项与必要的 diagnostics。
- 为 event 窗口新增 legal actions 与 `/apply` 执行映射，支持选择事件选项、继续/关闭事件，以及识别不可选项。
- 扩展 LLM runner / orchestrator，让自动流程能在 event 中继续决策，而不是把 event 误判为 combat、map 或未知窗口。
- 补充 event 相关的调试与验证路径，便于 live 排查“事件识别错相位”“按钮不可点击”“事件结束后未正确回到 map/combat”等问题。

## Capabilities

### New Capabilities
- `event-decision-bridge`: 定义 event 窗口的状态导出、legal actions 与事件选项执行语义。

### Modified Capabilities
- `in-game-runtime-bridge`: 扩展 live runtime phase/window 识别，使 event 房间不再误判为 `combat_transition` 或空 map。
- `action-apply-bridge`: 增加 event 相关 action 的受控执行映射与回执语义。
- `llm-autoplay-runner`: 让 runner 能在 event 窗口继续请求模型、提交 event 动作并在事件结束后恢复 run-flow。

## Impact

- C# mod runtime 导出与动作执行：`mod/Sts2Mod.StateBridge/`
- Python runner / policy / live 验证：`src/sts2_agent/`、`tools/`
- OpenSpec 新增 `event-decision-bridge` spec，并修改 `in-game-runtime-bridge`、`action-apply-bridge`、`llm-autoplay-runner`
