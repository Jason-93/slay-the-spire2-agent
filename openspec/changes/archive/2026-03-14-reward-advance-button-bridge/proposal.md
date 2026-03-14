## Why

当前 live 联调已经证明，战斗奖励收尾阶段存在一个真实断点：当界面进入“前进/继续”按钮窗口时，bridge 仍把它识别成 `reward`，但导出的 `rewards=[]` 且 `/actions=[]`，导致 runner 无法点击“前进”进入地图，更无法继续推进到下一场战斗。这个问题已经在真实游戏中复现，且直接阻断了 `reward -> map -> next combat` 自动化闭环，所以需要单独补齐。

## What Changes

- 补强 mod 对奖励收尾“前进/继续”窗口的识别，避免把该窗口继续导出为空 `reward_choice`。
- 为“前进/继续”窗口导出可执行 legal action，使外部 runner 能通过现有 `/apply` 流程点击进入地图。
- 明确 reward 完成、前进按钮、地图出现之间的 phase / metadata / diagnostics 语义，区分“仍可领奖”“需要点击前进”“正在过渡”“已进入 map”。
- 调整 autoplay runner 对该窗口的处理逻辑，支持在 reward 收尾阶段执行 continue/advance 动作，而不是把空 reward 窗口误判为卡死。
- 增加真实链路验证与测试，覆盖 card reward、普通 reward、前进按钮、地图恢复这一整段过渡。

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `in-game-runtime-bridge`: 调整奖励收尾窗口与“前进/继续”按钮的识别、metadata 与 legal actions 导出要求。
- `llm-autoplay-runner`: 调整 reward 收尾阶段的状态机与停止条件，支持点击 continue/advance 后继续推进到地图。

## Impact

- 影响 `mod/Sts2Mod.StateBridge/Providers/Sts2RuntimeReflectionReader.cs` 及相关 bridge extractor / runtime tests。
- 影响 `src/sts2_agent/orchestrator.py`、live 验证脚本与可能的 trace / 诊断字段。
- 影响 reward/map live 联调路径，重点是 `reward -> continue -> map` 这一段的自动化稳定性。
