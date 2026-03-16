## 1. 稳定窗口门控

- [x] 1.1 在 `src/sts2_agent/orchestrator.py` 中补充 stable window 判定，基于 `phase`、`window_kind`、`current_side`、`round_number`、`selection_kind` 与 legal actions 决定何时允许调用 policy。
- [x] 1.2 调整 live pre-submit gate，窗口失稳时执行 reobserve -> restabilize -> redecide，而不是沿用旧决策直接提交。
- [x] 1.3 收紧 rebase 规则，仅允许同稳定窗口内的强锚点动作受限 rebase，明确禁止 `end_turn`、`use_potion` 跨窗口 / 跨回合复用。

## 2. runner 与诊断落盘

- [x] 2.1 更新 `src/sts2_agent/live_autoplay.py` 与相关 CLI 入口，使 runner 在窗口漂移后能够重观测、重稳定并重新请求模型。
- [x] 2.2 扩展 trace / summary / artifacts，记录 `gate_status`、`gate_reason`、重决策次数、rebase 次数与错误 `end_turn` 诊断证据。
- [x] 2.3 为 orchestrator / runner 增加单元测试，覆盖“稳定后再决策”“旧 `end_turn` 不跨回合 rebase”“窗口漂移后重新决策”这些场景。

## 3. live 验证

- [x] 3.1 更新 `tools/validate_full_battle_llm.py` 或等效 live smoke 验证逻辑，识别并拒绝“仍有高价值动作却提交 `end_turn`”的运行结果。
- [x] 3.2 运行 Python 测试与本地 smoke 验证，确认 battle artifacts 能体现 stable gate / recovery 行为，且不再出现跨回合错误 `end_turn`。
- [x] 3.3 使用本地 bridge 与 LLM 端点完成一次 live battle 验证，确认修复后不会因为时序漂移提前结束玩家回合。
