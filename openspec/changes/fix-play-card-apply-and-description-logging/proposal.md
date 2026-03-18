## Why

当前 live bridge 在 `play_card` 上会出现“回执是 accepted，但游戏状态完全没有推进”的假成功，导致大模型反复提交同一张牌、整场自动对局卡死。同时，战斗选牌识别中的部分 description 读取会直接触发本地化格式化异常，日志被大量刷屏，掩盖真正的执行问题，也让 live 调试变得不可靠。

## What Changes

- 修正 `play_card` 的真实执行语义：bridge 不再把仅启动 UI 拖拽流程视为成功，而是优先走能稳定落地到游戏逻辑的运行时出牌入口。
- 收紧 `apply action` 的成功判定：当动作已被接收但没有触发可观察的 live 状态推进时，bridge 必须返回可诊断的失败或拒绝语义，而不是继续回报 accepted。
- 清理战斗选牌识别中的不安全 description 访问，避免为了判断窗口类型去触发 `LocString` 格式化异常。
- 将说明读取异常收敛到安全降级与日志诊断路径，避免单张卡牌描述问题污染整条自动对局链路。

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `action-apply-bridge`: 调整 `play_card` 的执行与成功判定要求，确保 accepted 对应真实状态推进或明确的后续决策变化。
- `in-game-runtime-bridge`: 调整 live runtime 的说明读取与诊断要求，确保战斗窗口识别和状态导出不会因不安全 description 访问触发格式化异常刷屏。

## Impact

- 主要影响 `mod/Sts2Mod.StateBridge/Providers/Sts2RuntimeReflectionReader.cs` 中的出牌执行、窗口识别与说明读取逻辑。
- 影响 `/apply` 的 live 语义、动作回执诊断信息，以及 full-battle LLM autoplay 的稳定性。
- 需要补充 live 验证，至少覆盖手动 `/apply play_card`、战斗选牌窗口识别，以及整场自动对局回放。
