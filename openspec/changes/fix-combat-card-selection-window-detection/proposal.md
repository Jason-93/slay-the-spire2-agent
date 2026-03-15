## Why

当前 live mod 在某些战斗选牌覆盖层出现时，会错误地继续导出 `window_kind=player_turn` 与普通 `play_card` / `end_turn` 动作，而不是导出 `combat_card_selection`。这会让 autoplay runner 与 agent 在真实对局中卡死在选牌界面，必须手动干预，因此需要优先修复 mod 侧窗口识别与动作导出。

## What Changes

- 修正 in-game runtime 对战斗选牌覆盖层的识别逻辑，覆盖 `NChooseACardSelectionScreen` 等实际运行时类型。
- 当战斗处于额外选牌窗口时，优先导出 `metadata.window_kind=combat_card_selection`，并补充稳定的 `selection_kind`、`selection_prompt` 与诊断字段。
- 在该窗口下只导出与当前选择一致的 legal actions，例如 `choose_combat_card` / `cancel_combat_selection`，不再同时暴露普通出牌动作。
- 补充 live 验证与最小回归，覆盖“覆盖层已出现但旧逻辑仍判为 player_turn”的场景。
- 增加日志与 diagnostics，便于排查未来新增的选牌屏幕类型或识别退化问题。

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `combat-selection-bridge`: 修正战斗额外选牌窗口的识别与动作导出，避免覆盖层出现时仍伪装为普通玩家回合。
- `in-game-runtime-bridge`: 强化 live runtime 对战斗覆盖层窗口的判定与 diagnostics，确保 `snapshot` / `actions` 对外语义与真实窗口一致。

## Impact

- 影响 `mod/Sts2Mod.StateBridge/Providers/Sts2RuntimeReflectionReader.cs` 中的战斗窗口识别、overlay 分析与 combat selection action 构建。
- 影响 live `/snapshot` 与 `/actions` 对外协议语义，尤其是 `metadata.window_kind`、`selection_*` diagnostics 与 legal action 集合。
- 影响 autoplay / LLM live 实测稳定性，可减少选牌界面卡死与手动介入。
