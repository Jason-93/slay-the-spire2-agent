## Why

当前 live autoplay 在调用 `/apply` 前过度依赖 action rebase 兜底，导致策略基于旧窗口做出的 `end_turn` 等低信息动作，可能在状态已切到新玩家回合后仍被重新匹配并提交。实际 trace 已出现“新回合已有能量和可打牌动作，却仍提交旧 `end_turn`”的问题，这会直接浪费回合并污染 battle 级验证结果。

## What Changes

- 为 orchestrator 与 runner 增加“稳定决策窗口”判定：只有当 `phase`、`window_kind`、`current_side`、`round_number`、`selection_kind` 与 legal actions 在短时间内稳定后，才允许调用策略。
- 收紧 pre-submit gate 与 rebase 语义：窗口变化后优先重观测与重新决策，禁止把旧窗口的 `end_turn`、`use_potion` 跨窗口直接 rebase 到新状态。
- 扩展 trace、summary 与 live validation artifacts，明确记录 `gate_status`、`gate_reason`、是否发生 restabilize / redecide，以及错误 `end_turn` 的诊断证据。
- 补充 battle smoke / live validation 规则，确保能把“仍有高价值合法动作却错误结束回合”的问题判为失败，而不是静默通过。

## Capabilities

### New Capabilities
- live battle autoplay 在真实游戏时序下，先等待窗口稳定，再请求模型决策。
- pre-submit gate 能识别窗口漂移，并触发 reobserve -> restabilize -> redecide，而不是盲目复用旧动作。

### Modified Capabilities
- `autoplay-orchestrator`: live 决策与提交流程改为“稳定窗口优先，保守 rebase 兜底”。
- `llm-autoplay-runner`: runner 会在窗口失稳时主动重试观测与重做决策，并把稳定性诊断写入 trace / summary。
- `live-apply-validation`: battle smoke 会显式审计错误 `end_turn`、窗口漂移与恢复质量。

## Impact

- 影响 `src/sts2_agent/orchestrator.py` 中 live pre-submit gate、rebase 判定、恢复链路与 trace 字段。
- 影响 `src/sts2_agent/live_autoplay.py`、`tools/run_llm_autoplay.py`、`tools/validate_full_battle_llm.py` 的 runner 控制流与 battle 验证逻辑。
- 需要补充 orchestrator / runner 测试与 live artifacts 断言，验证不会再把旧窗口 `end_turn` 提交到新玩家回合。
