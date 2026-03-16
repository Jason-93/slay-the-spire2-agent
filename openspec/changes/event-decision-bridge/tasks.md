## 1. runtime event 导出

- [ ] 1.1 在 `mod/Sts2Mod.StateBridge` 中补充 event 房间 / screen 检测，稳定导出 `phase=event` 与 `window_kind=event_choice|event_continue|event_transition`。
- [ ] 1.2 在 live snapshot metadata 中导出 `event_title`、`event_body`、`event_options`、`event_option_count`、`event_continue_available`、`event_detection_source` 等结构化字段，并保持失败时可诊断降级。
- [ ] 1.3 更新相关 contracts / parser / fixtures，使 Python 侧能够读取并消费 event 元数据。

## 2. event 动作执行

- [ ] 2.1 为 event 窗口新增 `choose_event_option` 与 `continue_event` legal actions，并把 `option_index` 与当前可见选项稳定绑定。
- [ ] 2.2 在 `/apply` 中实现 event 选项点击与继续按钮执行映射，补充 stale / runtime_incompatible / not_clickable 等结构化失败回执。
- [ ] 2.3 为 event 动作执行补充日志与单元测试，覆盖“窗口变化后拒绝旧动作”“继续后推进到新窗口”等场景。

## 3. runner / policy 接入

- [ ] 3.1 扩展 `src/sts2_agent/policy/llm.py` 与相关模型摘要，让 LLM 能看到 event 标题、正文、选项与 continue 语义。
- [ ] 3.2 扩展 `src/sts2_agent/orchestrator.py` / `src/sts2_agent/live_autoplay.py`，让 runner 将 event 视为可决策窗口并继续推进 run-flow。
- [ ] 3.3 补充 Python 测试，覆盖 event 窗口不会被误判为未知窗口、event 动作可以进入 runner 决策闭环。

## 4. live 验证

- [ ] 4.1 增加或更新调试 / 验证脚本，支持从 event 窗口读取状态、执行 event action，并记录 artifacts。
- [ ] 4.2 在本地 bridge + live 游戏中完成一次 event 处理 smoke test，确认能够从 event 选择分支或继续退出并恢复到后续 run-flow。
