## Why

当前 bridge 已能在 combat、map、reward 等关键窗口导出状态并提交动作，但在实际自动化测试中经常会卡在各种“继续/确认/前进（Proceed/Continue/OK）”按钮界面（例如战斗结算后从奖励链路返回地图、事件弹窗关闭、提示确认等）。这些界面通常不需要策略选择，却需要一次稳定的点击才能推进 run；缺少该能力会导致端到端自动对局与回归测试无法闭环，只能依赖人工干预。

## What Changes

- 在 `actions` 中新增一个可复用的“继续游戏/推进流程”类动作（拟定 `type="continue_game"`），用于表示当前窗口存在明确的“继续/前进/确认”按钮且点击是安全的流程推进操作。
- 在 in-game runtime 侧补充对“继续按钮/确认按钮”窗口的识别与导出：当检测到可点击控件时生成 `continue_game` legal action，并在 metadata 中给出判定来源（例如按钮文本/节点类型/探测路径）。
- 在 `POST /apply` 中增加 `continue_game` 的真实执行映射，确保动作在游戏主线程受控执行，并返回可诊断的回执（accepted/rejected/failed + handler/原因）。
- 为 fixture 与 live 联调补充回归用例与脚本，方便自动化测试稳定复现“卡住点”并验证推进成功。

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `in-game-runtime-bridge`: 增加对“继续/确认/前进”类 UI 的稳定识别与 `continue_game` legal actions 导出要求，支持自动化测试推进 run。
- `action-apply-bridge`: 扩展核心窗口动作执行映射，新增 `continue_game` 的受控执行语义与拒绝/失败诊断约束。

## Impact

- 受影响代码主要在 `mod/Sts2Mod.StateBridge/Providers/Sts2RuntimeReflectionReader.cs` 的窗口识别与动作映射，以及 `src/sts2_agent/` 中上层 orchestrator/autoplay 对“无策略决策但需推进”的处理。
- 受影响接口为 live `actions` 与 `POST /apply`（新增 action type），并会影响 `tools/validate_mod_bridge.py`、新增加的自动化冒烟脚本等测试工具。
- 对外协议字段保持最小增量：仅新增 `continue_game` action type，并通过 metadata 提供可选诊断信息。

