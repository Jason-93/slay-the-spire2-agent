## Why

当前 `/agent-status` bridge 与游戏内 HUD 已经打通，但 live 联调表明现有 overlay 在实际菜单与战斗 UI 中仍有明显可用性问题：挂载时机不稳定、面板过大、字体容易溢出、并且会遮挡原生图标与提示信息。继续在现有实现上做零散修补，调试收益有限，应该尽快把 HUD 重构为更接近游戏原生 UI 的轻量状态卡片。

## What Changes

- 保留现有 `/agent-status` 协议与 runner 同步链路，不再改动 endpoint 语义。
- 将游戏内 HUD 从实验性 overlay 重构为稳定的 `CanvasLayer` 状态卡片，参考 `sts2_typing` 的挂载与布局方式。
- 使用延迟挂载、独立根 `Control`、受控尺寸与自动换行，解决 `_Ready` 不稳定、文本溢出和父容器裁剪问题。
- 收紧默认展示内容，只保留 `status`、`phase`、动作标签、简短 `reason`、`confidence`、`turn/step` 等摘要字段，避免遮挡核心战斗信息。
- 补充 HUD 位置、字号、截断、透明度和可见性验证要求，确保菜单、战斗、奖励等界面都能稳定显示。

## Capabilities

### New Capabilities
- `agent-status-ui-bridge`: 定义外部 agent 通过本地 bridge 将最新决策状态同步到游戏内 HUD，并约束 HUD 的稳定挂载、摘要展示与低遮挡行为。

### Modified Capabilities
- None.

## Impact

- 受影响代码主要集中在 `mod/Sts2Mod.StateBridge/InGame/` 的 overlay 节点与挂载入口。
- `/agent-status` 的 HTTP 协议、Python bridge client 与 runner 生命周期大体保持不变，影响较小。
- 文档与验证步骤需要更新，加入“菜单界面可见”“不遮挡关键图标”“中文字体不溢出”等 live 检查项。
