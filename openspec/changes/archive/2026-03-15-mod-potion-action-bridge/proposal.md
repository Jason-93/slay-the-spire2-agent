## Why

当前 bridge 已经能在 `actions` 中导出 `use_potion`，但 mod 端还不能真正执行该动作，导致 battle autoplay 在真实对局里一旦模型选择药水就会收到 `unsupported_action` 并中断。随着整场战斗 autoplay 已经打通，这个缺口已经从“可接受的未实现能力”变成了影响连续实跑稳定性的主要短板之一。

现在补上很合适：Python 侧 runner、LLM policy、runtime snapshot 与药水说明都已经具备基础语义，缺的只是 mod 端把 `use_potion` 映射到真实游戏内药水使用流程，并补上对应的 live 验证闭环。

## What Changes

- 在 mod / bridge 的 `apply` 执行链路中新增 `use_potion` 的真实运行时映射，支持按当前 legal action 的 `potion_index` 或等效实例参数定位并使用药水。
- 为药水动作补充受控执行与失败语义，至少区分成功使用、药水已失效、目标窗口已变化、当前规则不允许使用等可诊断结果。
- 对 `use_potion` 的 live `/apply` 验证补充真实冒烟与 artifacts，确保 battle autoplay 后续可以安全放开药水动作，而不是继续在 runner 侧硬过滤。
- 收敛药水动作与 snapshot / action metadata 的一致性，确保 `snapshot.player.potions[]` 与 `actions[].metadata.potion_preview`、`apply use_potion` 的执行参数语义保持对齐。

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `action-apply-bridge`: 扩展核心真实动作执行映射与结果回执，补上 `use_potion` 的受控执行能力。
- `in-game-runtime-bridge`: 扩展 live runtime 对药水动作的运行时约束、参数定位和 diagnostics 语义。
- `live-apply-validation`: 扩展真实游戏内 apply 冒烟，覆盖至少一条可复盘的 `use_potion` 验证路径。

## Impact

- 影响 `mod/Sts2Mod.StateBridge/` 的 runtime action executor、药水定位与错误回执逻辑。
- 影响 `tools/validate_live_apply.py` 或新增 live 验证脚本的候选动作选择与 artifacts。
- 影响后续 Python 侧 autoplay 行为：该 change 完成后可以移除当前对 `use_potion` 的保守过滤，释放药水决策空间。
