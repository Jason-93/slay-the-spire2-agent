## Why

当前 live bridge 在玩家回合与敌方回合切换边界仍会偶发返回 `409 rejected`，说明导出的 legal actions 与实际可执行时机之间还存在抖动。与此同时，部分战斗动作会触发二级选择窗口，例如“消耗 1 张牌后再继续结算”，bridge 目前没有把这类额外选牌步骤建模成稳定的状态与动作，导致自动对局在真实战斗中容易卡住或误判。

## What Changes

- 收紧 in-game runtime 的战斗窗口导出与过渡态判定，减少回合切换边界上的过期动作与 `409 rejected`。
- 为战斗中的二级选牌/额外选择窗口建立明确导出语义，支持例如“消耗一张牌”“弃一张牌”“从若干张牌中选择一张”这类步骤。
- 扩展 `/actions` 与 `/apply` 的执行契约，使额外选择动作具有稳定的 legal action、参数校验与失败语义。
- 为 runner / agent 提供可诊断的过渡态与选牌态 metadata，便于区分“正常玩家回合”“回合切换等待中”“额外选牌中”。

## Capabilities

### New Capabilities
- `combat-selection-bridge`: 定义战斗内额外选牌/二级选择窗口的状态导出、legal actions 与执行约束。

### Modified Capabilities
- `in-game-runtime-bridge`: 调整 live runtime 战斗窗口、回合切换过渡态与额外选牌窗口的导出要求。
- `action-apply-bridge`: 调整动作提交在回合切换与额外选牌场景下的校验、拒绝语义与执行闭环。

## Impact

- 受影响代码主要在 `mod/Sts2Mod.StateBridge/Providers/Sts2RuntimeReflectionReader.cs`、`mod/Sts2Mod.StateBridge/Providers/InGameRuntimeCoordinator.cs`、相关测试与 live 验证脚本。
- `/snapshot`、`/actions`、`/apply` 的 battle-time 行为会更严格，runner 需要适配新的窗口种类与额外选择动作。
- 该变更将直接提升 live LLM autoplay 在真实战斗中的稳定性，特别是长战斗与带二级选择的卡牌场景。
