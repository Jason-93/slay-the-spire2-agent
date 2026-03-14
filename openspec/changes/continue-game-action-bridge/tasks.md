## 1. 协议与数据模型扩展

- [ ] 1.1 在 mod 侧动作类型枚举/模型中新增 `continue_game`（序列化为 `type="continue_game"`），并确保 `actions[].label` 可输出用户向文本。
- [ ] 1.2 在 Python 侧（`src/sts2_agent/`）补齐对 `continue_game` 的解析与类型兼容处理，避免未知 action type 导致崩溃或丢失诊断信息。

## 2. in-game runtime 检测与导出

- [ ] 2.1 在 `Sts2RuntimeReflectionReader` 中实现 `TryBuildContinueAction(...)`：探测 overlay/top screen 与 run node 中的候选“继续/确认/前进”控件，并校验可点击性。
- [ ] 2.2 实现保守导出策略：当窗口存在多选项策略决策时，默认不生成 `continue_game`；必要时在 `metadata` 中解释抑制原因。
- [ ] 2.3 为 `continue_game` 导出补充 diagnostics：例如 `metadata.continue_button_text`、`metadata.continue_target_type`、`metadata.continue_detection_source`（字段名可按现有 metadata 风格调整）。

## 3. apply 执行映射

- [ ] 3.1 在 `POST /apply` 路径中增加 `continue_game` 的校验与入队逻辑，确保仍受 `decision_id` 与 `read_only` 约束。
- [ ] 3.2 在游戏主线程消费阶段实现 `continue_game` 的真实执行：重新解析目标控件并触发 click/activate；失败时返回 `stale_action`/`runtime_incompatible`/`not_clickable` 等可诊断结果。
- [ ] 3.3 增加最小回归测试覆盖 `continue_game`：校验在目标控件缺失、不可点击、窗口变化时的拒绝/失败语义与回执字段。

## 4. 自动化测试与联调脚本

- [ ] 4.1 扩展 fixture provider，提供至少 1 个包含 `continue_game` 的稳定 fixture（例如 reward 结束后的 proceed/confirm 场景）。
- [ ] 4.2 新增或扩展 `tools/` 下的端到端验证脚本（例如 `validate_continue_game.py`）：等待 `continue_game` 出现并提交 apply，验证窗口推进与新的 `decision_id/state_version` 变化。
- [ ] 4.3 更新相关文档（README 或 `docs/`）记录：该动作的语义边界、常见触发窗口、以及如何在自动化测试中使用。

